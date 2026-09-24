"""Carry persistent state across a cycle boundary, explicitly and with provenance.

Queries are cycle-scoped by default (see ``read_events``), which makes a miss
mean exactly "not established in this cycle" instead of "I could not see". That
is only honest if state which genuinely outlives a cycle **re-asserts itself**
at the boundary rather than surviving because nothing overwrote it and an
unbounded backward search happened to find it.

This module is that re-assertion. It folds the events since the last complete
carry down to the terminal value of each persistent key and re-emits it on the
near side of the boundary, then writes a marker saying what it carried. The
marker is what keeps the work bounded: when the previous boundary carried every
family, the fold reads exactly one cycle. When it did not, because the agent
predates the carry, a family was added since, or an append failed, the fold
reads back to the last complete carry, and to the start of history if there is
none. That happens once, and the next boundary is bounded again.

**Provenance is not decoration here.** A carried assertion records where it came
from, because operator authorisation granted once and carried a hundred times
would otherwise read as freshly granted every cycle. An agent reading its own log
would find authority nobody conferred — the same manufactured-consent failure the
framework documents in narrative form, arriving instead through infrastructure.
``origin_cycle`` is taken from the source event when the source was itself
carried, so the chain reports the ORIGINAL grant rather than the last hop.
"""

import sys
import time
from typing import Dict, List, Optional, Tuple

from .agent_events_log import CYCLE_BOUNDARY_EVENT, append_event, read_events

#: Event types folded across the boundary as per-key terminal values.
CARRIED_EVENT_TYPES = frozenset({"mode_change"})

#: Within ``mode_change``, the fold is keyed by this field: the terminal value of
#: EACH mode carries, not merely the most recent mode_change of any kind. Keying
#: on recency alone would let a USER_REMOTE toggle silently drop AUTO_MODE.
CARRY_KEY_FIELD = "mode"

#: The families of state this version of the carry re-asserts. Sprint and
#: play-time scope are event-sourced and read cycle-scoped, so they are lost at a
#: boundary unless carried, exactly like a mode. The play-time timer is read the
#: same way and goes with them.
CARRY_FAMILIES = ("mode", "scope", "timer")

#: Written after every carry, whether or not anything was carried. It is what
#: bounds the next boundary's walk: a cycle holding a COMPLETE marker (every
#: family in CARRY_FAMILIES, no failed append) already contains the terminal
#: value of everything persistent, so the walk can stop there.
CARRY_MARKER_EVENT = "state_carried"

TIMER_EVENT_TYPES = frozenset({"scope_timer_set", "scope_timer_cleared", "scope_cleared"})


def _is_complete_marker(event: dict) -> bool:
    if event.get("event") != CARRY_MARKER_EVENT:
        return False
    data = event.get("data") or {}
    families = set(data.get("families") or ())
    return set(CARRY_FAMILIES) <= families and data.get("complete") is True


def _read_window() -> Tuple[List[dict], bool]:
    """Relevant events since the last complete carry, oldest first.

    Walks back from the boundary just written. The walk stops at the first
    boundary crossed AFTER a complete marker has been seen, which covers one cycle
    whenever the previous boundary carried everything, and the whole history when
    no boundary ever has. The second case is the base case the one-cycle fold
    never had: state established before the carry existed, or before a family was
    added to it, or across a boundary where the carry failed, is recovered once,
    and every later boundary is bounded again.

    Returns ``(events, bootstrapped)``; ``bootstrapped`` is True when the walk
    reached the start of history without finding a complete marker.
    """
    from .task.scope import SCOPE_EVENT_TYPES
    relevant = CARRIED_EVENT_TYPES | SCOPE_EVENT_TYPES | TIMER_EVENT_TYPES

    collected: List[dict] = []
    boundaries_seen = 0
    marker_seen = False

    for event in read_events(reverse=True, scope="all"):
        kind = event.get("event")
        if kind == CYCLE_BOUNDARY_EVENT:
            boundaries_seen += 1
            if boundaries_seen >= 2 and marker_seen:
                return list(reversed(collected)), False
            continue

        if boundaries_seen < 1:
            # Written after the boundary: this cycle's own events, already
            # visible to a cycle-scoped read and not ours to carry.
            continue

        if _is_complete_marker(event):
            marker_seen = True
        elif kind in relevant:
            collected.append(event)

    return list(reversed(collected)), True


