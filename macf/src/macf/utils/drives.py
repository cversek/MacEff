"""
Drives utilities.

Event-first architecture: All drive operations emit events to the append-only
JSONL log. Event queries reconstruct state from these events. State files are
deprecated fallback (Phase 6) and will be removed (Phase 7).
"""

import time
import uuid
from typing import Any, Dict, List, Optional
from .session import get_last_user_prompt_uuid


def _emit_event(event: str, data: dict) -> bool:
    """
    Lazy import wrapper to avoid circular import.

    agent_events_log imports from utils, utils imports drives,
    drives importing from agent_events_log creates a cycle.
    """
    from ..agent_events_log import append_event
    return append_event(event, data)

def start_dev_drv(session_id: str, agent_id: Optional[str] = None, prompt_uuid: Optional[str] = None) -> bool:
    """
    Mark Development Drive start.

    DEV_DRV = period from user plan approval/UserPromptSubmit to Stop hook.
    Event-first: emits dev_drv_started event as source of truth.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (unused, kept for API compatibility)
        prompt_uuid: Prompt UUID (auto-detected from JSONL if None)

    Returns:
        True if successful, False otherwise
    """
    started_at = time.time()

    # Use provided UUID or capture from JSONL or generate new
    if prompt_uuid is None:
        prompt_uuid = get_last_user_prompt_uuid(session_id)
    if prompt_uuid is None:
        # Generate UUID for test/isolated environments where JSONL isn't available
        prompt_uuid = f"gen_{uuid.uuid4().hex[:8]}"

    # EVENT-FIRST: Event is sole truth
    _emit_event("dev_drv_started", {
        "session_id": session_id,
        "prompt_uuid": prompt_uuid,
        "timestamp": started_at
    })

    return True

def complete_dev_drv(session_id: str, agent_id: Optional[str] = None) -> tuple[bool, float]:
    """
    Mark Development Drive completion and update stats.

    Returns:
        Tuple of (success: bool, duration_seconds: float)
    """
    # EVENT-FIRST: Query events for active drive start time
    from ..event_queries import get_active_dev_drv_start
    started_at, prompt_uuid = get_active_dev_drv_start(session_id)

    if started_at == 0.0:
        return (False, 0.0)  # No active drive

    duration = time.time() - started_at

    # Emit dev_drv_ended event
    _emit_event("dev_drv_ended", {
        "session_id": session_id,
        "prompt_uuid": prompt_uuid,
        "duration": duration
    })

    return (True, duration)

def get_dev_drv_stats(session_id: str, agent_id: Optional[str] = None) -> dict:
    """
    Get current Development Drive statistics from event log.

    EVENT-FIRST: Queries event log for DEV_DRV stats with snapshot baseline.

    Returns:
        Dict with keys: count, total_duration, current_started_at, avg_duration, prompt_uuid
    """
    try:
        # EVENT-FIRST: Query event log (lazy import to avoid circular)
        from ..event_queries import get_dev_drv_stats_from_events
        stats = get_dev_drv_stats_from_events(session_id)

        count = stats.get("count", 0)
        total_duration = stats.get("total_duration", 0.0)
        avg_duration = total_duration / count if count > 0 else 0.0

        return {
            "count": count,
            "total_duration": total_duration,
            "current_started_at": None,  # Not tracked in events (would need in-progress query)
            "prompt_uuid": stats.get("current_prompt_uuid"),
            "avg_duration": avg_duration,
            "from_snapshot": stats.get("from_snapshot", False)
        }
    except Exception:
        # No fallback - return empty stats
        return {
            "count": 0,
            "total_duration": 0.0,
            "current_started_at": None,
            "prompt_uuid": None,
            "avg_duration": 0.0,
            "from_snapshot": False
        }

def start_deleg_drv(session_id: str, agent_id: Optional[str] = None, subagent_type: Optional[str] = None) -> bool:
    """
    Mark Delegation Drive start.

    DELEG_DRV = period from Task tool invocation to SubagentStop hook.
    Event-first: emits deleg_drv_started event as source of truth.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (unused, kept for API compatibility)
        subagent_type: Type of subagent being delegated to (for event tracking)

    Returns:
        True if successful, False otherwise
    """
    started_at = time.time()

    # EVENT-FIRST: Event is sole truth
    _emit_event("deleg_drv_started", {
        "session_id": session_id,
        "subagent_type": subagent_type or "unknown",
        "timestamp": started_at
    })

    return True

