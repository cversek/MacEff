"""
Task scope management for AUTO_MODE boundary enforcement.

Scope tracks which tasks are actively being worked on, enabling the Stop hook
to block premature stopping when scoped tasks remain incomplete.

Dual persistence:
  - MTMD scope_status field on task files: drives display + loop mode detection
  - Event log (agent_events_log.jsonl): permanent history + real-time signaling

Scope lifecycle:
  scope_activated → tasks get scope_status="active" in MTMD
  scope_task_completed → individual task gets scope_status="inactive"
  scope_cleared → all scoped tasks get scope_status=None (removed)
  auto-clear → when last active task completes, entire scope clears

API follows the Full Disclosure Principle (cli_development.md §9):
  Functions return WHAT CHANGED, not just success/failure.
  The CLI caller prints each individual change.
"""

from typing import Dict, List, Optional
from ..agent_events_log import append_event, read_events


def _update_task_scope_status(task_id: str, scope_status: Optional[str]) -> bool:
    """Update a task's MTMD scope_status field.

    Args:
        task_id: Task ID to update
        scope_status: "active", "inactive", or None (clear)

    Returns:
        True if successful
    """
    import copy
    from .reader import TaskReader, update_task_file

    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task or not task.mtmd:
        return False

    new_mtmd = copy.deepcopy(task.mtmd)
    new_mtmd.scope_status = scope_status
    new_description = task.description_with_updated_mtmd(new_mtmd)
    return update_task_file(task_id, {"description": new_description})


def set_scope(task_ids: List[str], parent_expanded: bool = False,
              expanded_from: Optional[str] = None, session_id: str = "") -> dict:
    """Activate scope for a set of task IDs.

    Updates MTMD scope_status to "active" on each task file.

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

    # Event for history
    success = append_event(
        event="scope_activated",
        data={
            "task_ids": list(task_ids),
            "parent_expansion": parent_expanded,
            "expanded_from": expanded_from,
            "session_id": session_id,
        },
    )

    # Update MTMD on each task file (drives display + loop detection)
    if success:
        for tid in task_ids:
            _update_task_scope_status(str(tid), "active")

    result["success"] = success
    return result


def complete_scoped_task(task_id: str, session_id: str = "") -> dict:
    """Mark a scoped task as inactive (completed while scoped).

    Updates MTMD scope_status to "inactive". Auto-clears entire scope
    when the last active task completes.

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

    # Event for history
    success = append_event(
        event="scope_task_completed",
        data={
            "task_id": str(task_id),
            "remaining_active": remaining,
            "session_id": session_id,
        },
    )
    result["success"] = success

    if success:
        # Update MTMD on this task
        _update_task_scope_status(str(task_id), "inactive")

        # Auto-clear scope when last active task completes
        if remaining == 0:
            clear_result = clear_scope(session_id=session_id)
            result["auto_cleared"] = clear_result.get("success", False)

    return result


def clear_scope(session_id: str = "") -> dict:
    """Remove all tasks from scope.

    Sets MTMD scope_status to None on all scoped tasks.

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

    # Event for history
    success = append_event(
        event="scope_cleared",
        data={
            "active_removed": len(active),
            "inactive_removed": len(inactive),
            "session_id": session_id,
        },
    )

    # Clear MTMD scope_status on all scoped tasks
    if success:
        for tid in active + inactive:
            _update_task_scope_status(str(tid), None)

    result["success"] = success
    return result


def get_scope_state() -> Dict[str, str]:
    """Reconstruct current scope state from event log.

    Scans events in chronological order:
    - scope_cleared resets everything
    - scope_activated adds tasks as 'active'
    - scope_task_completed transitions task to 'inactive'

    Returns:
        Dict of {task_id: 'active' | 'inactive'}
    """
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


def get_active_timer() -> dict:
    """Check for an active (unexpired) scope timer.

    Returns:
        Dict with 'active' (bool), 'remaining_sec' (float), 'remaining_min' (int),
        'timer_end_epoch' (float), or {'active': False} if no timer.
    """
    import time
    for event in read_events(limit=None, reverse=True):
        if event.get("event") == "scope_timer_set":
            timer_end = event.get("data", {}).get("timer_end_epoch", 0)
            remaining = timer_end - time.time()
            if remaining > 0:
                return {
                    "active": True,
                    "remaining_sec": remaining,
                    "remaining_min": int(remaining / 60),
                    "timer_end_epoch": timer_end,
                }
            return {"active": False}
        elif event.get("event") == "scope_cleared":
            return {"active": False}
    return {"active": False}


def is_task_timer_blocked(task_id: str) -> dict:
    """Check if a task is blocked from completion by an active timer.

    A scoped task cannot be completed while a scope timer is active.

    Returns:
        Dict with 'blocked' (bool), 'remaining_min' (int), 'reason' (str).
    """
    scope = get_scope_state()
    if str(task_id) not in scope:
        return {"blocked": False, "remaining_min": 0, "reason": ""}

    timer = get_active_timer()
    if not timer.get("active"):
        return {"blocked": False, "remaining_min": 0, "reason": ""}

    return {
        "blocked": True,
        "remaining_min": timer["remaining_min"],
        "reason": (
            f"Cannot complete timer-scoped task — {timer['remaining_min']} min remaining. "
            f"Document progress in task notes. Timer gate lifts at expiry."
        ),
    }


def get_scope_check() -> dict:
    """Structured scope check for Stop hook and JSON output.

    Returns:
        Dict with 'active' (list), 'inactive' (list), 'active_count', 'inactive_count',
        'total', 'timer' (active timer info).
    """
    tasks = get_active_scope()
    active = [t for t in tasks if t["status"] == "active"]
    inactive = [t for t in tasks if t["status"] == "inactive"]
    timer = get_active_timer()
    return {
        "active": active,
        "inactive": inactive,
        "active_count": len(active),
        "inactive_count": len(inactive),
        "total": len(tasks),
        "timer": timer,
    }
