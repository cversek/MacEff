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


def _tmux_panes() -> Dict[int, str]:
    """Each tmux pane's shell pid, mapped to its session's name. Empty without tmux."""
    try:
        out = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{pane_pid} #{session_name}"],
                             capture_output=True, text=True, timeout=5)
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


def plan_attach(response: Optional[dict], session_unit: str, *,
                read_info: Optional[Callable] = None,
                verify: Optional[Callable] = None,
                ancestors: Callable[[int], List[int]] = _ancestors,
                tmux_panes: Callable[[], Dict[int, str]] = _tmux_panes,
                read_only: bool = False, control: bool = False) -> AttachPlan:
    """Decide how to attach to ``session_unit`` from the daemon's status ``response``.

    ``response`` is the daemon's status ``Response`` as a dict. There is no fallback to a
    name: a daemon that does not answer means nothing is resolved (R100).
    """
    if read_info is None or verify is None:
        from ..notify.session import read_session_info, verify_incarnation
        read_info = read_info or read_session_info
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
    return AttachPlan(NONE, reason=f"pid {pid} runs in a plain terminal, "
                                   f"not hosted by the client's daemon and not under tmux")


def readout_line(plan: AttachPlan) -> str:
    """The readout's line for attach (R101): how, or that nothing attachable hosts it."""
    if plan.kind == NONE:
        return f"Attach:       nothing attachable hosts this session ({plan.reason})"
    return f"Attach:       {' '.join(plan.argv)}  ({plan.reason})"
