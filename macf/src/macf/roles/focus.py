"""Focus: the one role the agent has chosen to hold, derived from events.

``role focus <id>`` and ``role unfocus`` append ``role_focus_change`` events;
the current focus is the most recent one, found by reverse scan (derive, do
not store -- the same rule work mode follows). Focus is lifetime state: it
survives compaction, so the scan reads the whole log and exits on the first
match, costing 'events since focus last changed'.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..agent_events_log import append_event, read_events

EVENT = "role_focus_change"


def current_focus_event() -> Tuple[Optional[str], float]:
    """(focused role's id or None, epoch of the focus change that set it)."""
    for ev in read_events(reverse=True, scope="all"):   # lifetime state: see module docstring
        if ev.get("event") == EVENT:
            return ev.get("data", {}).get("role_id") or None, float(ev.get("timestamp") or 0.0)
    return None, 0.0


def current_focus() -> Optional[str]:
    """The focused role's id, or None."""
    return current_focus_event()[0]


def last_focus_event_for(role_id: str, after_epoch: float, scope: str = "cycle") -> bool:
    """True if a focus change TO *role_id* was recorded after *after_epoch*."""
    for ev in read_events(reverse=True, scope=scope):
        if ev.get("timestamp", 0) < after_epoch:
            return False
        if ev.get("event") == EVENT and ev.get("data", {}).get("role_id") == role_id:
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
