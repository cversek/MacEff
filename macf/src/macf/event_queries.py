"""
Event Query Utilities - Reconstruct state from JSONL event log.

Functions for querying the append-only event log to extract statistics
and state without relying on mutable state files. Provides forensic data
that survives state file synchronization issues.

These functions replace reads from mutable session_state.json with
event-sourced queries from agent_events_log.jsonl.
"""

from typing import Tuple, Dict, List, Optional
from .agent_events_log import read_events


def get_latest_state_snapshot() -> Optional[dict]:
    """
    Find most recent state_snapshot event.

    State snapshots capture accumulated values as immutable baseline for
    event-first queries. Query functions use: baseline + incremental = accurate total.

    Returns:
        Most recent state_snapshot event dict, or None if no snapshots exist

    Example:
        >>> snapshot = get_latest_state_snapshot()
        >>> if snapshot:
        ...     baseline = snapshot["data"]["event_tallies"].get("dev_drv_ended", 0)
    """
    for event in read_events(limit=100, reverse=True):
        if event.get("event") == "state_snapshot":
            return event
    return None


def get_dev_drv_stats_from_events(session_id: str) -> dict:
    """
    Query dev_drv_started/ended events, return stats with snapshot baseline.

    Uses snapshot baseline + incremental events after snapshot = accurate total.
    This preserves historical data from before event logging began.

    Args:
        session_id: Session ID to filter events (uses first 8 chars for matching)

    Returns:
        Dictionary with keys:
        - count: Number of completed DEV_DRVs (int)
        - total_duration: Sum of all completed drive durations (float)
        - current_prompt_uuid: UUID of in-progress drive or most recent ended (str|None)
        - from_snapshot: Whether baseline came from snapshot (bool)
    """
    # Get snapshot baseline
    snapshot = get_latest_state_snapshot()
    snapshot_timestamp = snapshot.get("timestamp", 0) if snapshot else 0

    # Baseline from snapshot
    baseline_count = 0
    baseline_duration = 0.0
    from_snapshot = False

    if snapshot:
        snapshot_data = snapshot.get("data", {})
        # Try derived_values first (from state files)
        derived = snapshot_data.get("derived_values", {})
        if "completed_dev_drvs" in derived:
            baseline_count = derived["completed_dev_drvs"]
            from_snapshot = True
        else:
            # Fallback to event_tallies
            tallies = snapshot_data.get("event_tallies", {})
            baseline_count = tallies.get("dev_drv_ended", 0)
            from_snapshot = True

        # Duration from accumulated_durations
        durations = snapshot_data.get("accumulated_durations", {})
        baseline_duration = durations.get("total_dev_drv_duration_seconds", 0.0)

    # Collect incremental events AFTER snapshot (reverse scan, stop at snapshot)
    incremental_events = []
    session_prefix = session_id[:8] if session_id else ""

    for event in read_events(limit=None, reverse=True):
        event_timestamp = event.get("timestamp", 0)
        # Stop when we reach snapshot timestamp (efficient for long logs)
        if snapshot_timestamp > 0 and event_timestamp <= snapshot_timestamp:
            break

        event_type = event.get("event")
        if event_type not in ("dev_drv_started", "dev_drv_ended"):
            continue

        data = event.get("data", {})
        event_session = data.get("session_id", "")
        if session_prefix and event_session and not event_session.startswith(session_prefix):
            continue

        incremental_events.append(event)

    # Process in chronological order (reverse the reversed list)
    count = baseline_count
    total_duration = baseline_duration
    current_prompt_uuid = None
    started_prompts = {}

    for event in reversed(incremental_events):
        event_type = event.get("event")
        data = event.get("data", {})

        if event_type == "dev_drv_started":
            prompt_uuid = data.get("prompt_uuid")
            if prompt_uuid:
                started_prompts[prompt_uuid] = True
                current_prompt_uuid = prompt_uuid

        elif event_type == "dev_drv_ended":
            prompt_uuid = data.get("prompt_uuid")
            duration = data.get("duration", 0.0)

            if prompt_uuid and prompt_uuid in started_prompts:
                count += 1
                total_duration += duration
                current_prompt_uuid = prompt_uuid
                del started_prompts[prompt_uuid]

    return {
        "count": count,
        "total_duration": total_duration,
        "current_prompt_uuid": current_prompt_uuid,
        "from_snapshot": from_snapshot
    }


