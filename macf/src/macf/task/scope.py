"""
Task scope management for AUTO_MODE boundary enforcement.

Scope tracks which tasks are actively being worked on, enabling the Stop hook
to block premature stopping when scoped tasks remain incomplete.

State is persisted via the event system (agent_events_log.jsonl), following
the same pattern as mode tracking (detect_auto_mode/set_auto_mode).

Scope lifecycle:
  scope_activated → tasks are active
  scope_task_completed → individual task becomes inactive
  scope_cleared → all tasks removed from scope

API follows the Full Disclosure Principle (cli_development.md §9):
  Functions return WHAT CHANGED, not just success/failure.
  The CLI caller prints each individual change.
"""

from typing import Dict, List, Optional, Tuple
from ..agent_events_log import append_event, read_events


def set_scope(task_ids: List[str], parent_expanded: bool = False,
              expanded_from: Optional[str] = None, session_id: str = "") -> dict:
    """Activate scope for a set of task IDs.

    Returns:
        Dict with 'tasks_scoped' (list of IDs), 'parent_expanded' (bool),
        'expanded_from' (parent ID or None), 'success' (bool).
    """
    result = {
        "tasks_scoped": list(task_ids),
        "parent_expanded": parent_expanded,
        "expanded_from": expanded_from,
        "success": False,
    }

    success = append_event(
        event="scope_activated",
        data={
            "task_ids": list(task_ids),
            "parent_expansion": parent_expanded,
            "expanded_from": expanded_from,
            "session_id": session_id,
        },
    )
    result["success"] = success
    return result


def complete_scoped_task(task_id: str, session_id: str = "") -> dict:
    """Mark a scoped task as inactive (completed while scoped).

    Auto-clears scope when the last active task completes, so completed
    tasks don't show stale indicators in the tree.

    Returns:
        Dict with 'task_id', 'transitioned_to' ('inactive'), 'remaining_active' (int),
        'auto_cleared' (bool), 'success' (bool).
    """
    # Get current state to compute remaining
    scope = get_scope_state()
    remaining = sum(1 for tid, s in scope.items() if s == "active" and tid != str(task_id))

    result = {
        "task_id": str(task_id),
        "transitioned_to": "inactive",
        "remaining_active": remaining,
        "auto_cleared": False,
        "success": False,
    }

    success = append_event(
        event="scope_task_completed",
        data={
            "task_id": str(task_id),
            "remaining_active": remaining,
            "session_id": session_id,
        },
    )
    result["success"] = success

    # Auto-clear scope when last active task completes
    if success and remaining == 0:
        clear_result = clear_scope(session_id=session_id)
        result["auto_cleared"] = clear_result.get("success", False)

    return result


def clear_scope(session_id: str = "") -> dict:
    """Remove all tasks from scope.

    Returns:
        Dict with 'active_removed' (list of IDs), 'inactive_removed' (list of IDs),
        'success' (bool).
    """
    scope = get_scope_state()
    active = [tid for tid, s in scope.items() if s == "active"]
    inactive = [tid for tid, s in scope.items() if s == "inactive"]

    result = {
        "active_removed": active,
        "inactive_removed": inactive,
        "success": False,
    }

    success = append_event(
        event="scope_cleared",
        data={
            "active_removed": len(active),
            "inactive_removed": len(inactive),
            "session_id": session_id,
        },
    )
    result["success"] = success
    return result


def get_scope_state() -> Dict[str, str]:
    """Reconstruct current scope state from event log.

    Scans events in reverse chronological order:
    - scope_cleared resets everything
    - scope_activated adds tasks as 'active'
    - scope_task_completed transitions task to 'inactive'

    Returns:
        Dict of {task_id: 'active' | 'inactive'}
    """
    # Read all events and filter for scope-related ones
    scope_types = {"scope_activated", "scope_task_completed", "scope_cleared"}
    events = [e for e in read_events(limit=None, reverse=False)
              if e.get("event", "") in scope_types]

    state: Dict[str, str] = {}

    for event in events:
        event_type = event.get("event", "")
        data = event.get("data", {})

        if event_type == "scope_cleared":
            state.clear()
        elif event_type == "scope_activated":
            for tid in data.get("task_ids", []):
                state[str(tid)] = "active"
        elif event_type == "scope_task_completed":
            tid = str(data.get("task_id", ""))
            if tid in state:
                state[tid] = "inactive"

    return state


def get_active_scope() -> List[Dict]:
    """Get all scoped tasks with their subjects and status.

    Returns:
        List of dicts: {'id', 'status' ('active'/'inactive'), 'subject'}
    """
    from .reader import TaskReader

    scope = get_scope_state()
    if not scope:
        return []

    reader = TaskReader()
    result = []
    for tid, status in scope.items():
        task = reader.read_task(tid)
        subject = task.subject if task else f"Task #{tid}"
        result.append({"id": tid, "status": status, "subject": subject})

    return result


def get_scope_check() -> dict:
    """Structured scope check for Stop hook and JSON output.

    Returns:
        Dict with 'active' (list), 'inactive' (list), 'active_count', 'inactive_count', 'total'.
    """
    tasks = get_active_scope()
    active = [t for t in tasks if t["status"] == "active"]
    inactive = [t for t in tasks if t["status"] == "inactive"]
    return {
        "active": active,
        "inactive": inactive,
        "active_count": len(active),
        "inactive_count": len(inactive),
        "total": len(tasks),
    }
