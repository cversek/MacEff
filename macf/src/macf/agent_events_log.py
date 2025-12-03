"""
Agent Events Log - Forensic event sourcing for TODO recovery intelligence.

Event sourcing infrastructure with JSONL append-only log supporting:
- Atomic event appends with breadcrumb generation
- Forensic queries by breadcrumb components (session, cycle, git, prompt, timestamp)
- Set operations (union, intersection, subtraction)
- State reconstruction from events (slow-field tracking)

File: .maceff/agent_events_log.jsonl
Format: JSONL (one JSON object per line)
Schema: {timestamp, event, breadcrumb, data, hook_input}
"""

import fcntl
import json
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from .utils import (
    find_project_root,
    get_breadcrumb,
    parse_breadcrumb,
)


# Global log path override for testing
_TEST_LOG_PATH: Optional[Path] = None


def set_log_path(path: Optional[Path]) -> None:
    """
    Set custom log path for testing.

    Args:
        path: Path to use (None to reset to default)
    """
    global _TEST_LOG_PATH
    _TEST_LOG_PATH = path


def _get_log_path() -> Path:
    """
    Get path to agent events log file.

    Returns:
        Path to .maceff/agent_events_log.jsonl or test override
    """
    # Check for test override first
    if _TEST_LOG_PATH is not None:
        return _TEST_LOG_PATH

    # Check for environment variable override (for CLI testing)
    import os
    env_path = os.getenv("MACF_EVENTS_LOG_PATH")
    if env_path:
        return Path(env_path)

    try:
        project_root = find_project_root()
        maceff_dir = project_root / ".maceff"
        maceff_dir.mkdir(mode=0o700, exist_ok=True)
        return maceff_dir / "agent_events_log.jsonl"
    except Exception:
        # Fallback to current directory
        return Path(".maceff/agent_events_log.jsonl")


# Breadcrumb cache for performance (avoid repeated expensive calls)
_breadcrumb_cache: Dict[str, Any] = {
    "breadcrumb": None,
    "timestamp": 0,
    "ttl": 1.0  # Cache for 1 second
}


def _get_cached_breadcrumb() -> str:
    """
    Get breadcrumb with 1-second caching for performance.

    Returns:
        Breadcrumb string
    """
    current_time = time.time()

    # Check cache validity
    if (_breadcrumb_cache["breadcrumb"] is not None and
            current_time - _breadcrumb_cache["timestamp"] < _breadcrumb_cache["ttl"]):
        return _breadcrumb_cache["breadcrumb"]

    # Generate fresh breadcrumb
    breadcrumb = get_breadcrumb()

    # Update cache
    _breadcrumb_cache["breadcrumb"] = breadcrumb
    _breadcrumb_cache["timestamp"] = current_time

    return breadcrumb


def append_event(
    event: str,
    data: dict,
    hook_input: Optional[dict] = None
) -> bool:
    """
    Append event to log atomically with file locking.

    Args:
        event: Event type (lowercase_underscore format)
        data: Event-specific data fields
        hook_input: Original hook stdin data (optional)

    Returns:
        True if successful, False on failure

    Example:
        >>> append_event("session_started", {"session_id": "abc123", "cycle": 170})
        True
    """
    try:
        log_path = _get_log_path()

        # Generate breadcrumb for forensic querying (cached for performance)
        breadcrumb = _get_cached_breadcrumb()

        # Build event record
        event_record = {
            "timestamp": time.time(),
            "event": event,
            "breadcrumb": breadcrumb,
            "data": data,
            "hook_input": hook_input if hook_input is not None else {}
        }

        # Atomic append with file locking
        with open(log_path, 'a') as f:
            # Acquire exclusive lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(event_record) + '\n')
                f.flush()
            finally:
                # Release lock
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Set permissions on first write
        if log_path.stat().st_size == len(json.dumps(event_record)) + 1:
            log_path.chmod(0o600)

        return True

    except Exception:
        return False