def get_deleg_drv_stats_from_events(session_id: str) -> dict:
    """
    Query delegation_started/completed events, return stats.

    Counts delegations and tracks subagent types used.

    Args:
        session_id: Session ID to filter events (uses first 8 chars for matching)

    Returns:
        Dictionary with keys:
        - count: Number of completed delegations (int)
        - total_duration: Sum of all delegation durations (float)
        - subagent_types: List of subagent types (one per delegation, not deduplicated)
    """
    count = 0
    total_duration = 0.0
    subagent_types = []

    # Use first 8 chars of session_id for matching
    session_prefix = session_id[:8] if session_id else ""

    # Track started delegations to match with ended events
    started_delegations = {}  # key: subagent_type, value: timestamp

    # Read events in chronological order
    for event in read_events(limit=None, reverse=False):
        event_type = event.get("event")
        data = event.get("data", {})
        event_session = data.get("session_id", "")

        # Session isolation
        if session_prefix and event_session and not event_session.startswith(session_prefix):
            continue

        if event_type == "deleg_drv_started":
            subagent_type = data.get("subagent_type")
            timestamp = data.get("timestamp", 0.0)
            if subagent_type:
                # Use timestamp as unique key to handle multiple delegations to same type
                key = f"{subagent_type}_{timestamp}"
                started_delegations[key] = subagent_type

        elif event_type == "deleg_drv_ended":
            subagent_type = data.get("subagent_type")
            duration = data.get("duration", 0.0)

            # Match with most recent started delegation of this type
            if subagent_type:
                # Find matching started delegation
                matching_key = None
                for key, started_type in started_delegations.items():
                    if started_type == subagent_type:
                        matching_key = key
                        break

                if matching_key:
                    count += 1
                    total_duration += duration
                    subagent_types.append(subagent_type)
                    del started_delegations[matching_key]

    return {
        "count": count,
        "total_duration": total_duration,
        "subagent_types": subagent_types
    }


def get_cycle_number_from_events() -> int:
    """
    Get cycle number from most recent session_started event.

    Returns:
        Current cycle number (0 if no events found)
    """
    # Read most recent events first
    for event in read_events(limit=100, reverse=True):
        if event.get("event") == "session_started":
            data = event.get("data", {})
            cycle = data.get("cycle")
            if cycle is not None:
                return cycle

    # Default if no session_started events found
    return 0


def get_compaction_count_from_events(session_id: str) -> dict:
    """
    Count compaction_detected events with snapshot baseline.

    Uses reverse scan, stopping at snapshot timestamp for efficiency.

    Args:
        session_id: Session ID to filter events (uses first 8 chars for matching)

    Returns:
        Dictionary with keys:
        - count: Number of compactions detected (int)
        - from_snapshot: Whether baseline came from snapshot (bool)
    """
    snapshot = get_latest_state_snapshot()
    snapshot_timestamp = snapshot.get("timestamp", 0) if snapshot else 0

    baseline_count = 0
    from_snapshot = False

    if snapshot:
        tallies = snapshot.get("data", {}).get("event_tallies", {})
        baseline_count = tallies.get("compaction_detected", 0)
        from_snapshot = True

    # Count incremental events after snapshot (reverse scan, stop at snapshot)
    count = baseline_count
    session_prefix = session_id[:8] if session_id else ""

    for event in read_events(limit=None, reverse=True):
        event_timestamp = event.get("timestamp", 0)
        if snapshot_timestamp > 0 and event_timestamp <= snapshot_timestamp:
            break

        if event.get("event") == "compaction_detected":
            data = event.get("data", {})
            event_session = data.get("session_id", "")

            if session_prefix and event_session and not event_session.startswith(session_prefix):
                continue

            count += 1

    return {"count": count, "from_snapshot": from_snapshot}


