"""Which uid and gid numbers are held by more than one identity, across the host and its containers.

The host's tables and each running container's are read, and every number is listed with its
holder in each place. A number held in two places by different accounts is an overlap: to the
kernel those are one identity, so a file one writes into a shared mount, a process one runs,
or a firewall rule keyed on the number belongs to both.

A number at or above 1000 is a person's or an agent's, and two holders of it are two identities
whatever their names. Those overlaps fail the audit.

Below 1000 the numbers are system ids, which each side's packages allocate on their own: a
container's ``sshd`` or ``postgres`` takes whatever number its image's install handed out,
and the host gave the same number to something else. Those are reported in their own section
and do not fail the audit. Renumbering cannot reach them, since the packages create them; only
user-namespace remapping would. A system id held under the same name in every place (``root``
0, ``nobody`` 65534) is the same account by design and is not reported at all. Numbers a
deployment pins for its own services belong in its id block above 1000, where they count.

A place whose table can't be read is a failure, never a clean result: "nothing overlaps" must
mean every place was read.
"""
import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

KINDS = ("passwd", "group")
HOST = "host"
#: Below this, a number is a distribution's system id; at or above it, a person's or an agent's.
SYSTEM_ID_CEILING = 1000
#: ``nobody`` and ``nogroup``: a system id at the top of the range.
OVERFLOW_ID = 65534
COMMAND_TIMEOUT_S = 20

#: Runs an argv and returns its stdout; raises ``subprocess.CalledProcessError``, ``OSError`` or
#: ``subprocess.TimeoutExpired`` when it can't. Injected so tests need no docker.
Runner = Callable[[Sequence[str]], str]


def run_command(argv: Sequence[str]) -> str:
    return subprocess.run(list(argv), capture_output=True, text=True, check=True,
                          timeout=COMMAND_TIMEOUT_S).stdout


class Unreadable(Exception):
    """A place's table could not be read; the audit cannot say that place is clear."""


@dataclass(frozen=True)
class Holder:
    place: str
    name: str


@dataclass
class Report:
    places: List[str]
    #: kind -> number -> its holders, every place included.
    held: Dict[str, Dict[int, List[Holder]]] = field(default_factory=dict)
    #: place -> why its tables could not be read.
    unreadable: Dict[str, str] = field(default_factory=dict)
    #: why the host was left out of the comparison, when it was.
    host_left_out: str = ""

    def overlaps(self, kind: str) -> Dict[int, List[Holder]]:
        """Numbers at or above 1000 held by more than one identity: these fail the audit."""
        return {n: hs for n, hs in sorted(self.held.get(kind, {}).items())
                if not is_system(n) and is_overlap(n, hs)}

    def system_overlaps(self, kind: str) -> Dict[int, List[Holder]]:
        """System ids held under different names in different places: reported, not failing."""
        return {n: hs for n, hs in sorted(self.held.get(kind, {}).items())
                if is_system(n) and is_overlap(n, hs)}

    @property
    def clean(self) -> bool:
        return not self.unreadable and not any(self.overlaps(k) for k in KINDS)

    def exit_code(self) -> int:
        """0 every place read and nothing overlaps; 1 an overlap; 2 a place could not be read."""
        if self.unreadable:
            return 2
        return 0 if self.clean else 1

    def to_dict(self) -> dict:
        return {
            "places": self.places,
            "host_left_out": self.host_left_out,
            "unreadable": self.unreadable,
            "overlaps": {k: _as_json(self.overlaps(k)) for k in KINDS},
            "system_overlaps": {k: _as_json(self.system_overlaps(k)) for k in KINDS},
            "exit_code": self.exit_code(),
        }


def _as_json(found: Dict[int, List[Holder]]) -> dict:
    return {str(n): [{"place": h.place, "name": h.name} for h in hs] for n, hs in found.items()}


def is_system(number: int) -> bool:
    return number < SYSTEM_ID_CEILING or number == OVERFLOW_ID


def is_overlap(number: int, holders: List[Holder]) -> bool:
    """Whether the holders of *number* are more than one identity: held in two places or more,
    and, for a system id, under more than one name."""
    if len({h.place for h in holders}) < 2:
        return False
    return not (is_system(number) and len({h.name for h in holders}) == 1)


