"""Carry persistent state across a cycle boundary, explicitly and with provenance.

Queries are cycle-scoped by default (see ``read_events``), which makes a miss
mean exactly "not established in this cycle" instead of "I could not see". That
is only honest if state which genuinely outlives a cycle **re-asserts itself**
at the boundary rather than surviving because nothing overwrote it and an
unbounded backward search happened to find it.

This module is that re-assertion. It folds the cycle that just ended down to the
terminal value of each persistent key and re-emits it on the near side of the
boundary. Bounded work, once per cycle, at a fixed and auditable point.

**Provenance is not decoration here.** A carried assertion records where it came
from, because operator authorisation granted once and carried a hundred times
would otherwise read as freshly granted every cycle. An agent reading its own log
would find authority nobody conferred — the same manufactured-consent failure the
framework documents in narrative form, arriving instead through infrastructure.
``origin_cycle`` is taken from the source event when the source was itself
carried, so the chain reports the ORIGINAL grant rather than the last hop.
"""

import sys
from typing import Dict, List, Optional

from .agent_events_log import CYCLE_BOUNDARY_EVENT, append_event, read_events

#: Event types folded across the boundary.
#:
#: Deliberately short, and shorter than it would have been a cycle ago. Work mode
#: is DERIVED from scope membership rather than stored, and sprint scope lives in
#: the task store rather than the event log, so neither needs carrying. The more
#: state is derived, the less there is to carry — which is the argument for
#: deriving it, restated as a maintenance cost.
CARRIED_EVENT_TYPES = frozenset({"mode_change"})

#: Within ``mode_change``, the fold is keyed by this field: the terminal value of
#: EACH mode carries, not merely the most recent mode_change of any kind. Keying
#: on recency alone would let a USER_REMOTE toggle silently drop AUTO_MODE.
CARRY_KEY_FIELD = "mode"


def _fold_previous_cycle() -> Dict[str, dict]:
    """Terminal value of each carried key in the cycle that just ended.

    Reads back past the boundary just written and stops at the one before it, so
    the walk covers exactly one cycle regardless of how long the log is.
    """
    terminal: Dict[str, dict] = {}
    boundaries_seen = 0

    for event in read_events(reverse=True, scope="all"):
        if event.get("event") == CYCLE_BOUNDARY_EVENT:
            boundaries_seen += 1
            # 1 = the boundary we were just called after; 2 = the start of the
            # cycle we are folding, and the end of the work.
            if boundaries_seen >= 2:
                break
            continue

        if boundaries_seen < 1:
            # Events written after the boundary — this cycle's own. Not ours to
            # carry; they are already visible to a cycle-scoped read.
            continue

        if event.get("event") not in CARRIED_EVENT_TYPES:
            continue

        key = (event.get("data") or {}).get(CARRY_KEY_FIELD)
        if not key:
            continue

        # Reverse order, so the first sighting of a key is its terminal value.
        terminal.setdefault(key, event)

    return terminal


def carry_state_forward(current_cycle: Optional[int] = None) -> List[str]:
    """Re-emit the previous cycle's persistent state after the boundary.

    Call immediately AFTER ``compaction_detected`` is written — not from
    PreCompact, where no boundary exists yet to write on the far side of.

    Returns the keys carried. An empty list is a real answer — nothing
    persistent was set last cycle — but it is NOT the only way to get one: every
    append could have failed instead. Those two are opposite facts and the return
    value cannot tell them apart, so a failed carry says so on stderr rather than
    leaving the caller to read silence as success. The distinction matters more
    here than almost anywhere: an unreported carry failure drops the operator's
    authorisation at a boundary and looks exactly like a quiet cycle.
    """
    if current_cycle is None:
        from .event_queries import get_cycle_number_from_events
        current_cycle = get_cycle_number_from_events()

    carried: List[str] = []
    failed: List[str] = []
    for key, source in _fold_previous_cycle().items():
        data = dict(source.get("data") or {})

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

    if failed:
        # Deliberately stderr and not another append_event: the thing that just
        # failed was appending an event, so a second one is the least likely
        # channel to survive. This is the one place a print beats the log.
        print(
            "⚠️ MACF: carry-forward FAILED for "
            f"{', '.join(sorted(failed))} into cycle {current_cycle}. That state "
            "is now absent rather than stale — authority-granting modes will "
            "read as unset until re-established.",
            file=sys.stderr,
        )

    return carried