def _terminal_modes(window: List[dict]) -> List[dict]:
    """Terminal ``mode_change`` per mode, in the order they were written.

    The order matters as much as the fold. Readers take the most recent
    ``mode_change`` of any key, so emitting AUTO_MODE after a later MANUAL_MODE
    would hand back an authority the operator had withdrawn.
    """
    terminal: Dict[str, int] = {}
    for position, event in enumerate(window):
        if event.get("event") not in CARRIED_EVENT_TYPES:
            continue
        key = (event.get("data") or {}).get(CARRY_KEY_FIELD)
        if key:
            terminal[key] = position
    return [window[p] for p in sorted(terminal.values())]


def _terminal_timer(window: List[dict]) -> Optional[dict]:
    """The play-time timer still running at the boundary, if any."""
    for event in reversed(window):
        if event.get("event") not in TIMER_EVENT_TYPES:
            continue
        if event.get("event") != "scope_timer_set":
            return None
        end = (event.get("data") or {}).get("timer_end_epoch") or 0
        return event if end > time.time() else None
    return None


def carry_state_forward(current_cycle: Optional[int] = None) -> List[str]:
    """Re-emit persistent state after the boundary, then mark the carry.

    Call immediately AFTER ``compaction_detected`` is written, not from
    PreCompact, where no boundary exists yet to write on the far side of.

    Returns the keys carried: each mode, plus ``scope`` and ``timer`` when those
    were live. An empty list is a real answer, nothing persistent was set, but it
    is NOT the only way to get one: every append could have failed instead. Those
    two are opposite facts and the return value cannot tell them apart, so a
    failed carry says so on stderr rather than leaving the caller to read silence
    as success. An unreported carry failure drops the operator's authorisation at
    a boundary and looks exactly like a quiet cycle.
    """
    if current_cycle is None:
        from .event_queries import get_cycle_number_from_events
        current_cycle = get_cycle_number_from_events()

    from .task.scope import SCOPE_EVENT_TYPES, replay_scope_events

    window, bootstrapped = _read_window()
    carried: List[str] = []
    failed: List[str] = []

    for source in _terminal_modes(window):
        data = dict(source.get("data") or {})
        key = data.get(CARRY_KEY_FIELD)

        # Preserve the ORIGINAL grant through a chain of carries. Overwriting it
        # each hop would make a hundred-cycle-old authorisation look current,
        # which is the whole failure this field exists to prevent.
        # Both reads are from the event's DATA, not from the record's top level:
        # the cycle an event was written in lives inside data, and taking it from
        # the record silently yields None and dates every carry to the present.
        data["origin_cycle"] = data.get("origin_cycle", data.get("cycle"))
        if data["origin_cycle"] is None:
            data["origin_cycle"] = current_cycle
        data["carried"] = True
        data["carried_into_cycle"] = current_cycle
        data["carried_from_timestamp"] = source.get("timestamp")

        if append_event(source.get("event", "mode_change"), data):
            carried.append(key)
        else:
            failed.append(key)

    provenance = {"carried": True, "carried_into_cycle": current_cycle}

    # Scope is re-asserted as a snapshot that replays to the same state: every
    # member activated, the paused ones paused, the finished ones completed.
    scope = replay_scope_events(e for e in window if e.get("event") in SCOPE_EVENT_TYPES)
    if scope:
        members = sorted(scope, key=lambda t: (len(t), t))
        paused = [t for t in members if scope[t] == "paused"]
        finished = [t for t in members if scope[t] == "inactive"]
        ok = append_event("scope_activated", {"task_ids": members, **provenance})
        if ok and paused:
            ok = append_event("scope_paused", {
                "task_ids": paused,
                "justification": "carried across the cycle boundary; paused before it",
                **provenance,
            })
        for tid in finished:
            ok = ok and append_event("scope_task_completed", {"task_id": tid, **provenance})
        (carried if ok else failed).append("scope")

    timer = _terminal_timer(window)
    if timer is not None:
        data = dict(timer.get("data") or {})
        data.update(provenance)
        (carried if append_event("scope_timer_set", data) else failed).append("timer")

    marker = {
        "cycle": current_cycle,
        "keys": sorted(carried),
        "families": list(CARRY_FAMILIES),
        "complete": not failed,
        "bootstrapped": bootstrapped,
    }
    if not append_event(CARRY_MARKER_EVENT, marker):
        failed.append("the carry marker")

    if failed:
        # Deliberately stderr and not another append_event: the thing that just
        # failed was appending an event, so a second one is the least likely
        # channel to survive. This is the one place a print beats the log.
        print(
            "⚠️ MACF: carry-forward FAILED for "
            f"{', '.join(sorted(failed))} into cycle {current_cycle}. That state "
            "is now absent rather than stale — authority-granting modes will "
            "read as unset until re-established, and the next boundary will "
            "walk back past this one to recover it.",
            file=sys.stderr,
        )

    return carried
