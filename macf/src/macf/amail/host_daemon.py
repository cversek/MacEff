"""The broker on a host as a declared unit of its own primal daemon (MIS-0002 R53, MIS-0007 R81).

A container's start step gives the broker account a primal daemon whose declaration runs the
broker. A host has no broker account: every agent on it runs as the operator's login. So on a
host the broker gets the same shape on that login: a home of its own (by default the directory
its configuration lives in) holding a service identity and a declaration whose one unit runs the
broker. The operator's service manager starts that daemon, and the daemon starts and restarts the
broker. Under a system daemon it becomes a member by adding an ``export`` section; nothing here
changes for that (MIS-0007 R71, R79).

On a shared login the account proves nothing about which process is the broker, so what this
daemon exports is claimed (MIS-0007 R33). This module writes the identity and the declaration;
putting the daemon under the service manager is the operator's step, printed, never run.
"""
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from macf import calling_card

#: The service name in the identity, and the calling card's name: the container's broker uses both.
SERVICE = "amail_broker"
CARD_NAME = "AmailBroker"
#: The broker's unit, as the container's broker daemon declares it (persistent_layer section 14).
UNIT_NAME = "broker"
LIVENESS_INTERVAL_S = 60
MEMORY_LIMIT_MB = 256
#: The interim launchd job a host ran its broker under before this, on macOS; retired by the step.
INTERIM_LABEL_PREFIX = "maceff_amail_broker."


class HostDaemonError(ValueError):
    """A broker daemon that can't be set up as asked, with the reason."""


def service_id(domain: str) -> str:
    """The id half of the broker daemon's card: the same every time for one mail domain, and
    different for each domain on a host, as the container's ``service_agent_id`` is per deployment."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"maceff-service:{SERVICE}:{domain.strip().lower()}"))


def card_for(domain: str) -> str:
    return calling_card.build(CARD_NAME, service_id(domain))


def declaration(*, domain: str, broker_config: Path, python: Path, account: str,
                path_dirs: Sequence[str], pythonpath: Optional[str] = None) -> Dict:
    """The broker daemon's declaration: one unit that runs the broker on *broker_config*, with its
    whole environment stated (persistent_layer 5.2), validated by the daemon's own model."""
    from macf.pd.interface import Declaration
    env = {"PATH": ":".join(dict.fromkeys(d for d in path_dirs if d)), "HOME": os.path.expanduser("~"),
           "USER": account, "LOGNAME": account, "AMAIL_BROKER_CONFIG": str(broker_config)}
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    raw = {"version": 1, "agent": card_for(domain),
           "units": [{"name": UNIT_NAME, "command": [str(python), "-m", "macf.amail.daemons.broker"],
                      "account": account, "restart": "always", "liveness_interval_s": LIVENESS_INTERVAL_S,
                      "memory_limit_mb": MEMORY_LIMIT_MB, "environment": env}],
           "operator_channels": [], "notice_routes": {}}
    Declaration.model_validate(raw)
    return raw


@dataclass
class HostDaemonPlan:
    """The files the broker daemon's home needs, each with its text, and the operator's steps."""
    home: Path
    card: str
    files: Dict[Path, str] = field(default_factory=dict)
    unchanged: List[Path] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)

    def write(self) -> List[Path]:
        written = []
        for path, text in self.files.items():
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            beside = path.with_name(f".{path.name}.new")
            beside.write_text(text)
            os.chmod(beside, 0o644)
            os.replace(beside, path)
            written.append(path)
        return written


@dataclass(frozen=True, kw_only=True)
class DeclaredBroker:
    """A daemon declaration that already runs the broker on a given config: whose, and where."""
    card: str
    home: Path
    unit: str


