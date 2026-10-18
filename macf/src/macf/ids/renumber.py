"""Move an existing deployment's accounts and groups onto their declared numbers, once.

Run as root inside the deployment's container BEFORE it is recreated on an image that
declares the id block: the old numbers are known only to this container's live
``/etc/passwd`` and ``/etc/group``, which the recreate replaces. The seats are paused and
their sessions stopped first, because their processes still run as the old numbers.

Every account and group the framework owns is mapped by NAME, from its number in the live
tables to its declared one (``AgentsConfig.ids``): the agents and their own groups,
``admin``, the shared groups and the amail services, plus any deployment service account
named with ``--service NAME=NUMBER``. Files are re-owned only under the roots named: the
volumes the framework knows (``/home``, the shared workspace, the amail stores) and any
bind mount the caller adds. A symlink is re-owned itself and never followed, and a mount
inside a root is left alone unless it is a root too.

A bind mount holds host files. In there an old number may be a host account's own file,
not the container account's (the overlap this exists to end), so the plan lists such
roots apart for the operator to read before ``--apply``. A file whose access list names
users or groups is listed too: re-owning does not rewrite an access list.
"""
import grp
import os
import pwd
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple

#: The roots the framework itself owns in a deployment container.
FRAMEWORK_ROOTS = ("/home", "/shared_workspace", "/var/lib/amail_broker", "/var/lib/amail_ingest")
ACL_XATTR = "system.posix_acl_access"
#: How many paths the summary names under each finding; the listing holds them all.
SHOWN = 10


class RenumberRefused(Exception):
    """The mapping is ambiguous or incomplete; nothing has been changed."""


@dataclass
class Mapping:
    uid: Dict[int, int] = field(default_factory=dict)
    gid: Dict[int, int] = field(default_factory=dict)
    #: number -> the name it was mapped by, for the listing.
    uid_names: Dict[int, str] = field(default_factory=dict)
    gid_names: Dict[int, str] = field(default_factory=dict)

    def empty(self) -> bool:
        return not self.uid and not self.gid


