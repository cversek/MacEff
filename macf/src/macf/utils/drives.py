"""
Drives utilities.

Event-first architecture: All drive operations emit events to the append-only
JSONL log. Event queries reconstruct state from these events.
"""

import sys
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

def start_dev_drv(session_id: str, agent_id: Optional[str] = None, prompt_uuid: Optional[str] = None, prompt_preview: Optional[str] = None) -> bool:
    """
    Mark Development Drive start.

    DEV_DRV = period from user plan approval/UserPromptSubmit to Stop hook.
    Event-first: emits dev_drv_started event as source of truth.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (unused, kept for API compatibility)
        prompt_uuid: Prompt UUID (auto-detected from JSONL if None)
        prompt_preview: First 200 chars of user prompt for forensic recovery (optional)

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
    event_data = {
        "session_id": session_id,
        "prompt_uuid": prompt_uuid,
        "timestamp": started_at
    }
    # Include prompt preview for forensic recovery if provided
    if prompt_preview:
        event_data["prompt_preview"] = prompt_preview
    _emit_event("dev_drv_started", event_data)

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
    except Exception as e:
        print(f"⚠️ MACF: dev drive stats query failed: {e}", file=sys.stderr)
        return {
            "count": 0,
            "total_duration": 0.0,
            "current_started_at": None,
            "prompt_uuid": None,
            "avg_duration": 0.0,
            "from_snapshot": False
        }

def _tool_use_id_short(tool_use_id: str) -> str:
    """Return the 6-char display slice of a tool_use_id.

    CC tool_use_ids are formatted ``toolu_<24+ chars>``. The constant
    ``toolu_`` prefix is uninformative; slicing [6:12] gives the first
    six unique characters — the right length for a human-readable
    Telegram tag while preserving uniqueness within a session.
    Returns empty string if input is too short.
    """
    if not tool_use_id or len(tool_use_id) < 12:
        return ""
    return tool_use_id[6:12]


def start_deleg_drv(
    session_id: str,
    agent_id: Optional[str] = None,
    subagent_type: Optional[str] = None,
    tool_use_id: str = "",
) -> bool:
    """
    Mark Delegation Drive start.

    DELEG_DRV = period from Agent tool invocation (parent side) to
    SubagentStop hook (subagent finished). Event-first: emits the
    deleg_drv_started event as source of truth.

    Args:
        session_id: Parent session UUID.
        agent_id: Unused, kept for API compatibility.
        subagent_type: Type of subagent being delegated to
            (e.g. ``"Explore"``, ``"DevOpsEng"``).
        tool_use_id: Full Claude Code tool_use_id (``toolu_<24+ chars>``)
            of the Agent tool invocation. Primary cross-surface join
            key — grep this value in the parent's transcript JSONL to
            find the assistant turn that invoked the SA and the user
            turn that received its result. The 6-char display slice is
            derived automatically.

    Returns:
        True if the event was emitted.
    """
    started_at = time.time()

    _emit_event("deleg_drv_started", {
        "session_id": session_id,
        "subagent_type": subagent_type or "unknown",
        "timestamp": started_at,
        "tool_use_id": tool_use_id,
        "tool_use_id_short": _tool_use_id_short(tool_use_id),
    })

    return True


def bridge_deleg_drv_to_agent(
    session_id: str,
    agent_id: str,
    agent_type: Optional[str] = None,
) -> bool:
    """Emit ``deleg_drv_subagent_booted`` — the parallel-safe bridge event.

    Pairs a deleg_drv_started (parent's tool_use_id) with the subagent's
    runtime agent_id. Called from the SubagentStart hook handler. The
    bridge consumes the OLDEST UNBRIDGED started event for this parent
    session — parallel-safe via FIFO matching because Claude Code
    dispatches Agent tool invocations serially within a turn, so the
    bridge order matches the started order.

    Args:
        session_id: Parent session UUID. (CC subagents share the parent's
            session_id; see CC internals KB §10.31.)
        agent_id: The subagent's CC AgentId (``a<16hex>``).
        agent_type: Subagent type as reported by SubagentStart hook
            (CC field: ``agent_type``).

    Returns:
        True if a started event was found and the bridge was paired.
        False if no unbridged started event exists for this session
        (the bridge still emits with empty tool_use_id so the SA's
        existence is recorded even without parent linkage).
    """
    from ..event_queries import get_oldest_unbridged_deleg_drv_started

    started_at, tool_use_id, tool_use_id_short, started_subagent_type = (
        get_oldest_unbridged_deleg_drv_started(
            session_id,
            preferred_subagent_type=agent_type or "",
        )
    )

    found_match = started_at > 0.0

    _emit_event("deleg_drv_subagent_booted", {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_type": agent_type or started_subagent_type or "unknown",
        "tool_use_id": tool_use_id,
        "tool_use_id_short": tool_use_id_short,
        "started_at": started_at,
    })

    return found_match


def complete_deleg_drv_by_agent(
    session_id: str,
    agent_id: str,
    agent_transcript_path: str = "",
    last_assistant_message: str = "",
) -> tuple:
    """Emit ``deleg_drv_ended`` keyed on agent_id via the bridge event.

    Looks up the bridge event for this agent_id (emitted at SubagentStart
    time by :func:`bridge_deleg_drv_to_agent`) to recover the parent's
    tool_use_id + subagent_type + start timestamp. Parallel-safe:
    SubagentStops are matched by agent_id directly, not by "most-recent"
    heuristics that fail for concurrent delegations.

    Args:
        session_id: Parent session UUID.
        agent_id: The subagent's AgentId from SubagentStop hook input.
        agent_transcript_path: Full path to the subagent's JSONL (from
            SubagentStop ``hook_input.agent_transcript_path``).
        last_assistant_message: Subagent's final response text (from
            SubagentStop ``hook_input.last_assistant_message``).
            Stored as a 200-char preview on the ended event.

    Returns:
        Tuple of (success, duration_seconds, tool_use_id,
        tool_use_id_short, resolved_subagent_type). ``success=False``
        when no bridge event exists for this agent_id (e.g. SA started
        before SubagentStart instrumentation landed).
    """
    from ..event_queries import get_deleg_drv_bridge_by_agent_id

    bridge = get_deleg_drv_bridge_by_agent_id(session_id, agent_id)
    if bridge is None:
        _emit_event("deleg_drv_ended", {
            "session_id": session_id,
            "agent_id": agent_id,
            "agent_type": "unknown",
            "subagent_type": "unknown",
            "duration": 0.0,
            "tool_use_id": "",
            "tool_use_id_short": "",
            "agent_transcript_path": agent_transcript_path,
            "last_assistant_message_preview": last_assistant_message[:200],
            "bridged": False,
        })
        return (False, 0.0, "", "", "unknown")

    started_at = bridge.get("started_at", 0.0)
    tool_use_id = bridge.get("tool_use_id", "")
    tool_use_id_short = bridge.get("tool_use_id_short", "")
    resolved_subagent_type = bridge.get("agent_type", "unknown")

    duration = time.time() - started_at if started_at > 0.0 else 0.0

    _emit_event("deleg_drv_ended", {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_type": resolved_subagent_type,
        "subagent_type": resolved_subagent_type,
        "duration": duration,
        "tool_use_id": tool_use_id,
        "tool_use_id_short": tool_use_id_short,
        "agent_transcript_path": agent_transcript_path,
        "last_assistant_message_preview": last_assistant_message[:200],
        "bridged": True,
    })

    return (True, duration, tool_use_id, tool_use_id_short, resolved_subagent_type)

def complete_deleg_drv(
    session_id: str,
    agent_id: Optional[str] = None,
    subagent_type: Optional[str] = None,
) -> tuple[bool, float, str, str]:
    """
    Mark Delegation Drive completion and update stats (legacy path).

    The preferred path is :func:`complete_deleg_drv_by_agent`, which
    uses the SubagentStart-emitted bridge event to match SubagentStop
    to the right started by agent_id. This function uses the
    "most recent active started" heuristic — adequate for serial
    delegations but unsafe for parallel/concurrent.

    Args:
        session_id: Session identifier.
        agent_id: Unused, kept for API compatibility.
        subagent_type: Optional override. When provided AND not empty/
            "unknown", takes precedence over the started event's value.
            Otherwise the started event's subagent_type is used.

    Returns:
        Tuple of (success, duration_seconds, tool_use_id_short,
        resolved_subagent_type). ``tool_use_id_short`` may be empty if
        the original Start event didn't carry a ``tool_use_id``.
    """
    from ..event_queries import get_active_deleg_drv_start
    started_at, tool_use_id_short, started_subagent_type = get_active_deleg_drv_start(session_id)

    if started_at == 0.0:
        return (False, 0.0, "", "")  # No active drive

    duration = time.time() - started_at

    if subagent_type and subagent_type != "unknown":
        resolved_subagent_type = subagent_type
    elif started_subagent_type:
        resolved_subagent_type = started_subagent_type
    else:
        resolved_subagent_type = "unknown"

    _emit_event("deleg_drv_ended", {
        "session_id": session_id,
        "subagent_type": resolved_subagent_type,
        "duration": duration,
        "tool_use_id_short": tool_use_id_short,
    })

    return (True, duration, tool_use_id_short, resolved_subagent_type)

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
    except Exception as e:
        print(f"⚠️ MACF: deleg drive stats query failed: {e}", file=sys.stderr)
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
    except Exception as e:
        print(f"⚠️ MACF: record_delegation_start failed: {e}", file=sys.stderr)
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
    except Exception as e:
        print(f"⚠️ MACF: record_delegation_complete failed: {e}", file=sys.stderr)
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
    except Exception as e:
        print(f"⚠️ MACF: get_delegations_this_drive failed: {e}", file=sys.stderr)
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
