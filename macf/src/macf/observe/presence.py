"""Presence: who can see the session, and how, as one record the call line reads.

MIS-0002-R91 (call_line_MUST_show_presence): the observed agent's per-call line shows each
onlooker that watches and each operator surface that is present.
MIS-0002-R98 (presence_MUST_say_enabled_when_undetectable): a surface that cannot detect
its viewer says it is enabled, never that someone is attached.
MIS-0002-R102 (presence_SHOULD_show_reachable): an operator reachable through a channel is
told apart from an operator attached at a keyboard.
MIS-0002-R97 (keyboard_surface_MUST_set_presence) is the head maintainer's judgment per
surface; ``surface_state`` is where a surface declares what it can know.

The record is not kept anywhere: the per-call hook derives it from the agent's own event
log, which it already reads, so it cannot drift from the acts (R16) or outlive the daemon.
When the daemon is not alive, presence is said as unknown, never shown as nobody there.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .acts import ENDED, EVENT_END, EVENT_INVITE, EVENT_PAUSE, EVENT_RESUME, PAUSED, Observation, fold

ATTACHED = "attached"
ENABLED = "enabled"
REACHABLE = "reachable"


@dataclass(frozen=True)
class Surface:
    """An operator surface: how the operator can reach the session.

    ``keyboard`` surfaces can type (a terminal, a remote-control viewer); a channel can
    only carry messages. ``detects_viewer`` says whether the surface can tell that someone
    is looking, and ``viewer_seen`` what it saw.
    """

    name: str
    keyboard: bool
    detects_viewer: bool = True
    viewer_seen: bool = False


def surface_state(s: Surface) -> Optional[str]:
    """What a surface may claim, or None when it is not present at all."""
    if not s.keyboard:
        return REACHABLE
    if not s.detects_viewer:
        return ENABLED
    return ATTACHED if s.viewer_seen else None


def build(surfaces: Iterable[Surface], observations: Dict[str, Observation]) -> dict:
    """The presence record: surfaces present, with their state, and onlookers watching."""
    present = []
    for s in surfaces:
        st = surface_state(s)
        if st is not None:
            present.append({"surface": s.name, "state": st})
    watching = [{"onlooker": o.onlooker, "paused": o.status == PAUSED}
                for o in sorted(observations.values(), key=lambda o: o.onlooker) if o.status != ENDED]
    return {"version": 1, "surfaces": present, "onlookers": watching}


#: A surface's state, as the primal daemon records it when the state changes. The name is
#: provisional until the step-1 contract settles it.
EVENT_SURFACE = "pd_surface_state"
GONE = "gone"
#: The primal daemon's start (``macf.pd.interface.EVENT_DAEMON_START``, pinned equal by a
#: test). Named here rather than imported, because the per-call line reads presence on
#: every tool call and the interface module builds the declaration's models on import.
DAEMON_START = "pd_daemon_start"


def surface_event(s: Surface) -> dict:
    """The event recording a surface's current state, or that it is gone."""
    return {"event": EVENT_SURFACE, "data": {"surface": s.name, "state": surface_state(s) or GONE}}


def fold_surfaces(events: Iterable[dict]) -> Dict[str, str]:
    """Each surface's latest state since the newest daemon start; a surface last recorded
    gone is absent. A state an earlier daemon recorded says nothing about the operator now,
    so a daemon's start begins the fold again. A row that doesn't name a surface and its
    state as strings costs only itself, as in ``fold``: the per-call line and the carry
    both read this."""
    states: Dict[str, str] = {}
    for ev in events:
        if ev.get("event") == DAEMON_START:
            states.clear()
        elif ev.get("event") == EVENT_SURFACE:
            data = ev.get("data")
            name = data.get("surface") if isinstance(data, dict) else None
            st = data.get("state") if isinstance(data, dict) else None
            if not (isinstance(name, str) and isinstance(st, str)):
                print(f"⚠️ MACF: observe: skipped a malformed {EVENT_SURFACE} at {ev.get('timestamp')}: "
                      f"{data!r}", file=sys.stderr)
                continue
            states[name] = st
    return {name: st for name, st in states.items() if name and st and st != GONE}


def from_events(events: Iterable[dict], daemon_alive: bool) -> Optional[dict]:
    """The presence record, derived from the observed agent's own log at read time.

    Nothing is copied into a file of its own, so nothing outlives its writer: when the
    primal daemon is not alive, presence is unknown (None), never a stale "watching" and
    never "nobody". Onlookers come from the observation acts (R90), surfaces from their
    recorded states.
    """
    if not daemon_alive:
        return None
    events = list(events)
    surfaces = [{"surface": name, "state": st} for name, st in sorted(fold_surfaces(events).items())]
    record = build([], fold(events))
    record["surfaces"] = surfaces
    return record


def call_line(record: Optional[dict]) -> str:
    """The presence segment of the per-call line (R91), or '' when nobody can see the session."""
    if record is None:
        return "presence: unknown"
    parts: List[str] = []
    onlookers = record.get("onlookers") or []
    if onlookers:
        names = [o["onlooker"] + (" (paused)" if o.get("paused") else "") for o in onlookers]
        parts.append("onlookers: " + ", ".join(names))
    surfaces = record.get("surfaces") or []
    if surfaces:
        parts.append("operator: " + ", ".join(f"{s['surface']} {s['state']}" for s in surfaces))
    return " · ".join(parts)


#: What the segment reads from the cycle's own events. A compaction carries open
#: observations and present surfaces across (``macf.cycle_carry``), so the cycle is enough.
OBSERVE_EVENTS = (EVENT_INVITE, EVENT_PAUSE, EVENT_RESUME, EVENT_END, EVENT_SURFACE, DAEMON_START)


def daemon_alive(card: str, base: Optional[Path] = None) -> bool:
    """Whether the agent's primal daemon is alive: its record names a live process by pid
    and start time. The record alone is not enough, since a pid is reused; ``ps`` is asked
    for the start time, a few milliseconds on macOS."""
    from macf.notify.session import verify_incarnation
    from macf.pd.names import record_path
    try:
        record = json.loads(record_path(card, base).read_text())
        pid, start = record["pid"], record["proc_start"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return isinstance(pid, int) and isinstance(start, str) and verify_incarnation(pid, start)


def segment(agent_home: Path, events: Optional[Iterable[dict]] = None) -> str:
    """The presence segment of the agent's per-call line (R91), '' when there is none.

    Shown only for an agent that declares a daemon, so an agent without one isn't told
    "unknown" on every call. The declaration is the test, because it is the one sign a
    daemon is meant to run that holds on every platform: a container under the start
    script has no unit file, and the daemon's record goes when it stops. Declared and not
    alive is ``presence: unknown``, never nobody.
    """
    from macf.pd.names import IdentityError, agent_card, declaration_path
    if not declaration_path(agent_home).exists():
        return ""
    try:
        card = agent_card(agent_home)
    except IdentityError:
        return call_line(None)
    if not daemon_alive(card):
        return call_line(None)
    if events is None:
        from macf.agent_events_log import read_events
        events = read_events(reverse=False, only=OBSERVE_EVENTS)
    return call_line(from_events(events, True))
