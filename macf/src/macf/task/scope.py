"""
Task scope management for AUTO_MODE boundary enforcement.

Scope tracks which tasks are actively being worked on, enabling the Stop hook
to block premature stopping when scoped tasks remain incomplete.

Dual persistence:
  - MTMD scope_status field on task files: drives display + loop mode detection
  - Event log (agent_events_log.jsonl): permanent history + real-time signaling

Scope lifecycle (3-state model — extended from 2-state Cycle 514):
  scope_activated → tasks get scope_status="active" in MTMD
  scope_task_completed → individual task gets scope_status="inactive"
  scope_cleared → all scoped tasks get scope_status=None (removed)
  scope_paused → task transitions "active" → "paused" with justification (BUG #1067)
  scope_unpaused → task transitions "paused" → "active"
  scope_added → incrementally add tasks as "active" (no replace; BUG #1067)
  scope_removed → incrementally remove specific tasks from scope (BUG #1067)
  auto-clear → when last active task completes, entire scope clears

Gate semantics: gate blocks Stop when active_count > 0. Paused tasks remain
in scope (visible in `scope show` with ⏸️ marker, audited via task notes) but
do NOT count toward the gate. This allows the agent to satisfy the gate by
explicitly pausing genuinely-cycle-spanning items with justification, instead
of either force-completing or idle-looping.

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

    Scans events in chronological order. 3-state model (BUG #1067):

    - scope_cleared resets everything
    - scope_activated / scope_added adds tasks as 'active'
    - scope_task_completed transitions task to 'inactive'
    - scope_paused transitions task to 'paused'
    - scope_unpaused transitions paused task back to 'active'
    - scope_removed drops tasks entirely

    Returns:
        Dict of {task_id: 'active' | 'paused' | 'inactive'}
    """
    scope_types = {
        "scope_activated", "scope_task_completed", "scope_cleared",
        "scope_paused", "scope_unpaused", "scope_added", "scope_removed",
    }
    events = [e for e in read_events(limit=None, reverse=False)
              if e.get("event", "") in scope_types]

    state: Dict[str, str] = {}

    for event in events:
        event_type = event.get("event", "")
        data = event.get("data", {})

        if event_type == "scope_cleared":
            state.clear()
        elif event_type == "scope_activated":
            # Replace semantics: scope_activated also resets prior set
            # (current behavior — set_scope is replace-style via scope set CLI)
            # We do NOT clear here because scope set's clear is separate; the
            # CLI orchestrates clear+activate. So scope_activated is purely additive.
            for tid in data.get("task_ids", []):
                state[str(tid)] = "active"
        elif event_type == "scope_added":
            for tid in data.get("task_ids", []):
                # Only add if not already present (don't reset paused→active)
                if str(tid) not in state:
                    state[str(tid)] = "active"
        elif event_type == "scope_removed":
            for tid in data.get("task_ids", []):
                state.pop(str(tid), None)
        elif event_type == "scope_task_completed":
            tid = str(data.get("task_id", ""))
            if tid in state:
                state[tid] = "inactive"
        elif event_type == "scope_paused":
            for tid in data.get("task_ids", []):
                if str(tid) in state and state[str(tid)] == "active":
                    state[str(tid)] = "paused"
        elif event_type == "scope_unpaused":
            for tid in data.get("task_ids", []):
                if str(tid) in state and state[str(tid)] == "paused":
                    state[str(tid)] = "active"

    return state


def pause_scoped_tasks(task_ids: List[str], justification: str, session_id: str = "") -> dict:
    """Pause one or more active scoped tasks with mandatory justification.

    Paused tasks remain in scope (visible in `scope show` with ⏸️ marker)
    but do NOT count toward the Stop hook gate. This is the structural
    'I'm not idle-looping; this task is paused for reason X' exit path.

    Args:
        task_ids: list of task IDs to pause
        justification: REQUIRED — recorded in event log AND in task note
        session_id: current session

    Returns:
        Dict with 'paused_ids' (list, those that transitioned), 'skipped_ids'
        (list with reasons), 'success' (bool).
    """
    result = {"paused_ids": [], "skipped_ids": [], "success": False}

    if not justification or not justification.strip():
        result["skipped_ids"] = [{"id": tid, "reason": "missing_justification"} for tid in task_ids]
        return result

    scope = get_scope_state()
    pausable: List[str] = []
    for tid in task_ids:
        sid = str(tid)
        if sid not in scope:
            result["skipped_ids"].append({"id": sid, "reason": "not_in_scope"})
            continue
        if scope[sid] == "paused":
            result["skipped_ids"].append({"id": sid, "reason": "already_paused"})
            continue
        if scope[sid] == "inactive":
            result["skipped_ids"].append({"id": sid, "reason": "already_completed"})
            continue
        pausable.append(sid)

    if not pausable:
        return result

    success = append_event(
        event="scope_paused",
        data={
            "task_ids": pausable,
            "justification": justification,
            "session_id": session_id,
        },
    )

    if success:
        from .reader import add_task_note
        for tid in pausable:
            _update_task_scope_status(tid, "paused")
            # Also append a task note for human audit (best-effort)
            add_task_note(tid, f"⏸️ SCOPE PAUSED: {justification}")
        result["paused_ids"] = pausable

    result["success"] = success
    return result