def get_delegations_this_drive_from_events(session_id: str) -> List[Dict]:
    """
    Get list of delegations that occurred during the current DEV_DRV.

    Reconstructs the delegations_this_drive list from deleg_drv_started/ended events
    that occurred after the most recent dev_drv_started event.

    Args:
        session_id: Session ID to filter events (uses first 8 chars for matching)

    Returns:
        List of delegation dicts with keys:
        - subagent_type: Type of subagent (e.g., "devops-eng", "test-eng")
        - started_at: Timestamp when delegation started
        - duration: Duration in seconds (if completed, else None)
        - completed: Whether delegation finished
    """
    delegations = []
    last_dev_drv_start_time = 0.0

    # Use first 8 chars of session_id for matching
    session_prefix = session_id[:8] if session_id else ""

    # First pass: find most recent dev_drv_started timestamp
    for event in read_events(limit=None, reverse=False):
        event_type = event.get("event")
        data = event.get("data", {})
        event_session = data.get("session_id", "")

        # Session isolation
        if session_prefix and event_session and not event_session.startswith(session_prefix):
            continue

        if event_type == "dev_drv_started":
            timestamp = data.get("timestamp", 0.0)
            if timestamp > last_dev_drv_start_time:
                last_dev_drv_start_time = timestamp
                delegations = []  # Reset - new DEV_DRV started

        elif event_type == "deleg_drv_started" and last_dev_drv_start_time > 0:
            timestamp = data.get("timestamp", 0.0)
            if timestamp >= last_dev_drv_start_time:
                delegations.append({
                    "subagent_type": data.get("subagent_type", "unknown"),
                    "started_at": timestamp,
                    "duration": None,
                    "completed": False
                })

        elif event_type == "deleg_drv_ended" and delegations:
            subagent_type = data.get("subagent_type")
            duration = data.get("duration", 0.0)

            # Find matching uncompleted delegation
            for deleg in reversed(delegations):
                if deleg["subagent_type"] == subagent_type and not deleg["completed"]:
                    deleg["duration"] = duration
                    deleg["completed"] = True
                    break

    return delegations


def get_last_session_id_from_events() -> str:
    """
    Get the previous session ID from most recent migration_detected event.

    This is used for session migration recovery - finding the session that
    was active before the current one started.

    Returns:
        Previous session ID string, or empty string if no migration detected
    """
    # Read most recent events first
    for event in read_events(limit=100, reverse=True):
        if event.get("event") == "migration_detected":
            data = event.get("data", {})
            previous_session = data.get("previous_session", "")
            if previous_session:
                return previous_session

    # Fallback: check session_started events for session_id continuity
    # (older events might have previous session info)
    return ""


def get_last_session_end_time_from_events() -> Optional[float]:
    """
    Get timestamp of most recent session_ended event.

    Used to determine when the previous session ended, useful for
    calculating session gaps and recovery timing.

    Returns:
        Unix timestamp of last session end, or None if no session_ended events
    """
    # Read most recent events first
    for event in read_events(limit=100, reverse=True):
        if event.get("event") == "session_ended":
            data = event.get("data", {})
            timestamp = data.get("timestamp")
            if timestamp:
                return float(timestamp)

    return None


def get_auto_mode_from_events(session_id: str) -> Tuple[bool, str, float]:
    """
    Get auto_mode setting from most recent auto_mode_detected event.

    Searches for most recent auto_mode_detected event for the specified session.
    Higher priority sources (env_var) override lower priority (config).

    Args:
        session_id: Session ID to filter events (uses first 8 chars for matching)

    Returns:
        Tuple of (auto_mode: bool, source: str, confidence: float)
        Default: (False, "default", 0.0)
    """
    # Use first 8 chars of session_id for matching
    session_prefix = session_id[:8] if session_id else ""

    # Track highest priority detection
    best_auto_mode = False
    best_source = "default"
    best_confidence = 0.0

    # Priority order: env_var > config > default
    priority_order = {
        "env_var": 3,
        "config": 2,
        "session": 1,
        "default": 0
    }

    # Read most recent events first
    for event in read_events(limit=100, reverse=True):
        if event.get("event") == "auto_mode_detected":
            data = event.get("data", {})
            event_session = data.get("session_id", "")

            # Session isolation
            if session_prefix and event_session and not event_session.startswith(session_prefix):
                continue

            auto_mode = data.get("auto_mode", False)
            source = data.get("source", "default")
            confidence = data.get("confidence", 0.0)

            # Check if this source has higher priority
            current_priority = priority_order.get(source, 0)
            best_priority = priority_order.get(best_source, 0)

            if current_priority > best_priority:
                best_auto_mode = auto_mode
                best_source = source
                best_confidence = confidence
            elif current_priority == best_priority and best_source == "default":
                # First detection found (reading in reverse)
                best_auto_mode = auto_mode
                best_source = source
                best_confidence = confidence

    return (best_auto_mode, best_source, best_confidence)
