"""What ``harness attach`` does with a name: which agent, where it is, and the command.

The pieces live elsewhere: the roster and the matcher (roster.py), the remotes and the ssh
hand-off (remotes.py), and the plan from an agent's own daemon (attach.py). This module
only decides, and returns the decision, so the command can be tested without a tmux
server or an ssh connection and ``cli.cmd_harness_attach`` is left to carry it out.

The order of preference, for an agent on this endpoint:
1. its daemon's session unit, resolved from the daemon (MIS-0002-R100);
2. the legacy harness's session, only for an agent that declares no session unit.

A declared session unit that can't be resolved is said, with the reason, and nothing is
attached: falling back to a name there is exactly what R100 forbids (persistent_layer 4.1).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from .attach import NONE, TMUX, AttachPlan, window_commands
from .roster import LOCAL, RosterEntry


@dataclass(frozen=True)
class Decision:
    """Run ``before`` in order, then replace this process with ``argv``; or exit with
    ``exit_code`` having printed ``message``."""

    argv: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    before: List[List[str]] = field(default_factory=list)
    exit_code: Optional[int] = None
    message: str = ""


def _tmux_legacy(agent: str, card: str, *, control: bool, read_only: bool,
                 has_session: Callable[[str, Dict[str, str]], bool],
                 environment: Callable[[str], Optional[Dict[str, str]]]) -> Decision:
    """The legacy harness's session, by exact name on the server that holds it."""
    # "=" forces an exact match; tmux resolves targets by prefix, so a bare name would
    # happily attach to "<agent>-stale-ssh".
    target = f"={agent}"
    env = environment(agent) or dict(os.environ)
    if not has_session(target, env):
        return Decision(exit_code=1, message=(
            f"No tmux session '{agent}' on this host.\n"
            f"   start it:  maceff_{agent.rpartition('_')[0].lower()}_harness_launch\n"
            f"   or:        systemctl --user start cc-harness-{agent}.service"))
    # -CC hands the session to iTerm2 as native windows: the client owns the alternate
    # screen, so only control mode gives native scrollback, selection and find on macOS.
    # -d evicts other clients, whose different geometries fragment the redraw; read-only
    # observers skip it.
    argv = ["tmux"] + (["-CC"] if control else []) + ["attach", "-t", target,
                                                       "-r" if read_only else "-d"]
    return Decision(argv=argv, env=env, before=window_commands(AttachPlan(TMUX, argv), card))


def decide_local(entry: RosterEntry, *, control: bool, read_only: bool,
                 plan_for_home: Callable[..., Optional[AttachPlan]],
                 has_session: Callable[[str, Dict[str, str]], bool],
                 environment: Callable[[str], Optional[Dict[str, str]]]) -> Decision:
    """Attach to ``entry`` on this endpoint: from its daemon, or its legacy session."""
    if entry.home:
        plan = plan_for_home(Path(entry.home), read_only=read_only, control=control)
        if plan is not None:
            if plan.kind == NONE:
                return Decision(exit_code=1, message=(
                    f"{entry.card}: nothing attachable hosts its session ({plan.reason})"))
            return Decision(argv=plan.argv, before=window_commands(plan, entry.card or ""))
    if not entry.identifier:
        return Decision(exit_code=1, message=f"{entry.account}: no card, so no session to name")
    return _tmux_legacy(entry.identifier, entry.card or "", control=control, read_only=read_only,
                        has_session=has_session, environment=environment)


def decide_remote(entry: RosterEntry, remotes, *, control: Optional[bool],
                  read_only: bool) -> Decision:
    """Hand the attach to ``entry``'s remote, which resolves it from its own daemon."""
    from .remotes import handoff_argv
    remote = next((r for r in remotes.remotes if r.name == entry.endpoint), None)
    if remote is None:
        return Decision(exit_code=1, message=f"{entry.card}: no remote named {entry.endpoint!r} "
                                             f"is declared any more")
    try:
        argv = handoff_argv(remote, entry, control=control, default_control=remotes.control,
                            read_only=read_only)
    except ValueError as e:
        return Decision(exit_code=1, message=str(e))
    return Decision(argv=argv)


def by_card(entries: Sequence[RosterEntry], card: str) -> Optional[RosterEntry]:
    """The local entry with exactly this card: what a remote hand-off names."""
    hits = [e for e in entries if e.card == card and e.endpoint == LOCAL]
    return hits[0] if len(hits) == 1 else None


def decide(entry: RosterEntry, remotes, *, control: Optional[bool], read_only: bool,
           **local) -> Decision:
    """Attach to the one agent the name resolved to, wherever it is."""
    if entry.endpoint != LOCAL:
        return decide_remote(entry, remotes, control=control, read_only=read_only)
    chosen = remotes.control if control is None else control
    return decide_local(entry, control=chosen, read_only=read_only, **local)