def unpause_scoped_tasks(task_ids: List[str], session_id: str = "") -> dict:
    """Unpause one or more paused scoped tasks (restore to active).

    Args:
        task_ids: list of task IDs to unpause
        session_id: current session

    Returns:
        Dict with 'unpaused_ids', 'skipped_ids', 'success'.
    """
    result = {"unpaused_ids": [], "skipped_ids": [], "success": False}
    scope = get_scope_state()
    unpausable: List[str] = []
    for tid in task_ids:
        sid = str(tid)
        if sid not in scope:
            result["skipped_ids"].append({"id": sid, "reason": "not_in_scope"})
            continue
        if scope[sid] != "paused":
            result["skipped_ids"].append({"id": sid, "reason": f"not_paused (current: {scope[sid]})"})
            continue
        unpausable.append(sid)

    if not unpausable:
        return result

    success = append_event(
        event="scope_unpaused",
        data={"task_ids": unpausable, "session_id": session_id},
    )

    if success:
        from .reader import add_task_note
        for tid in unpausable:
            _update_task_scope_status(tid, "active")
            add_task_note(tid, f"▶️ SCOPE UNPAUSED — task restored to active scope")
        result["unpaused_ids"] = unpausable

    result["success"] = success
    return result


def add_to_scope(task_ids: List[str], session_id: str = "") -> dict:
    """Incrementally add tasks to scope as active (no replace).

    Distinct from `set_scope` which replaces the entire scope. `add_to_scope`
    appends without affecting existing scoped tasks. Useful when a new BUG
    surfaces mid-sprint and should be tracked.

    Args:
        task_ids: list of task IDs to add
        session_id: current session

    Returns:
        Dict with 'added_ids', 'skipped_ids' (already in scope), 'success'.
    """
    result = {"added_ids": [], "skipped_ids": [], "success": False}
    scope = get_scope_state()
    addable: List[str] = []
    for tid in task_ids:
        sid = str(tid)
        if sid in scope:
            result["skipped_ids"].append({"id": sid, "reason": f"already_in_scope ({scope[sid]})"})
            continue
        addable.append(sid)

    if not addable:
        return result

    success = append_event(
        event="scope_added",
        data={"task_ids": addable, "session_id": session_id},
    )

    if success:
        for tid in addable:
            _update_task_scope_status(tid, "active")
        result["added_ids"] = addable

    result["success"] = success
    return result


def remove_from_scope(task_ids: List[str], session_id: str = "") -> dict:
    """Incrementally remove tasks from scope (no completion).

    Distinct from `complete_scoped_task` (which marks 'inactive') and
    `pause_scoped_tasks` (which marks 'paused' with justification).
    `remove_from_scope` drops the tasks entirely — they leave scope without
    status transition. Useful for correcting accidental scope additions.

    Args:
        task_ids: list of task IDs to remove
        session_id: current session

    Returns:
        Dict with 'removed_ids', 'skipped_ids' (not in scope), 'success'.
    """
    result = {"removed_ids": [], "skipped_ids": [], "success": False}
    scope = get_scope_state()
    removable: List[str] = []
    for tid in task_ids:
        sid = str(tid)
        if sid not in scope:
            result["skipped_ids"].append({"id": sid, "reason": "not_in_scope"})
            continue
        removable.append(sid)

    if not removable:
        return result

    success = append_event(
        event="scope_removed",
        data={"task_ids": removable, "session_id": session_id},
    )

    if success:
        for tid in removable:
            _update_task_scope_status(tid, None)
        result["removed_ids"] = removable

    result["success"] = success
    return result


def get_active_scope() -> List[Dict]:
    """Get all scoped tasks with their subjects and status.

    Returns:
        List of dicts: {'id', 'status' ('active'/'paused'/'inactive'), 'subject'}
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
        elif event.get("event") in ("scope_cleared", "scope_timer_cleared"):
            # scope_cleared: full scope reset (also kills timer)
            # scope_timer_cleared: targeted timer-only clear (scope set retained)
            return {"active": False}
    return {"active": False}


def is_task_timer_blocked(task_id: str) -> dict:
    """Check if a task is blocked from completion by an active timer.

    Only the LAST active scoped task is blocked by the timer. Earlier tasks
    can be completed freely — this clears scope incrementally and feeds the
    Markov recommender at each gate point via the Stop hook.

    Returns:
        Dict with 'blocked' (bool), 'remaining_min' (int), 'reason' (str).
    """
    scope = get_scope_state()
    if str(task_id) not in scope:
        return {"blocked": False, "remaining_min": 0, "reason": ""}

    timer = get_active_timer()
    if not timer.get("active"):
        return {"blocked": False, "remaining_min": 0, "reason": ""}

    # Count active scoped tasks (not yet completed)
    check = get_scope_check()
    active_count = check["active_count"]

    # Only block the LAST active scoped task — allow earlier completions
    if active_count > 1:
        return {"blocked": False, "remaining_min": 0, "reason": ""}

    return {
        "blocked": True,
        "remaining_min": timer["remaining_min"],
        "reason": (
            f"Last scoped task — timer gate active with {timer['remaining_min']} min remaining. "
            f"Document progress in task notes. Timer gate lifts at expiry."
        ),
    }


def get_scope_check() -> dict:
    """Structured scope check for Stop hook and JSON output.

    Returns:
        Dict with 'active' (list), 'paused' (list), 'inactive' (list),
        'active_count', 'paused_count', 'inactive_count', 'total',
        'timer' (active timer info).

    Gate semantics: only 'active_count' blocks the Stop gate. Paused tasks
    remain in scope (audit trail) but are explicitly excluded from gate.
    """
    tasks = get_active_scope()
    active = [t for t in tasks if t["status"] == "active"]
    paused = [t for t in tasks if t["status"] == "paused"]
    inactive = [t for t in tasks if t["status"] == "inactive"]
    timer = get_active_timer()
    return {
        "active": active,
        "paused": paused,
        "inactive": inactive,
        "active_count": len(active),
        "paused_count": len(paused),
        "inactive_count": len(inactive),
        "total": len(tasks),
        "timer": timer,
    }
