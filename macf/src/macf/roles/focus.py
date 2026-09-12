"""Focus: the one role the agent has chosen to hold, derived from events.

``role focus <id>`` and ``role unfocus`` append ``role_focus_change`` events;
the current focus is the most recent one, found by reverse scan (derive, do
not store -- the same rule work mode follows). Focus is lifetime state: it
survives compaction, so the scan reads the whole log and exits on the first
match, costing 'events since focus last changed'.
"""
from typing import Any, Dict, List, Optional

from ..agent_events_log import append_event, read_events

EVENT = "role_focus_change"


def current_focus() -> Optional[str]:
    """The focused role's id, or None."""
    for ev in read_events(reverse=True, scope="all"):   # lifetime state: see module docstring
        if ev.get("event") == EVENT:
            return ev.get("data", {}).get("role_id") or None
    return None


def last_focus_event_for(role_id: str, after_epoch: float, scope: str = "cycle") -> bool:
    """True if a focus change TO *role_id* was recorded after *after_epoch*."""
    for ev in read_events(reverse=True, scope=scope):
        if ev.get("timestamp", 0) < after_epoch:
            return False
        if ev.get("event") == EVENT and ev.get("data", {}).get("role_id") == role_id:
            return True
    return False


def set_focus(role_id: Optional[str], previous: Optional[str], unserviced: List[Dict[str, Any]] = (),
              note: str = "") -> None:
    """Record a focus change. *unserviced* is the audit trail an unfocus leaves
    behind: the due-now duties that had no service at the moment of escape."""
    append_event(EVENT, {"role_id": role_id, "previous": previous,
                         "unserviced_due_now": list(unserviced), "note": note})