def read_events(
    limit: Optional[int] = None,
    reverse: bool = True
) -> Generator[dict, None, None]:
    """
    Read events from log (generator for memory efficiency).

    Args:
        limit: Maximum events to yield (None = all)
        reverse: If True, read from end (most recent first)

    Yields:
        Event dictionaries

    Example:
        >>> for event in read_events(limit=10, reverse=True):
        ...     print(event["event"], event["timestamp"])
    """
    try:
        log_path = _get_log_path()

        if not log_path.exists():
            return

        with open(log_path, 'r') as f:
            lines = f.readlines()

        # Reverse if requested
        if reverse:
            lines = reversed(lines)

        count = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
                yield event

                count += 1
                if limit is not None and count >= limit:
                    break

            except json.JSONDecodeError:
                # Skip malformed lines
                continue

    except Exception:
        return


def _matches_filter(event: dict, filters: dict) -> bool:
    """
    Check if event matches filter specification.

    Args:
        event: Event dictionary
        filters: Filter specification with keys:
            - event_type: Filter by event type
            - since: Events after timestamp
            - until: Events before timestamp
            - breadcrumb: Breadcrumb component filters (dict)
            - session_id: Full session UUID
            - without_matching: Exclude events with matching type

    Returns:
        True if event matches all filters
    """
    # Event type filter
    if 'event_type' in filters:
        if event.get('event') != filters['event_type']:
            return False

    # Timestamp range filters
    if 'since' in filters:
        if event.get('timestamp', 0) <= filters['since']:
            return False

    if 'until' in filters:
        if event.get('timestamp', float('inf')) >= filters['until']:
            return False

    # Breadcrumb component filters
    if 'breadcrumb' in filters:
        breadcrumb_str = event.get('breadcrumb', '')
        breadcrumb_data = parse_breadcrumb(breadcrumb_str)

        if not breadcrumb_data:
            return False

        breadcrumb_filters = filters['breadcrumb']

        # Session hash filter (shortened)
        if 's' in breadcrumb_filters:
            if breadcrumb_data.get('session_id') != breadcrumb_filters['s']:
                return False

        # Cycle number filter
        if 'c' in breadcrumb_filters:
            if breadcrumb_data.get('cycle') != breadcrumb_filters['c']:
                return False

        # Git hash filter (shortened)
        if 'g' in breadcrumb_filters:
            if breadcrumb_data.get('git_hash') != breadcrumb_filters['g']:
                return False

        # Prompt UUID filter (shortened)
        if 'p' in breadcrumb_filters:
            if breadcrumb_data.get('prompt_uuid') != breadcrumb_filters['p']:
                return False

        # Timestamp range filter (t_min, t_max)
        if 't_min' in breadcrumb_filters:
            if breadcrumb_data.get('timestamp', 0) < breadcrumb_filters['t_min']:
                return False

        if 't_max' in breadcrumb_filters:
            if breadcrumb_data.get('timestamp', float('inf')) > breadcrumb_filters['t_max']:
                return False

    # Full session UUID filter (search in data field)
    if 'session_id' in filters:
        event_session = event.get('data', {}).get('session_id')
        if event_session != filters['session_id']:
            return False

    # Exclusion filter
    if 'without_matching' in filters:
        if event.get('event') == filters['without_matching']:
            return False

    return True


def query_events(filters: dict) -> List[dict]:
    """
    Query events with forensic filters.

    Args:
        filters: Query specification (see _matches_filter for details)

    Returns:
        List of event dictionaries matching filters

    Examples:
        >>> # Find all events from cycle 170
        >>> events = query_events({'breadcrumb': {'c': 170}})

        >>> # Find events in git state g_44545c6
        >>> events = query_events({'breadcrumb': {'g': '44545c6'}})

        >>> # Find events between timestamps
        >>> events = query_events({'breadcrumb': {'t_min': 1000, 't_max': 2000}})
    """
    results = []

    for event in read_events(limit=None, reverse=False):
        if _matches_filter(event, filters):
            results.append(event)

    return results