def declared_broker(broker_config: Path, homes: Sequence[Path]) -> Optional[DeclaredBroker]:
    """The first of *homes* whose daemon declaration has a unit running the broker on *broker_config*,
    or None. A broker may already be a unit of an agent's own daemon, as on a host set up by hand; a
    second daemon for it would contend for the same socket and listener (one broker per system)."""
    from macf.pd.names import IdentityError, agent_card, declaration_path
    target = Path(broker_config).resolve()
    for home in homes:
        path = declaration_path(Path(home))
        try:
            declared = json.loads(path.read_text())
        except FileNotFoundError:   # noqa: S112 - a home with no declaration declares no broker
            continue
        except (OSError, ValueError) as e:
            print(f"⚠️ MACF: amail: {path} can't be read (not counted as declaring the broker): {e}", file=sys.stderr)
            continue
        for unit in declared.get("units") or []:
            command = [str(a) for a in unit.get("command") or []]
            conf = (unit.get("environment") or {}).get("AMAIL_BROKER_CONFIG")
            if "macf.amail.daemons.broker" in command and conf and Path(conf).resolve() == target:
                try:
                    card = agent_card(Path(home))
                except IdentityError:
                    card = str(declared.get("agent") or home)
                return DeclaredBroker(card=card, home=Path(home), unit=str(unit.get("name")))
    return None


def _identity_conflict(home: Path, card: str) -> Optional[str]:
    """Why *home* can't be the broker daemon's home, or None: it names another agent."""
    from macf.pd.names import IdentityError, agent_card
    if not (home / ".maceff" / "config.json").exists() and not (home / ".maceff_primary_agent.id").exists():
        return None
    try:
        held = agent_card(home)
    except IdentityError as e:
        return f"{home} holds identity files that don't name an agent ({e})"
    if not calling_card.same(held, card):
        return f"{home} is the home of {held}, not of the broker daemon {card}; choose another home"
    return None


def plan(broker_config: Path, *, python: Path, account: str, path_dirs: Sequence[str],
         home: Optional[Path] = None, pythonpath: Optional[str] = None,
         interim_plists: Sequence[Path] = ()) -> HostDaemonPlan:
    """What the broker daemon's *home* (default: *broker_config*'s directory) needs: the service
    identity and the declaration, and the operator's steps to retire an interim job and install
    the daemon. A file already as it should be is left alone."""
    from macf.amail.peer_setup import CardError, _load
    broker_config = Path(broker_config).resolve()
    try:
        _, addressing = _load(broker_config)
    except CardError as e:
        raise HostDaemonError(str(e)) from e
    home = Path(home).resolve() if home else broker_config.parent
    card = card_for(addressing.domain)
    elsewhere = declared_broker(broker_config, [b.home for b in addressing.agents.values() if b.home
                                                and Path(b.home).resolve() != home])
    if elsewhere is not None:
        raise HostDaemonError(f"the broker on {broker_config} is already unit {elsewhere.unit!r} of {elsewhere.card}'s "
                              f"daemon ({elsewhere.home}); a second daemon would contend for its socket and "
                              f"listener (one broker per system, MIS-0004 R01). Nothing to do here.")
    problem = _identity_conflict(home, card)
    if problem:
        raise HostDaemonError(problem)
    wanted = {
        home / ".maceff" / "config.json": json.dumps({"agent_identity": {"calling_card": CARD_NAME}}, indent=2) + "\n",
        home / ".maceff_primary_agent.id": service_id(addressing.domain) + "\n",
        home / ".maceff" / "pd" / "declaration.json": json.dumps(
            declaration(domain=addressing.domain, broker_config=broker_config, python=python, account=account,
                        path_dirs=path_dirs, pythonpath=pythonpath), indent=2) + "\n",
    }
    out = HostDaemonPlan(home=home, card=card)
    for path, text in wanted.items():
        try:
            same = path.read_text() == text
        except FileNotFoundError:
            same = False
        if same:
            out.unchanged.append(path)
        else:
            out.files[path] = text
    for plist in interim_plists:
        label = plist.stem
        out.steps.append(f"launchctl bootout gui/$(id -u)/{label} && rm {plist}   # the interim job; the "
                         f"daemon runs the broker from now on")
    out.steps.append(f"MACEFF_AGENT_HOME_DIR={home} macf_tools pd install")
    return out


def interim_jobs(launch_agents: Path) -> List[Path]:
    """The interim launchd jobs that ran a broker directly, which the daemon's unit replaces."""
    if not launch_agents.is_dir():
        return []
    return sorted(launch_agents.glob(f"{INTERIM_LABEL_PREFIX}*.plist"))
