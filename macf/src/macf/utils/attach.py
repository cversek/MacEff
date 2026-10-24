"""Attach by name, resolved from the agent's primal daemon.

MIS-0002-R100 (attach_MUST_resolve_from_pd): the session to attach to comes from the
daemon's own status, never from a tmux name or the environment. A rename, a second
session with a similar name, or a session the client's daemon hosts all defeat a
name lookup; the daemon knows which process is the agent's session unit.

MIS-0002-R101 (readout_MUST_say_nothing_attachable): when nothing attachable hosts the
session, the answer says so, with the reason, instead of failing quietly.

The daemon's status gives the session unit's pid and start time. From there:
- a session the client's background daemon hosts attaches through the client's own
  verb, ``claude attach <id>``;
- a session under tmux attaches to the pane's session, by exact name;
- anything else (a bare terminal, a stale pid) has nothing to attach to, and says so.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

CLIENT = "client"
TMUX = "tmux"
NONE = "none"

#: Unit states with a live session behind them.
_LIVE = ("running", "waiting_on_a_person", "starting")


@dataclass(frozen=True)
class AttachPlan:
    """How to attach, or why there is nothing to attach to."""

    kind: str
    argv: List[str] = field(default_factory=list)
    reason: str = ""


def _ancestors(pid: int) -> List[int]:
    """``pid`` and its ancestors, nearest first, as ``ps`` reports them."""
    chain = []
    seen = set()
    while pid and pid > 1 and pid not in seen:
        chain.append(pid)
        seen.add(pid)
        try:
            out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
            pid = int(out) if out else 0
        except (OSError, ValueError, subprocess.TimeoutExpired):
            break
    return chain


def _tmux_panes(env: Optional[Dict[str, str]] = None) -> Dict[int, str]:
    """Each tmux pane's shell pid, mapped to its session's name. Empty without tmux.
    ``env`` selects another server, a session unit's (``TMUX_TMPDIR``)."""
    try:
        out = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{pane_pid} #{session_name}"],
                             capture_output=True, text=True, timeout=5, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    panes = {}
    for line in out.stdout.splitlines():
        fields = line.split(" ", 1)
        if len(fields) == 2 and fields[0].isdigit() and fields[1]:
            panes[int(fields[0])] = fields[1]
    return panes


def _session_unit(response: Optional[dict], unit: str) -> tuple:
    """The named unit's status from a daemon response, or None with the reason."""
    if response is None:
        return None, "the primal daemon did not answer"
    if not response.get("ok"):
        return None, f"the primal daemon refused: {response.get('error') or 'no reason given'}"
    for u in response.get("units") or []:
        if u.get("unit") == unit:
            return u, ""
    return None, f"the primal daemon reports no unit named {unit!r}"


def _owned(path) -> bool:
    """A directory this account owns: another account's server is no keyboard of ours."""
    import os
    try:
        return path.is_dir() and path.stat().st_uid == os.getuid()
    except OSError:
        return False


def plan_attach(response: Optional[dict], session_unit: str, *,
                read_info: Optional[Callable] = None,
                verify: Optional[Callable] = None,
                ancestors: Callable[[int], List[int]] = _ancestors,
                tmux_panes: Callable[..., Dict[int, str]] = _tmux_panes,
                read_only: bool = False, control: bool = False,
                tmux_tmpdir: Optional[str] = None) -> AttachPlan:
    """Decide how to attach to ``session_unit`` from the daemon's status ``response``.

    ``response`` is the daemon's status ``Response`` as a dict. There is no fallback to a
    name: a daemon that does not answer means nothing is resolved (R100).
    """
    if read_info is None or verify is None:
        from ..notify.session import read_session_info, verify_incarnation
        read_info = read_info or (lambda pid: read_session_info(pid, missing_ok=True))
        verify = verify or verify_incarnation

    status, why = _session_unit(response, session_unit)
    if status is None:
        return AttachPlan(NONE, reason=why)
    state = status.get("state")
    if state not in _LIVE:
        return AttachPlan(NONE, reason=f"the session unit is {state}; no session runs")
    pid = status.get("pid")
    if not pid:
        return AttachPlan(NONE, reason="the primal daemon reports no pid for the session unit")
    if not verify(pid, status.get("proc_start")):
        return AttachPlan(NONE, reason=f"pid {pid} is no longer the session the primal daemon started")

    info = read_info(pid)
    if info is not None and getattr(info, "kind", None) == "bg":
        return AttachPlan(CLIENT, ["claude", "attach", info.session_id],
                          reason="the client's daemon hosts this session")

    panes = tmux_panes()
    for p in ancestors(pid):
        if p in panes:
            argv = ["tmux"] + (["-CC"] if control else []) + ["attach", "-t", f"={panes[p]}"]
            argv.append("-r" if read_only else "-d")
            return AttachPlan(TMUX, argv, reason=f"the session runs in tmux session {panes[p]!r}")
    if tmux_tmpdir:
        # A session unit (pd.session_unit): the unit's process is the wrapper, which
        # parents its own tmux server, so the session's pane descends from the unit
        # rather than the other way round, on the server under ``tmux_tmpdir``.
        import os
        from pathlib import Path
        # The card's own server first; then this account's other session-unit servers beside
        # it, for a unit declared with another --agent, which names its server after that.
        # Either way the pane is found by descent from the daemon's pid, never by a name.
        here = Path(tmux_tmpdir)
        servers = [here] + sorted(d for d in here.parent.glob("*.tmux")
                                  if d != here and _owned(d))
        for server in servers:
            env = {**os.environ, "TMUX_TMPDIR": str(server)}
            env.pop("TMUX", None)
            for pane, name in tmux_panes(env).items():
                if pid in ancestors(pane):
                    argv = (["env", f"TMUX_TMPDIR={server}", "tmux"] + (["-CC"] if control else [])
                            + ["attach", "-t", f"={name}", "-r" if read_only else "-d"])
                    return AttachPlan(TMUX, argv, reason=f"the session unit runs tmux session {name!r} "
                                                         f"on its own server")
    return AttachPlan(NONE, reason=f"pid {pid} runs in a plain terminal, "
                                   f"not hosted by the client's daemon and not under tmux")