def query_set_operations(queries: List[dict], operation: str) -> List[dict]:
    """
    Perform set operations on multiple queries.

    Args:
        queries: List of query filter dicts
        operation: One of "union", "intersection", "subtraction"

    Returns:
        List of events after set operation

    Examples:
        >>> # Union: Events from cycle 170 OR cycle 171
        >>> results = query_set_operations([
        ...     {'breadcrumb': {'c': 170}},
        ...     {'breadcrumb': {'c': 171}}
        ... ], 'union')

        >>> # Intersection: Events from cycle 170 AND git state g_44545c6
        >>> results = query_set_operations([
        ...     {'breadcrumb': {'c': 170}},
        ...     {'breadcrumb': {'g': '44545c6'}}
        ... ], 'intersection')

        >>> # Subtraction: Events from cycle 170 EXCEPT tool_call_started
        >>> results = query_set_operations([
        ...     {'breadcrumb': {'c': 170}},
        ...     {'event_type': 'tool_call_started'}
        ... ], 'subtraction')
    """
    if not queries:
        return []

    # Execute all queries
    query_results = [set(json.dumps(e, sort_keys=True) for e in query_events(q)) for q in queries]

    # Perform set operation
    if operation == "union":
        result_set = set().union(*query_results)
    elif operation == "intersection":
        result_set = query_results[0]
        for query_result in query_results[1:]:
            result_set = result_set.intersection(query_result)
    elif operation == "subtraction":
        result_set = query_results[0]
        for query_result in query_results[1:]:
            result_set = result_set.difference(query_result)
    else:
        return []

    # Convert back to dicts and sort by timestamp
    results = [json.loads(s) for s in result_set]
    results.sort(key=lambda e: e.get('timestamp', 0))

    return results


def reconstruct_state_at(timestamp: float) -> dict:
    """
    Reconstruct agent state at specific timestamp.

    Uses slow-field tracking to build state from events up to timestamp.

    Args:
        timestamp: Unix epoch timestamp

    Returns:
        Dict with session_id, cycle, and other tracked state fields

    Example:
        >>> state = reconstruct_state_at(1500.0)
        >>> print(state["session_id"], state["cycle"])
    """
    state = {
        "session_id": None,
        "cycle": None,
    }

    # Scan events up to timestamp
    for event in read_events(limit=None, reverse=False):
        event_time = event.get('timestamp', 0)

        if event_time > timestamp:
            break

        # Update state with slow-changing fields from data
        event_data = event.get('data', {})

        if 'session_id' in event_data:
            state['session_id'] = event_data['session_id']

        if 'cycle' in event_data:
            state['cycle'] = event_data['cycle']

    return state


def get_current_state() -> dict:
    """
    Get latest reconstructed state.

    Returns:
        Dict with current session_id, cycle, etc.

    Example:
        >>> state = get_current_state()
        >>> print(f"Current: {state['session_id']} Cycle {state['cycle']}")
    """
    return reconstruct_state_at(time.time())


def tally_all_events() -> dict:
    """
    Scan event log and count ALL event types for snapshot baseline.

    Counts every unique event type found in the log, sums durations from
    *_ended events, and captures metadata about the scan. Designed for
    future extensibility - new event types automatically included.

    Returns:
        {
            "event_tallies": {"session_started": 50, "dev_drv_ended": 148, ...},
            "accumulated_durations": {
                "total_dev_drv_duration_seconds": 12345.67,
                "total_deleg_drv_duration_seconds": 5678.90
            },
            "metadata": {
                "events_scanned": 6500,
                "earliest_timestamp": 1760000000.0,
                "latest_timestamp": 1764719000.0,
                "unique_event_types": 15
            }
        }

    Example:
        >>> tallies = tally_all_events()
        >>> print(f"Total sessions: {tallies['event_tallies'].get('session_started', 0)}")
    """
    event_tallies: Dict[str, int] = {}
    accumulated_durations = {
        "total_dev_drv_duration_seconds": 0.0,
        "total_deleg_drv_duration_seconds": 0.0,
    }
    events_scanned = 0
    earliest_timestamp = float('inf')
    latest_timestamp = 0.0

    for event in read_events(limit=None, reverse=False):
        events_scanned += 1

        # Track timestamps
        event_time = event.get('timestamp', 0)
        if event_time > 0:
            earliest_timestamp = min(earliest_timestamp, event_time)
            latest_timestamp = max(latest_timestamp, event_time)

        # Count by event type
        event_type = event.get('event', 'unknown')
        event_tallies[event_type] = event_tallies.get(event_type, 0) + 1

        # Sum durations from *_ended events
        event_data = event.get('data', {})
        if event_type == 'dev_drv_ended':
            duration = event_data.get('duration_seconds', 0)
            if isinstance(duration, (int, float)):
                accumulated_durations['total_dev_drv_duration_seconds'] += duration
        elif event_type == 'deleg_drv_ended':
            duration = event_data.get('duration_seconds', 0)
            if isinstance(duration, (int, float)):
                accumulated_durations['total_deleg_drv_duration_seconds'] += duration

    # Handle empty log case
    if earliest_timestamp == float('inf'):
        earliest_timestamp = 0.0

    return {
        "event_tallies": event_tallies,
        "accumulated_durations": accumulated_durations,
        "metadata": {
            "events_scanned": events_scanned,
            "earliest_timestamp": earliest_timestamp,
            "latest_timestamp": latest_timestamp,
            "unique_event_types": len(event_tallies),
        }
    }