def wanted(config, services: Dict[str, int]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Declared numbers by name: (accounts, groups)."""
    ids = config.ids
    users = {"admin": ids.slot("admin"), "amail_broker": ids.slot("amail_broker"),
             "amail_ingest": ids.slot("amail_ingest")}
    groups = dict(users)
    groups.update({g: ids.slot(g) for g in ("agents_all", "sa_all", "policyeditors")})
    block = range(ids.base, ids.base + 1000)
    for name, number in services.items():
        if number not in block:
            raise RenumberRefused(f"service {name} at {number} is outside the block {block.start}-{block.stop - 1}")
        users[name] = groups[name] = number
    for spec in config.agents.values():
        users[spec.username] = groups[spec.username] = spec.uid
    return users, groups


def derive(config, services: Dict[str, int],
           getpw: Callable[[str], int] = lambda n: pwd.getpwnam(n).pw_uid,
           getgr: Callable[[str], int] = lambda n: grp.getgrnam(n).gr_gid) -> Mapping:
    """Old number -> declared number, by name, from the live tables. A name absent from the
    live tables has nothing to move. Two names on one old number, or two old numbers onto
    one new number, are refused: either would re-own one identity's files as another's."""
    users, groups = wanted(config, services)
    m = Mapping()
    for kind, table, lookup, out, names in (("account", users, getpw, m.uid, m.uid_names),
                                           ("group", groups, getgr, m.gid, m.gid_names)):
        new_seen: Dict[int, str] = {}
        for name, new in sorted(table.items()):
            if new in new_seen:
                raise RenumberRefused(f"{kind}s {new_seen[new]} and {name} are both declared at {new}")
            new_seen[new] = name
            try:
                old = lookup(name)
            except KeyError:
                continue
            if old == new:
                continue
            if old in out:
                raise RenumberRefused(
                    f"{kind}s {names[old]} and {name} both hold {old} in this container; "
                    f"which one owns its files cannot be told")
            if old in table.values():
                raise RenumberRefused(
                    f"{kind} {name} holds {old}, which is another name's declared number; "
                    f"move that one first or choose another block")
            out[old] = new
            names[old] = name
    return m


@dataclass
class Plan:
    #: (path, old uid, old gid, new uid, new gid), in walk order.
    changes: List[Tuple[str, int, int, int, int]] = field(default_factory=list)
    acl_files: List[str] = field(default_factory=list)
    skipped_mounts: List[str] = field(default_factory=list)
    missing_roots: List[str] = field(default_factory=list)
    #: (path, uid, gid) left after the move on a number outside the block that nothing maps:
    #: the base image's ubuntu account at 1000, say. After the recreate such a file belongs to
    #: whoever holds that number on the host, the overlap the move exists to end.
    unmapped: List[Tuple[str, int, int]] = field(default_factory=list)
    #: Planned executables whose setuid or setgid bit takes effect: chown clears both, even as root.
    setid_files: List[str] = field(default_factory=list)


def _walk(root: Path) -> Iterator[Tuple[Path, os.stat_result]]:
    """Every entry under *root*, the root included, without following symlinks or crossing
    onto another filesystem; a crossing point is yielded with st_dev differing, once."""
    top = os.lstat(root)
    yield root, top
    stack = [root]
    while stack:
        here = stack.pop()
        try:
            entries = list(os.scandir(here))
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            continue
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue                                     # gone since the listing: nothing to move
            p = Path(e.path)
            if st.st_dev != top.st_dev:
                yield p, st      # the mount point itself, flagged by the caller
                continue
            yield p, st
            if stat.S_ISDIR(st.st_mode):
                stack.append(p)


def plan(mapping: Mapping, roots: Iterable[str],
         has_acl: Optional[Callable[[str], bool]] = None, block: Optional[range] = None) -> Plan:
    """Every entry the move would re-own, and what it would leave behind. With *block*, an
    entry whose owner after the move is outside the block, and not root, is named as unmapped."""
    has_acl = has_acl or _has_acl
    out = Plan()
    root_list = [str(Path(r)) for r in roots]
    for root in root_list:
        r = Path(root)
        if not os.path.lexists(r):
            out.missing_roots.append(root)
            continue
        top_dev = os.lstat(r).st_dev
        for p, st in _walk(r):
            if st.st_dev != top_dev:
                if str(p) not in root_list:
                    out.skipped_mounts.append(str(p))
                continue
            nu = mapping.uid.get(st.st_uid, st.st_uid)
            ng = mapping.gid.get(st.st_gid, st.st_gid)
            if (nu, ng) != (st.st_uid, st.st_gid):
                out.changes.append((str(p), st.st_uid, st.st_gid, nu, ng))
                if stat.S_ISREG(st.st_mode) and _setid_takes_effect(st.st_mode):
                    out.setid_files.append(str(p))
            if block is not None and not stat.S_ISLNK(st.st_mode) and (
                    (nu != 0 and nu not in block) or (ng != 0 and ng not in block)):
                out.unmapped.append((str(p), nu, ng))
            if not stat.S_ISLNK(st.st_mode) and has_acl(str(p)):
                out.acl_files.append(str(p))
    return out


def _setid_takes_effect(mode: int) -> bool:
    """A setuid or setgid bit that changes what running the file does: setuid with the owner's
    execute bit, setgid with the group's. Setgid on a file nobody can execute (mode 2664, which a
    shared group directory's files often carry) changes nothing, so clearing it loses nothing."""
    return bool((mode & stat.S_ISUID and mode & stat.S_IXUSR) or (mode & stat.S_ISGID and mode & stat.S_IXGRP))


def _has_acl(path: str) -> bool:
    try:
        return ACL_XATTR in os.listxattr(path, follow_symlinks=False)
    except OSError:
        return False


def apply(p: Plan, chown: Callable[[str, int, int], None] = None) -> Tuple[int, List[Tuple[str, str]]]:
    """Re-own every planned path, symlinks themselves. A path that can't be re-owned (gone,
    read-only, refused) is recorded and the rest still go, so one failure never leaves the move
    stopped halfway with a traceback. Returns (changed, [(path, why)]). The live account tables are
    untouched, so the mapping derives the same again, and a rerun finishes what is left."""
    chown = chown or (lambda path, u, g: os.chown(path, u, g, follow_symlinks=False))
    done, failed = 0, []
    for path, _ou, _og, nu, ng in p.changes:
        try:
            chown(path, nu, ng)
            done += 1
        except OSError as e:
            failed.append((path, e.strerror or type(e).__name__))
    return done, failed


def processes_on(numbers: Iterable[int], proc: Path = Path("/proc"),
                 gids: Iterable[int] = ()) -> List[Tuple[int, str, str]]:
    """(pid, which number, command) for each running process whose real or effective uid is one
    the move re-numbers, or whose real or effective gid is. Such a process keeps writing as its old
    number while its files move, and what it writes then is left outside the block (the amail
    broker and ingest, an admin login). Which number reads ``uid 998`` or ``gid 1007``."""
    wanted = {"Uid:": set(numbers), "Gid:": set(gids)}
    found = []
    for d in proc.iterdir():
        if not d.name.isdigit():
            continue
        try:
            status = (d / "status").read_text()
            comm = (d / "comm").read_text().strip()
        except OSError:
            continue
        hits = {}
        for line in status.splitlines():
            key = line[:4]
            if key in wanted and key not in hits:
                real, eff = (int(x) for x in line.split()[1:3])
                hit = real if real in wanted[key] else eff if eff in wanted[key] else None
                hits[key] = None if hit is None else f"{key[:3].lower()} {hit}"
        which = hits.get("Uid:") or hits.get("Gid:")
        if which:
            found.append((int(d.name), which, comm))
    return found


def render(mapping: Mapping, p: Plan, bind_roots: List[str]) -> str:
    lines = ["uid moves:"] + [f"  {o} -> {n}  ({mapping.uid_names[o]})" for o, n in sorted(mapping.uid.items())]
    lines += ["gid moves:"] + [f"  {o} -> {n}  ({mapping.gid_names[o]})" for o, n in sorted(mapping.gid.items())]
    if mapping.empty():
        lines.append("nothing to move: every account and group already holds its declared number")
    lines.append(f"files to re-own: {len(p.changes)}")
    by_root: Dict[str, int] = {}
    for path, *_ in p.changes:
        root = next((b for b in sorted(bind_roots, key=len, reverse=True) if path == b or path.startswith(b + "/")), None)
        if root:
            by_root[root] = by_root.get(root, 0) + 1
    for root, n in sorted(by_root.items()):
        lines.append(f"  BIND MOUNT {root}: {n} file(s); an old number here may be a host account's "
                     f"own file, read the listing before --apply")
    for m in p.missing_roots:
        lines.append(f"  root not present, skipped: {m}")
    for m in p.skipped_mounts:
        lines.append(f"  mount inside a root, not touched (name it as a root to include it): {m}")
    if p.acl_files:
        lines.append(f"files with an access list ({len(p.acl_files)}): re-owning does not rewrite "
                     f"entries naming old numbers; check them with getfacl")
    if p.unmapped:
        numbers = sorted({n for _path, u, g in p.unmapped for n in (u, g)})
        lines.append(f"files left outside the block ({len(p.unmapped)}), on {', '.join(map(str, numbers))}: "
                     f"no declared name maps these numbers, so the move leaves them, and after the "
                     f"recreate they belong to whoever holds those numbers on the host; re-own or "
                     f"remove them by hand (they are in the listing)")
        lines += [f"  {path}  {u}:{g}" for path, u, g in p.unmapped[:SHOWN]]
        if len(p.unmapped) > SHOWN:
            lines.append(f"  ... {len(p.unmapped) - SHOWN} more")
    if p.setid_files:
        lines.append(f"setuid or setgid files to re-own ({len(p.setid_files)}): chown clears those "
                     f"bits, even as root; set them again after --apply if they were meant")
        lines += [f"  {path}" for path in p.setid_files[:SHOWN]]
        if len(p.setid_files) > SHOWN:
            lines.append(f"  ... {len(p.setid_files) - SHOWN} more")
    return "\n".join(lines)
