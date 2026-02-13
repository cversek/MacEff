"""
Task lifecycle event schemas and queries.

Defines canonical schemas for task events and provides query functions
for reconstructing task state from the immutable event log.

NOTE: Task events are currently constructed manually in cli.py (lines ~4349, ~4807).
Future refactor should use these schemas as the single source of truth for
event construction, replacing inline dict literals with schema-based builders.
"""
from typing import Dict, Optional, TypedDict


# --- Event Schemas ---

class TaskStartedData(TypedDict):
    """Schema for 'task_started' event data."""
    task_id: str
    task_type: str
    breadcrumb: str
    plan_ca_ref: str


class TaskCompletedData(TypedDict):
    """Schema for 'task_completed' event data."""
    task_id: str
    task_type: str
    breadcrumb: str
    plan_ca_ref: str
    report: Optional[str]


class TaskPausedData(TypedDict):
    """Schema for 'task_paused' event data. Not yet emitted by CLI."""
    task_id: str
    task_type: str
    breadcrumb: str


# Event type constants
TASK_STARTED = "task_started"
TASK_COMPLETED = "task_completed"
TASK_PAUSED = "task_paused"

TASK_LIFECYCLE_EVENTS = {TASK_STARTED, TASK_COMPLETED, TASK_PAUSED}


# --- Queries ---

def get_active_tasks_from_events() -> Dict[str, str]:
    """
    Get all in_progress tasks from event log via canonical reverse scan.

    Uses first-event-wins deduplication: scans in reverse, first lifecycle
    event encountered for each task_id determines its current state.

    Returns:
        Dict of {task_id: task_type} for tasks whose most recent event
        is task_started (not task_completed or task_paused).
    """
    from ..agent_events_log import read_events

    task_final_states: Dict[str, Dict[str, str]] = {}

    for event in read_events(limit=None, reverse=True):
        event_type = event.get("event")
        data = event.get("data", {})

        # Early exit on compaction boundary
        if event_type == "compaction_detected":
            break

        task_id = data.get("task_id")
        if not task_id:
            continue

        # First-event-wins deduplication
        if task_id in task_final_states:
            continue

        if event_type == TASK_STARTED:
            task_final_states[task_id] = {
                "state": "active",
                "task_type": data.get("task_type", "")
            }
        elif event_type in (TASK_COMPLETED, TASK_PAUSED):
            task_final_states[task_id] = {
                "state": "ended",
                "task_type": data.get("task_type", "")
            }

    return {
        tid: state["task_type"]
        for tid, state in task_final_states.items()
        if state["state"] == "active" and state["task_type"]
    }
