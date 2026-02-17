"""
Task lifecycle event schemas and queries.

Defines canonical schemas for task events and provides query functions
for reconstructing task state from the immutable event log.

NOTE: Task events are currently constructed manually in cli.py (lines ~4349, ~4807).
Future refactor should use these schemas as the single source of truth for
event construction, replacing inline dict literals with schema-based builders.
"""
import sys
from typing import Dict, List, Optional, TypedDict


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
    """Schema for 'task_paused' event data. Emitted by cmd_task_pause."""
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


def get_active_tasks_from_filesystem() -> Dict[str, str]:
    """
    Get all in_progress tasks by reading task JSON files from disk.

    Filesystem-based complement to get_active_tasks_from_events().
    Reads task files directly, extracts task_type from MTMD metadata.
    Useful for recovery scenarios where event log may be incomplete
    (e.g., sentinel task #000 created before event emission existed,
    or after compaction clears event history).

    Returns:
        Dict of {task_id: task_type} for tasks with status "in_progress".
    """
    from .reader import TaskReader
    from .protection import get_task_type

    active: Dict[str, str] = {}
    try:
        reader = TaskReader()
        for task in reader.read_all_tasks():
            if task.status == "in_progress":
                # Extract task_type: MTMD is authoritative, subject emoji is fallback
                task_type = None
                if task.mtmd and task.mtmd.task_type:
                    task_type = task.mtmd.task_type
                else:
                    task_type = get_task_type(task.description or "", task.subject or "")
                if task_type:
                    active[task.id] = task_type
    except (FileNotFoundError, OSError) as e:
        print(f"⚠️ MACF: Filesystem task scan failed: {e}", file=sys.stderr)

    return active


def emit_task_started_for_recovery(active_tasks: Dict[str, str], source: str = "compaction_recovery") -> List[str]:
    """
    Re-emit task_started events for in_progress tasks after compaction boundary.

    Without this, get_active_tasks_from_events() cannot see pre-compaction
    task_started events (they're behind the compaction_detected boundary).

    Args:
        active_tasks: Dict of {task_id: task_type} from pre-boundary scan
        source: Provenance marker for the re-emitted events

    Returns:
        List of task_ids for which events were emitted
    """
    from ..agent_events_log import append_event

    emitted = []
    for task_id, task_type in active_tasks.items():
        event_data: TaskStartedData = {
            "task_id": str(task_id),
            "task_type": task_type,
            "breadcrumb": "",
            "plan_ca_ref": "",
        }
        # Add provenance outside schema — source marks this as recovery, not original
        append_event(TASK_STARTED, {**event_data, "source": source})
        emitted.append(str(task_id))
        print(f"[task:recovery] Re-emitted task_started for #{task_id} ({task_type})", file=sys.stderr)

    return emitted