def readout_line(plan: AttachPlan) -> str:
    """The readout's line for attach (R101): how, or that nothing attachable hosts it."""
    if plan.kind == NONE:
        return f"Attach:       nothing attachable hosts this session ({plan.reason})"
    return f"Attach:       {' '.join(plan.argv)}  ({plan.reason})"


def plan_attach_for_home(home, *, read_only: bool = False, control: bool = False,
                         ask: Optional[Callable] = None, load: Optional[Callable] = None,
                         card_of: Optional[Callable] = None, base=None,
                         **probes) -> Optional[AttachPlan]:
    """How to attach to the session of the agent whose home is ``home``, from its daemon.

    The card comes from the home's own files and the session unit from the agent's
    declaration (the one unit of kind ``session``); the daemon's status says which process
    that unit is (R100). None means the agent declares no session unit, so any session it
    has is the legacy harness's; a declared one that can't be resolved is a plan of kind
    ``none`` with the reason, never a guess by name (persistent_layer 4.1).
    """
    from ..pd.client import DaemonUnavailable
    from ..pd.core import DeclarationRefused
    from ..pd.session_unit import tmux_dir
    from .identity import session_identifier
    if card_of is None:
        from ..pd.names import agent_card as card_of
    if load is None:
        from ..pd.core import load_declaration as load
    if ask is None:
        from ..pd.client import ask

    try:
        card = card_of(home)
        declaration = load(home, card)
    except (DeclarationRefused, OSError, ValueError) as e:
        return AttachPlan(NONE, reason=f"the agent's declaration can't be read: {e}")
    session = next((u for u in declaration.units if u.kind == "session"), None)
    if session is None:
        return None
    try:
        response = ask(card, {"op": "status"}).model_dump()
    except DaemonUnavailable as e:
        return AttachPlan(NONE, reason=f"the primal daemon did not answer: {e}")
    return plan_attach(response, session.name, read_only=read_only, control=control,
                       tmux_tmpdir=str(tmux_dir(session_identifier(card), base)), **probes)


def plan_attach_for_card(card: str, *, read_only: bool = False, control: bool = False,
                         ask: Optional[Callable] = None, base=None, **probes) -> AttachPlan:
    """How to attach to the session of the agent with ``card``, from its daemon alone.

    For an agent whose home isn't known here (a second agent on one login, whose home the
    roster can't place), so its declaration can't name the session unit. The daemon's
    status still says which processes are its units, and the session is the live unit
    whose process parents a pane on the card's own tmux server (R100): found by descent
    from the daemon's own pid, never by a name.
    """
    from ..pd.client import DaemonUnavailable
    from ..pd.session_unit import tmux_dir
    from .identity import session_identifier
    if ask is None:
        from ..pd.client import ask

    try:
        response = ask(card, {"op": "status"}).model_dump()
    except DaemonUnavailable as e:
        return AttachPlan(NONE, reason=f"the primal daemon did not answer: {e}")
    tmpdir = str(tmux_dir(session_identifier(card), base))
    reasons = []
    for unit in response.get("units") or []:
        plan = plan_attach(response, unit.get("unit"), read_only=read_only, control=control,
                           tmux_tmpdir=tmpdir, **probes)
        if plan.kind != NONE:
            return plan
        reasons.append(f"{unit.get('unit')}: {plan.reason}")
    return AttachPlan(NONE, reason="no unit of the primal daemon hosts a session here ("
                                   + ("; ".join(reasons) or "it reports no units") + ")")


def window_commands(plan: AttachPlan, card: str) -> List[List[str]]:
    """The tmux commands that name the attached window by ``card`` and keep that name.

    Run before the attach, on the same server the attach reaches. A read-only plan gets
    none: an onlooker changes nothing in the session it watches.
    """
    if plan.kind != TMUX or "-r" in plan.argv:
        return []
    tmux_at = plan.argv.index("tmux")
    prefix = plan.argv[:tmux_at + 1]
    target = plan.argv[plan.argv.index("-t") + 1] + ":"
    return [prefix + ["rename-window", "-t", target, card],
            prefix + ["set-window-option", "-t", target, "automatic-rename", "off"],
            prefix + ["set-window-option", "-t", target, "allow-rename", "off"]]