def complete_deleg_drv(session_id: str, agent_id: Optional[str] = None, subagent_type: Optional[str] = None) -> tuple[bool, float]:
    """
    Mark Delegation Drive completion and update stats.

    Returns:
        Tuple of (success: bool, duration_seconds: float)
    """
    # EVENT-FIRST: Query events for active drive start time
    from ..event_queries import get_active_deleg_drv_start
    started_at = get_active_deleg_drv_start(session_id)

    if started_at == 0.0:
        return (False, 0.0)  # No active drive

    duration = time.time() - started_at

    # Emit deleg_drv_ended event
    _emit_event("deleg_drv_ended", {
        "session_id": session_id,
        "subagent_type": subagent_type or "unknown",
        "duration": duration
    })

    return (True, duration)

def get_deleg_drv_stats(session_id: str, agent_id: Optional[str] = None) -> dict:
    """
    Get current Delegation Drive statistics from event log.

    EVENT-FIRST: Queries event log for DELEG_DRV stats.

    Returns:
        Dict with keys: count, total_duration, current_started_at, avg_duration, subagent_types
    """
    try:
        # EVENT-FIRST: Query event log (lazy import to avoid circular)
        from ..event_queries import get_deleg_drv_stats_from_events
        stats = get_deleg_drv_stats_from_events(session_id)

        count = stats.get("count", 0)
        total_duration = stats.get("total_duration", 0.0)
        avg_duration = total_duration / count if count > 0 else 0.0

        return {
            "count": count,
            "total_duration": total_duration,
            "current_started_at": None,  # Not tracked in events
            "avg_duration": avg_duration,
            "subagent_types": stats.get("subagent_types", [])
        }
    except Exception:
        # No fallback - return empty stats
        return {
            "count": 0,
            "total_duration": 0.0,
            "current_started_at": None,
            "avg_duration": 0.0,
            "subagent_types": []
        }

def record_delegation_start(
    session_id: str,
    tool_use_uuid: str,
    subagent_type: str,
    agent_id: Optional[str] = None
) -> bool:
    """
    Record delegation start via event emission.

    Event-first: emits delegation_started event as source of truth.

    Args:
        session_id: Session identifier
        tool_use_uuid: Task tool_use_id for JSONL sidechain lookup
        subagent_type: Type of subagent (e.g., "devops-eng", "test-eng")
        agent_id: Agent identifier (unused, kept for API compatibility)

    Returns:
        True if recorded successfully, False otherwise
    """
    try:
        _emit_event("delegation_started", {
            "session_id": session_id,
            "tool_use_uuid": tool_use_uuid,
            "subagent_type": subagent_type,
            "timestamp": time.time()
        })
        return True
    except Exception:
        return False

def record_delegation_complete(
    session_id: str,
    tool_use_uuid: str,
    duration: float,
    agent_id: Optional[str] = None
) -> bool:
    """
    Mark delegation as complete with duration via event emission.

    Event-first: emits delegation_completed event as source of truth.

    Args:
        session_id: Session identifier
        tool_use_uuid: Task tool_use_id to match
        duration: Duration in seconds
        agent_id: Agent identifier (unused, kept for API compatibility)

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        _emit_event("delegation_completed", {
            "session_id": session_id,
            "tool_use_uuid": tool_use_uuid,
            "duration": duration,
            "timestamp": time.time()
        })
        return True
    except Exception:
        return False

def get_delegations_this_drive(
    session_id: str,
    agent_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all delegations for current DEV_DRV from event log.

    EVENT-FIRST: Queries event log for delegations since last dev_drv_started.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (auto-detected if None)

    Returns:
        List of delegation dicts (empty list on failure)
    """
    try:
        # EVENT-FIRST: Query event log (lazy import to avoid circular)
        from ..event_queries import get_delegations_this_drive_from_events
        return get_delegations_this_drive_from_events(session_id)
    except Exception:
        # No fallback - return empty list
        return []

def clear_delegations_this_drive(
    session_id: str,
    agent_id: Optional[str] = None
) -> bool:
    """
    Clear delegation list (called after DEV_DRV Complete reporting).

    Event-first: No-op - delegations are scoped to DEV_DRV via event timestamps.
    When dev_drv_ended is emitted, delegations for that drive are implicitly closed.
    Kept for API compatibility.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (unused, kept for API compatibility)

    Returns:
        True always (no-op in event-first architecture)
    """
    # No-op: Event-first architecture scopes delegations by dev_drv timestamps
    # get_delegations_this_drive_from_events() queries events since last dev_drv_started
    return True
