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
    for event in read_events(reverse=True):
        if event.get("event") == "state_snapshot":
            return event
    return None


def get_latest_event(event_type: str, limit: Optional[int] = None) -> Optional[dict]:
    """
    Find most recent event of a specific type.

    Args:
        event_type: The event type to search for (e.g., "todos_updated")
        limit: Maximum events to scan (default None = scan all)

    Returns:
        Most recent event of the specified type, or None if not found
    """
    for event in read_events(limit=limit, reverse=True):
        if event.get("event") == event_type:
            return event
    return None


def get_nth_event(event_type: str, n: int = 0, limit: Optional[int] = None) -> Optional[dict]:
    """
    Find the nth most recent event of a specific type.

    Args:
        event_type: The event type to search for (e.g., "todos_updated")
        n: How many events back (0 = most recent, 1 = previous, etc.)
        limit: Maximum events to scan (default None = scan all)

    Returns:
        The nth most recent event of the specified type, or None if not found
    """
    count = 0
    for event in read_events(limit=limit, reverse=True):
        if event.get("event") == event_type:
            if count == n:
                return event
            count += 1
    return None


def get_recent_events(event_type: str, max_count: int = 100, limit: Optional[int] = None) -> List[dict]:
    """
    Get all recent events of a specific type.

    Args:
        event_type: The event type to search for
        max_count: Maximum number of matching events to return
        limit: Maximum events to scan (default None = scan all)

    Returns:
        List of matching events, most recent first
    """
    results = []
    for event in read_events(limit=limit, reverse=True):
        if event.get("event") == event_type:
            results.append(event)
            if len(results) >= max_count:
                break
    return results


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
                del started_prompts[prompt_uuid]  # Drive completed
                current_prompt_uuid = prompt_uuid  # Track most recent ended UUID

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
    Get cycle number from events.

    Priority (last-write-wins semantics):
    1. Most recent cycle_correction event's 'cycle' field (manual correction)
    2. Most recent compaction_detected event's 'cycle' field (current cycle)
    3. state_snapshot's derived_values.cycle_number (baseline)
    4. Default to 1 for first run

    Returns:
        Current cycle number (1 if no events found)
    """
    # Reverse scan - find most recent cycle source
    # Self-limiting: exits on first match
    for event in read_events(limit=None, reverse=True):
        event_type = event.get("event")

        # Highest priority: cycle_correction (manual fix for test pollution)
        if event_type == "cycle_correction":
            data = event.get("data", {})
            cycle = data.get("cycle")
            if cycle is not None and cycle > 0:
                return cycle

        # Primary: compaction_detected has authoritative cycle number
        if event_type == "compaction_detected":
            data = event.get("data", {})
            cycle = data.get("cycle")
            if cycle is not None and cycle > 0:
                return cycle

        # Fallback: state_snapshot baseline
        if event_type == "state_snapshot":
            data = event.get("data", {})
            # Check derived_values first (from state file captures)
            derived = data.get("derived_values", {})
            if "cycle_number" in derived:
                return derived["cycle_number"]
            # Fallback to event_tallies
            tallies = data.get("event_tallies", {})
            if "compaction_detected" in tallies:
                return tallies["compaction_detected"] + 1

    # No events - return 1 (first run default)
    return 1


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


def get_latest_compaction_event(session_id: str) -> Optional[dict]:
    """Most recent ``compaction_detected`` event for a given session.

    The SessionStart hook unconditionally emits ``compaction_detected`` whenever
    it detects compaction, both for the ``source == 'compact'`` path and the
    JSONL-fallback detection path. The event carries the session_id and the
    event-record's own ``timestamp`` field (set by ``append_event`` at emission
    time).

    Token-reading code uses this event's timestamp as a lower bound on
    "what counts as post-compaction" — any assistant message in the transcript
    with ``timestamp < event.timestamp`` is pre-compaction (either before the
    boundary or a preserved-segment replay with its original older timestamp)
    and must be filtered out.

    Args:
        session_id: Session ID to filter events. Matching uses the first 8
                    characters (same prefix convention as
                    ``get_active_dev_drv_start``). A different session's
                    compaction does NOT bound the current session's reads.

    Returns:
        The full event record dict (with ``timestamp``, ``event``, ``data``,
        ``breadcrumb`` keys) or ``None`` if no matching event exists.
    """
    session_prefix = session_id[:8] if session_id else ""
    if not session_prefix:
        return None

    for event in read_events(reverse=True):
        if event.get("event") != "compaction_detected":
            continue
        event_session = event.get("data", {}).get("session_id", "")
        if not event_session or not event_session.startswith(session_prefix):
            continue
        return event
    return None


def get_active_dev_drv_start(session_id: str) -> tuple[float, str]:
    """Get start time and prompt_uuid of active (unended) dev_drv from events."""
    from .agent_events_log import read_events
    session_prefix = session_id[:8] if session_id else ""

    # Read in reverse - find most recent started/ended first
    for event in read_events(reverse=True):
        event_type = event.get("event")
        data = event.get("data", {})
        event_session = data.get("session_id", "")
        if session_prefix and event_session and not event_session.startswith(session_prefix):
            continue
        if event_type == "dev_drv_ended":
            return (0.0, "")  # Most recent is ended - no active drive
        if event_type == "dev_drv_started":
            return (data.get("timestamp", 0.0), data.get("prompt_uuid", ""))
    return (0.0, "")


def get_active_deleg_drv_start(session_id: str) -> tuple[float, str, str]:
    """Get start time + tool_use_id_short + subagent_type of active (unended)
    deleg_drv from events.

    Returns:
        Tuple of (started_at, tool_use_id_short, subagent_type).
        ``(0.0, "", "")`` when no active drive exists.
    """
    from .agent_events_log import read_events
    session_prefix = session_id[:8] if session_id else ""

    # Reverse stream — first started/ended event for this session
    # wins. Phase 1 streaming readers make this O(events-to-answer),
    # not O(total-events), so no cap is needed.
    for event in read_events(reverse=True):
        event_type = event.get("event")
        data = event.get("data", {})
        event_session = data.get("session_id", "")
        if session_prefix and event_session and not event_session.startswith(session_prefix):
            continue
        if event_type == "deleg_drv_ended":
            return (0.0, "", "")  # Most recent is ended - no active drive
        if event_type == "deleg_drv_started":
            return (
                data.get("timestamp", 0.0),
                data.get("tool_use_id_short", ""),
                data.get("subagent_type", ""),
            )
    return (0.0, "", "")


def get_oldest_unbridged_deleg_drv_started(
    session_id: str,
    preferred_subagent_type: str = "",
) -> tuple:
    """Find the best-match deleg_drv_started event without a matching booted event.

    Bridge primitive that survives parallel-delegation out-of-order
    SubagentStart firing:

    1. Filter starteds to unbridged + within the 120s recency window.
    2. If ``preferred_subagent_type`` is supplied AND any candidate
       matches it, return the OLDEST matching one. This handles
       parallel same-type-pair delegations where SubagentStart fires
       in an order that differs from PreToolUse:Agent dispatch order.
    3. Otherwise fall back to the oldest unbridged candidate (FIFO).

    The type-preference step makes the bridge robust to out-of-order
    SubagentStart firing as long as the parallel SAs have distinct
    subagent_types — which is the common practical case. Same-type
    parallel pairs (two Explore SAs at once) still fall back to FIFO,
    which is the best available signal given CC's hook payload.

    Args:
        session_id: Parent session UUID.
        preferred_subagent_type: When non-empty, prefer a started whose
            ``subagent_type`` matches. Pass this from SubagentStart's
            ``agent_type`` field to disambiguate parallel different-type
            delegations.

    Returns:
        Tuple of (started_at, tool_use_id, tool_use_id_short, subagent_type).
        ``(0.0, "", "", "")`` when no unbridged started exists in window.
    """
    from .agent_events_log import read_events
    session_prefix = session_id[:8] if session_id else ""

    started_events: List[dict] = []
    bridged_tool_use_ids: set = set()

    # Walk events in forward order to preserve FIFO semantics
    for event in read_events(reverse=False):
        event_type = event.get("event")
        data = event.get("data", {})
        event_session = data.get("session_id", "")
        if session_prefix and event_session and not event_session.startswith(session_prefix):
            continue
        if event_type == "deleg_drv_started":
            started_events.append(data)
        elif event_type == "deleg_drv_subagent_booted":
            tuid = data.get("tool_use_id", "")
            if tuid:
                bridged_tool_use_ids.add(tuid)

    # Build the list of bridgeable candidates:
    # - has tool_use_id (skip pre-schema starteds — not bridgeable)
    # - not already bridged
    # - within 120s recency window (CC's PreToolUse:Agent → SubagentStart
    #   latency is sub-second; anything older is a stale unmatched
    #   started from a prior demo / failed delegation and would yield
    #   nonsense duration on the eventual SubagentStop).
    import time
    now = time.time()
    max_age = 120.0

    candidates = []
    for data in started_events:
        tuid = data.get("tool_use_id", "")
        if not tuid:
            continue
        if tuid in bridged_tool_use_ids:
            continue
        ts = data.get("timestamp", 0.0)
        if ts == 0.0 or (now - ts) > max_age:
            continue
        candidates.append(data)

    if not candidates:
        return (0.0, "", "", "")

    # Type-preference step: if caller supplied a preferred_subagent_type
    # AND any candidate matches, return the OLDEST matching one. This
    # survives out-of-order SubagentStart firing for parallel SAs of
    # distinct types. Same-type parallel pairs still fall back to FIFO.
    if preferred_subagent_type:
        for data in candidates:
            if data.get("subagent_type", "") == preferred_subagent_type:
                return (
                    data.get("timestamp", 0.0),
                    data.get("tool_use_id", ""),
                    data.get("tool_use_id_short", ""),
                    data.get("subagent_type", ""),
                )

    # FIFO fallback: oldest unbridged candidate.
    data = candidates[0]
    return (
        data.get("timestamp", 0.0),
        data.get("tool_use_id", ""),
        data.get("tool_use_id_short", ""),
        data.get("subagent_type", ""),
        )
    return (0.0, "", "", "")


def get_deleg_drv_bridge_by_agent_id(session_id: str, agent_id: str) -> Optional[dict]:
    """Find the deleg_drv_subagent_booted event for the given agent_id.

    Returns the bridge event's data dict (carrying tool_use_id +
    tool_use_id_short + agent_type + started_at) so callers can recover
    the full pair-key at SubagentStop time. Returns ``None`` if no
    bridge event exists for this agent_id (e.g. SA started before the
    SubagentStart handler was instrumented).

    Args:
        session_id: Parent session UUID for filtering.
        agent_id: The subagent's CC AgentId to match.

    Returns:
        The event's ``data`` dict, or ``None``.
    """
    from .agent_events_log import read_events
    session_prefix = session_id[:8] if session_id else ""

    # Reverse walk — most recent bridge for this agent_id wins
    for event in read_events(reverse=True):
        if event.get("event") != "deleg_drv_subagent_booted":
            continue
        data = event.get("data", {})
        event_session = data.get("session_id", "")
        if session_prefix and event_session and not event_session.startswith(session_prefix):
            continue
        if data.get("agent_id") == agent_id:
            return data
    return None


def get_current_session_id_from_events() -> str:
    """
    Get current session ID from most recent event containing session_id.

    This is the authoritative source for session ID - uses event log
    instead of mtime-based file detection which can be non-deterministic
    when multiple session files exist.

    Looks for session_id in ANY recent event (not just session_started),
    since tool_call events and others also carry session_id from hooks.

    Returns:
        Current session ID string, or empty string if no events with session_id
    """
    # Length guard: legitimate session IDs are full UUIDs (~36 chars). Some
    # historical writers stored breadcrumb-truncated 8-char prefixes (e.g.
    # 'd4abc33b' from `s_d4abc33b/...`) into event data, which then poisoned
    # downstream consumers — JSONL path resolution failed, get_token_info
    # defaulted to tokens_used=0, dashboard rendered CL100 perpetually. Reject
    # short values so the get_current_session_id() caller falls through to
    # mtime-based detection (which reads the full UUID from JSONL filename).
    MIN_VALID_LEN = 16

    for event in read_events(reverse=True):
        # Check data.session_id first (most events store it there)
        session_id = event.get("data", {}).get("session_id", "")
        if session_id and len(session_id) >= MIN_VALID_LEN:
            return session_id
        # Also check top-level session_id (some events may use this)
        session_id = event.get("session_id", "")
        if session_id and len(session_id) >= MIN_VALID_LEN:
            return session_id
    return ""


def get_last_session_id_from_events() -> str:
    """
    Get the previous session ID from most recent migration_detected event.

    This is used for session migration recovery - finding the session that
    was active before the current one started.

    Returns:
        Previous session ID string, or empty string if no migration detected
    """
    # Read most recent events first
    for event in read_events(reverse=True):
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
    for event in read_events(reverse=True):
        if event.get("event") == "session_ended":
            data = event.get("data", {})
            timestamp = data.get("timestamp")
            if timestamp:
                return float(timestamp)

    return None


def get_auto_mode_from_events(session_id: str) -> Tuple[bool, str]:
    """
    Get auto_mode setting from most recent mode_change event.

    Searches for the most recent mode_change event (the authoritative setting)
    to determine current operating mode. mode_change events are emitted by
    `macf_tools mode set` and by SessionStart tunneling after compaction.

    Note: Previously searched auto_mode_detected events, which are forensic
    records emitted BY SessionStart — creating a chicken-and-egg bug where
    the function would find its own previous (false) output instead of the
    user's actual mode_change setting.

    Args:
        session_id: Session ID to filter events (uses first 8 chars for matching)

    Returns:
        Tuple of (auto_mode: bool, source: str)
        Default: (False, "default")
    """
    # NOTE: No session isolation for mode_change events.
    # Mode is a user directive that must persist across session restarts.
    # Unlike dev_drv events (per-session), mode_change is a global setting.
    # The autonomous_operation policy specifies: mode persists across compaction
    # (source=compact) and resets only on crash/restart (source=resume).
    # SessionStart handles the reset logic — this function just finds the
    # most recent mode_change regardless of which session wrote it.

    # Read most recent events first — find the latest mode_change
    # NOTE: limit=None because mode_change events are rare (1 per session)
    # and can be buried under thousands of tool_call/cli_command events.
    # With limit=200, a busy session would push mode_change out of range.
    for event in read_events(limit=None, reverse=True):
        if event.get("event") == "mode_change":
            data = event.get("data", {})

            mode = data.get("mode", "MANUAL_MODE")
            enabled = data.get("enabled", False)
            auto_mode = (mode == "AUTO_MODE" and enabled)

            return (auto_mode, "event")

    return (False, "default")


def get_active_policy_injections_from_events() -> List[Dict[str, str]]:
    """
    Get list of currently active policy injections from event log.

    Scans in REVERSE (most recent first) for efficiency, stopping at:
    - policy_injections_cleared_all event (explicit clear)
    - compaction_detected event (cycle boundary - injections reset)

    **Design Note**: Injections do NOT persist across compaction. After compaction,
    agents must re-inject policies. This simplifies implementation (bounded search)
    and aligns with fresh-context-fresh-injections philosophy.

    Event types:
    - policy_injection_activated: Activates injection for a policy
    - policy_injection_cleared: Deactivates specific policy (auto-clear or lifecycle)
    - policy_injections_cleared_all: Deactivates ALL policies (early exit)

    Returns:
        List of dicts with keys:
        - policy_name: Name of the policy (e.g., "task_management")
        - policy_path: Absolute path to the policy file

    Example:
        >>> injections = get_active_policy_injections_from_events()
        >>> for inj in injections:
        ...     print(f"{inj['policy_name']}: {inj['policy_path']}")
    """
    # Track active policies found during reverse scan
    # Key: policy_name, Value: {"policy_path": "...", "state": "active"|"cleared"}
    policy_final_states: Dict[str, Dict[str, str]] = {}

    # Reverse scan - first event for each policy determines its state
    for event in read_events(limit=None, reverse=True):
        event_type = event.get("event")
        data = event.get("data", {})

        # Early exit conditions (compaction boundary or explicit clear-all)
        if event_type in ("policy_injections_cleared_all", "compaction_detected"):
            break

        elif event_type == "policy_injection_cleared":
            policy_name = data.get("policy_name")
            if policy_name and policy_name not in policy_final_states:
                # First time seeing this policy - it's cleared (don't re-inject)
                policy_final_states[policy_name] = {"state": "cleared"}

        elif event_type == "policy_injection_activated":
            policy_name = data.get("policy_name")
            policy_path = data.get("policy_path", "")
            source = data.get("source", "")
            if policy_name and policy_name not in policy_final_states:
                # First time seeing this policy - it's active
                policy_final_states[policy_name] = {
                    "state": "active",
                    "policy_path": policy_path,
                    "source": source,
                }

    # Filter to only active policies and format output
    return [
        {"policy_name": name, "policy_path": state["policy_path"], "source": state.get("source", "")}
        for name, state in policy_final_states.items()
        if state.get("state") == "active"
    ]