def emit_state_snapshot(
    session_id: str,
    snapshot_type: str,
    source: str,
    state_file_values: Optional[dict] = None,
) -> bool:
    """
    Emit state_snapshot event with comprehensive tallies for historical baseline.

    Creates immutable baseline that query functions use: baseline + incremental
    events after snapshot = accurate total. Enables safe migration from mutable
    state files to event-first queries without losing historical data.

    Args:
        session_id: Current session identifier
        snapshot_type: "initialization" | "compaction_recovery" | "manual"
        source: "state_files" | "event_log_scan" | "command_line"
        state_file_values: Optional dict with values from state files to merge
            {
                "cycle_number": 205,
                "dev_drv_count": 50,
                "deleg_drv_count": 25,
                "compaction_count": 13,
                "auto_mode": False,
                "auto_mode_source": "default"
            }

    Returns:
        True if snapshot emitted successfully, False on failure

    Example:
        >>> emit_state_snapshot(
        ...     session_id="abc123",
        ...     snapshot_type="initialization",
        ...     source="state_files",
        ...     state_file_values={"cycle_number": 205, "dev_drv_count": 50}
        ... )
        True
    """
    # Tally all events in the log
    tallies = tally_all_events()

    # Merge state file values for historical data predating the log
    derived_values = {}
    current_state = {}

    if state_file_values:
        # Derived values from state files
        if 'cycle_number' in state_file_values:
            derived_values['cycle_number'] = state_file_values['cycle_number']

        if 'dev_drv_count' in state_file_values:
            derived_values['completed_dev_drvs'] = state_file_values['dev_drv_count']

        if 'deleg_drv_count' in state_file_values:
            derived_values['completed_deleg_drvs'] = state_file_values['deleg_drv_count']

        # Current state from state files
        if 'auto_mode' in state_file_values:
            current_state['auto_mode'] = state_file_values['auto_mode']

        if 'auto_mode_source' in state_file_values:
            current_state['auto_mode_source'] = state_file_values['auto_mode_source']

        if 'compaction_count' in state_file_values:
            # Override event tally with state file value if higher (historical data)
            event_count = tallies['event_tallies'].get('compaction_detected', 0)
            state_count = state_file_values['compaction_count']
            if state_count > event_count:
                tallies['event_tallies']['compaction_detected'] = state_count

    # Build snapshot data
    snapshot_data = {
        "session_id": session_id,
        "snapshot_type": snapshot_type,
        "source": source,
        "event_tallies": tallies['event_tallies'],
        "accumulated_durations": tallies['accumulated_durations'],
        "derived_values": derived_values,
        "current_state": current_state,
        "snapshot_metadata": tallies['metadata'],
    }

    # Emit the snapshot event
    return append_event("state_snapshot", snapshot_data)


__all__ = [
    "append_event",
    "read_events",
    "query_events",
    "query_set_operations",
    "reconstruct_state_at",
    "get_current_state",
    "tally_all_events",
    "emit_state_snapshot",
]
