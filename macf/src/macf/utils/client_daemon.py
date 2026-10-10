"""Adopting the sessions Claude Code's own background daemon already supervises.

MIS-0002-R66 (pd_MUST_adopt_harness_supervisor): where the harness supervises a
session itself, the primal daemon adopts that session instead of starting a second
supervisor over it. This module is the decision and the vocabulary, not the daemon:
given the agent's session unit and what the client's daemon hosts, it says whether to
adopt, to start, or to refuse, and it turns a control act into the client's own verb.

MEASURED on 2.1.296 (macOS):
- a hosted session is recognised by its sidecar's ``kind: "bg"``, never by argv, which
  is the generic ``claude bg-spare`` of a pre-started host;
- a SIGTERM ends the session as "done" and nothing respawns it, so a signal is never a
  restart; ``claude respawn <id>`` brings the same session back, and ``claude stop``
  ends it with its conversation kept;
- the client's daemon is transient: it starts on demand and exits soon after its last
  client, so its absence says nothing about whether a hosted session is alive. Orphaned
  workers keep their sidecars and are found the same way.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

#: What the primal daemon does about its session unit.
ADOPT = "adopt"
START = "start"
REFUSE = "refuse"

#: The control acts the primal daemon sends a unit (MIS-0002-R70), and the client verb
#: each becomes for an adopted session. A restart is a respawn: the client restarts a
#: running background session in place, under the same session id. Attaching is not a
#: control act: it needs a terminal, so the operator's own command runs ``claude attach``
#: (``utils.attach``) and the daemon never does.
CLIENT_VERBS = {
    "start": "respawn",
    "restart": "respawn",
    "stop": "stop",
}


@dataclass(frozen=True)
class AdoptionDecision:
    """What to do about one session unit, and why, in words an event can carry."""

    unit: str
    action: str
    session_id: Optional[str] = None
    pid: Optional[int] = None
    reason: str = ""


def _in_home(cwd: str, home: Path) -> bool:
    """True when ``cwd`` is the agent home or a directory below it, both resolved.

    Agents often run their session in a project directory under their home, so an exact
    match would miss them and start a second supervisor beside the client's. Containment
    is by path component, so a neighbouring home whose name extends this one (``/x/ira``
    and ``/x/ira2``) is never inside it.
    """
    try:
        return Path(os.path.realpath(cwd)).is_relative_to(Path(os.path.realpath(home)))
    except (OSError, ValueError, TypeError):
        return False


def decide(unit, hosted: Iterable, agent_home: Path) -> AdoptionDecision:
    """Adopt, start or refuse for ``unit``, given the sessions the client hosts.

    ``unit`` needs ``name`` and ``kind``; ``hosted`` holds readout entries with
    ``session_id``, ``pid`` and ``cwd`` (``notify.session.harness_hosted_sessions``).
    A service unit is never the client's to supervise, so it is always started. A
    session unit is adopted when exactly one hosted session runs in the agent's home or
    a directory below it. Two or more is refused: adopting one would leave another
    supervised twice, and picking by recency is a guess.
    """
    if getattr(unit, "kind", "service") != "session":
        return AdoptionDecision(unit.name, START, reason="a service unit; the client does not host it")
    mine = [h for h in hosted if _in_home(h.cwd, Path(agent_home))]
    if not mine:
        return AdoptionDecision(unit.name, START,
                                reason="no session the client hosts runs in the agent home or below it")
    if len(mine) > 1:
        ids = ", ".join(h.session_id[:8] for h in mine)
        return AdoptionDecision(unit.name, REFUSE,
                                reason=f"the client hosts {len(mine)} sessions in the agent home ({ids}); "
                                       f"the operator chooses which is the agent's")
    h = mine[0]
    return AdoptionDecision(unit.name, ADOPT, session_id=h.session_id, pid=h.pid,
                            reason="the client's daemon already supervises this session")


def client_command(act: str, session_id: str, claude: str = "claude") -> List[str]:
    """The client's own command for a control act on an adopted session.

    Never a signal: a signalled worker ends as "done" and stays down. A respawn can fail
    once the client has pruned a finished job; the caller then treats the session as not
    hosted and decides again, which starts it fresh, rather than retrying the respawn.
    """
    verb = CLIENT_VERBS.get(act)
    if verb is None:
        raise ValueError(f"no client verb for control act {act!r}; known: {', '.join(sorted(CLIENT_VERBS))}")
    if not session_id:
        raise ValueError("an adopted session needs its session id")
    return [claude, verb, session_id]


def unit_state(hosted_status: str) -> tuple:
    """The unit state (MIS-0002-R20) of an adopted, live session, with its reason.

    The sidecar's status is turn state, stamped at transitions, so it never says a
    session waits on a person; that inference belongs to the readout (MIS-0002-R21).
    A live hosted process is running, and the raw status goes into the reason.
    """
    return "running", f"hosted by the client's daemon, turn state {hosted_status or 'unknown'}"
