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

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .acts import ENDED, PAUSED, Observation, fold

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


def surface_event(s: Surface) -> dict:
    """The event recording a surface's current state, or that it is gone."""
    return {"event": EVENT_SURFACE, "data": {"surface": s.name, "state": surface_state(s) or GONE}}


def fold_surfaces(events: Iterable[dict]) -> Dict[str, str]:
    """Each surface's latest state from the log; a surface last recorded gone is absent."""
    states: Dict[str, str] = {}
    for ev in events:
        if ev.get("event") == EVENT_SURFACE:
            data = ev.get("data") or {}
            states[data.get("surface")] = data.get("state")
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
