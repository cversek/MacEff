"""Focus: the one role the agent has chosen to hold, derived from events.

``role focus <id>`` and ``role unfocus`` append ``role_focus_change`` events;
the current focus is the most recent one, found by reverse scan (derive, do
not store -- the same rule work mode follows). Focus is lifetime state: it
survives compaction because the cycle carry re-asserts it at each boundary, so
the scan reads one cycle (#460). A carried focus event is a continuation, not
an act: its time is the original's, and it never acknowledges a duty.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..agent_events_log import append_event, read_events

EVENT = "role_focus_change"


#: The carry's marker (``macf.cycle_carry.CARRY_MARKER_EVENT``), and the family name
#: it lists when it carried the focus.
CARRY_MARKER = "state_carried"
CARRY_FAMILY = "focus"


def _since(ev: Dict[str, Any]) -> float:
    data = ev.get("data") or {}
    return float(data.get("carried_from_timestamp") or ev.get("timestamp") or 0.0)


def current_focus_event() -> Tuple[Optional[str], float]:
    """(focused role's id or None, epoch of the focus change that set it).

    Cycle-scoped. A miss is authoritative only when this cycle's carry says it
    carried the focus; a cycle opened before the carry knew about focus falls back
    to the whole log, once, the way the carry itself bootstraps."""
    carried_here = False
    for ev in read_events(reverse=True):
        kind = ev.get("event")
        if kind == EVENT:
            return ev.get("data", {}).get("role_id") or None, _since(ev)
        if kind == CARRY_MARKER and CARRY_FAMILY in ((ev.get("data") or {}).get("families") or ()):
            carried_here = True
    if carried_here:
        return None, 0.0
    for ev in read_events(reverse=True, scope="all"):   # before the carry knew focus
        if ev.get("event") == EVENT:
            return ev.get("data", {}).get("role_id") or None, _since(ev)
    return None, 0.0


def current_focus() -> Optional[str]:
    """The focused role's id, or None."""
    return current_focus_event()[0]


def last_focus_event_for(role_id: str, after_epoch: float, scope: str = "cycle") -> bool:
    """True if a focus change TO *role_id* was recorded after *after_epoch*."""
    for ev in read_events(reverse=True, scope=scope):
        if ev.get("timestamp", 0) < after_epoch:
            return False
        data = ev.get("data", {})
        if ev.get("event") == EVENT and data.get("role_id") == role_id and not data.get("carried"):
            return True
    return False


CHARTER_EVENT = "role_charter_shown"


def note_charter_shown(role_id: str, charter_mtime: float) -> None:
    """The charter reached the agent's context (focus, engage, or SessionStart)."""
    append_event(CHARTER_EVENT, {"role_id": role_id, "charter_mtime": charter_mtime})


def charter_fresh(role_id: str, charter_mtime: float, session_id: str = "") -> bool:
    """True if this role's charter, at this mtime, was shown earlier in the
    current cycle and (when known) the current session -- so a repeat may be
    suppressed without the Boundaries ever having been absent from context."""
    for ev in read_events(reverse=True, scope="cycle"):
        if ev.get("event") != CHARTER_EVENT:
            continue
        data = ev.get("data", {})
        if data.get("role_id") != role_id:
            continue
        if session_id and not str(ev.get("breadcrumb", "")).startswith(f"s_{session_id[:8]}"):
            return False                     # shown, but in another session: context did not carry it
        return float(data.get("charter_mtime") or 0) >= charter_mtime
    return False


def set_focus(role_id: Optional[str], previous: Optional[str], unserviced: List[Dict[str, Any]] = (),
              note: str = "") -> None:
    """Record a focus change. *unserviced* is the audit trail an unfocus leaves
    behind: the due-now duties that had no service at the moment of escape."""
    append_event(EVENT, {"role_id": role_id, "previous": previous,
                         "unserviced_due_now": list(unserviced), "note": note})