def parse_table(text: str) -> List[Tuple[str, int]]:
    """``name:x:number:...`` lines, as getent and /etc/passwd and /etc/group print them."""
    rows = []
    for line in text.splitlines():
        fields = line.split(":")
        if len(fields) < 3 or not fields[0] or line.startswith("#"):
            continue
        try:
            rows.append((fields[0], int(fields[2])))
        except ValueError:
            continue
    return rows


def read_table(kind: str, place: str, run: Runner) -> List[Tuple[str, int]]:
    """The *kind* table of *place*: ``getent``, or the file itself where a container has no getent."""
    prefix = [] if place == HOST else ["docker", "exec", place]
    errors = []
    for argv in (prefix + ["getent", kind], prefix + ["cat", f"/etc/{kind}"]):
        try:
            rows = parse_table(run(argv))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            errors.append(f"{' '.join(argv[len(prefix):])}: {e}")
            continue
        if rows:
            return rows
        errors.append(f"{' '.join(argv[len(prefix):])}: no entries")
    raise Unreadable("; ".join(errors))


def running_containers(run: Runner) -> List[str]:
    try:
        out = run(["docker", "ps", "--format", "{{.Names}}"])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        raise Unreadable(f"docker ps: {e}") from e
    return sorted(n for n in out.split() if n)


#: Why the host is not compared off Linux.
NOT_SHARED_KERNEL = ("this host is not Linux: its containers run in a Linux VM whose kernel the "
                     "host does not share, so a host number and a container number are not one "
                     "identity here; the containers are compared with each other only")


def audit(containers: Optional[List[str]] = None, run: Runner = run_command,
          platform: str = sys.platform) -> Report:
    """Read the host and each container (every running one when *containers* is None).

    The host is compared only on Linux, where containers share its kernel. Elsewhere
    (Docker Desktop or Colima on macOS) they run in a VM, the host's own accounts may not
    even be in /etc/passwd, and only the containers, which share the VM's kernel, are
    compared with each other."""
    unreadable: Dict[str, str] = {}
    if containers is None:
        try:
            containers = running_containers(run)
        except Unreadable as e:
            unreadable["docker"] = str(e)
            containers = []
    on_linux = platform.startswith("linux")
    report = Report(places=([HOST] if on_linux else []) + list(containers), unreadable=unreadable,
                    host_left_out="" if on_linux else NOT_SHARED_KERNEL)
    for kind in KINDS:
        report.held[kind] = {}
    for place in report.places:
        try:
            tables = {kind: read_table(kind, place, run) for kind in KINDS}
        except Unreadable as e:
            report.unreadable[place] = str(e)
            continue
        for kind, rows in tables.items():
            for name, number in rows:
                report.held[kind].setdefault(number, []).append(Holder(place, name))
    return report


def render(report: Report) -> str:
    """One table per kind: each overlapping number, and who holds it in each place."""
    lines = [f"places read: {', '.join(p for p in report.places if p not in report.unreadable) or 'none'}"]
    if report.host_left_out:
        lines.append(f"host left out: {report.host_left_out}")
    for place, why in report.unreadable.items():
        lines.append(f"UNREADABLE {place}: {why}")
    def rows(found: Dict[int, List[Holder]]) -> List[str]:
        out = []
        for number, holders in found.items():
            by_place: Dict[str, List[str]] = {}
            for h in holders:
                by_place.setdefault(h.place, []).append(h.name)
            cells = [f"{p}={'/'.join(by_place[p])}" for p in report.places if p in by_place]
            out.append(f"  {number:>6}  " + "  ".join(cells))
        return out

    for kind in KINDS:
        label = "uid" if kind == "passwd" else "gid"
        overlaps = report.overlaps(kind)
        if overlaps:
            lines.append(f"{label}: {len(overlaps)} number(s) at or above 1000 held by more than one identity")
            lines.extend(rows(overlaps))
        else:
            lines.append(f"{label}: no overlap at or above 1000")
    for kind in KINDS:
        label = "uid" if kind == "passwd" else "gid"
        system = report.system_overlaps(kind)
        if system:
            lines.append(f"system {label}s under different names (allocated by each side's packages; "
                         f"reported, not counted): {len(system)}")
            lines.extend(rows(system))
    verdict = {0: "CLEAN", 1: "OVERLAP", 2: "INCOMPLETE: a place could not be read"}[report.exit_code()]
    lines.append(verdict)
    return "\n".join(lines)


def render_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)
