"""
Drives utilities.
"""

import time
from typing import Any, Dict, List, Optional
from .session import get_last_user_prompt_uuid
from .state import SessionOperationalState

def start_dev_drv(session_id: str, agent_id: Optional[str] = None, prompt_uuid: Optional[str] = None) -> bool:
    """
    Mark Development Drive start.

    DEV_DRV = period from user plan approval/UserPromptSubmit to Stop hook.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (auto-detected if None)
        prompt_uuid: Prompt UUID (auto-detected from JSONL if None)

    Returns:
        True if successful, False otherwise
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)
    state.current_dev_drv_started_at = time.time()

    # Use provided UUID or capture from JSONL
    if prompt_uuid is None:
        prompt_uuid = get_last_user_prompt_uuid(session_id)
    state.current_dev_drv_prompt_uuid = prompt_uuid

    return state.save()

def complete_dev_drv(session_id: str, agent_id: Optional[str] = None) -> tuple[bool, float]:
    """
    Mark Development Drive completion and update stats.

    Returns:
        Tuple of (success: bool, duration_seconds: float)
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    if state.current_dev_drv_started_at is None:
        return (False, 0.0)

    # Calculate duration
    duration = time.time() - state.current_dev_drv_started_at

    # Update stats
    state.dev_drv_count += 1
    state.total_dev_drv_duration += duration

    # Clear current drive tracking
    state.current_dev_drv_started_at = None
    state.current_dev_drv_prompt_uuid = None

    success = state.save()
    return (success, duration)

def get_dev_drv_stats(session_id: str, agent_id: Optional[str] = None) -> dict:
    """
    Get current Development Drive statistics.

    Returns:
        Dict with keys: count, total_duration, current_started_at, avg_duration
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    avg_duration = 0.0
    if state.dev_drv_count > 0:
        avg_duration = state.total_dev_drv_duration / state.dev_drv_count

    return {
        "count": state.dev_drv_count,
        "total_duration": state.total_dev_drv_duration,
        "current_started_at": state.current_dev_drv_started_at,
        "prompt_uuid": state.current_dev_drv_prompt_uuid,
        "avg_duration": avg_duration
    }

def start_deleg_drv(session_id: str, agent_id: Optional[str] = None) -> bool:
    """
    Mark Delegation Drive start.

    DELEG_DRV = period from Task tool invocation to SubagentStop hook.

    Returns:
        True if successful, False otherwise
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)
    state.current_deleg_drv_started_at = time.time()
    return state.save()

def complete_deleg_drv(session_id: str, agent_id: Optional[str] = None) -> tuple[bool, float]:
    """
    Mark Delegation Drive completion and update stats.

    Returns:
        Tuple of (success: bool, duration_seconds: float)
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    if state.current_deleg_drv_started_at is None:
        return (False, 0.0)

    # Calculate duration
    duration = time.time() - state.current_deleg_drv_started_at

    # Update stats
    state.deleg_drv_count += 1
    state.total_deleg_drv_duration += duration
    state.current_deleg_drv_started_at = None  # Clear current

    success = state.save()
    return (success, duration)

def get_deleg_drv_stats(session_id: str, agent_id: Optional[str] = None) -> dict:
    """
    Get current Delegation Drive statistics.

    Returns:
        Dict with keys: count, total_duration, current_started_at, avg_duration
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    avg_duration = 0.0
    if state.deleg_drv_count > 0:
        avg_duration = state.total_deleg_drv_duration / state.deleg_drv_count

    return {
        "count": state.deleg_drv_count,
        "total_duration": state.total_deleg_drv_duration,
        "current_started_at": state.current_deleg_drv_started_at,
        "avg_duration": avg_duration
    }

def record_delegation_start(
    session_id: str,
    tool_use_uuid: str,
    subagent_type: str,
    agent_id: Optional[str] = None
) -> bool:
    """
    Record delegation start in session state.

    Args:
        session_id: Session identifier
        tool_use_uuid: Task tool_use_id for JSONL sidechain lookup
        subagent_type: Type of subagent (e.g., "devops-eng", "test-eng")
        agent_id: Agent identifier (auto-detected if None)

    Returns:
        True if recorded successfully, False otherwise
    """
    try:
        state = SessionOperationalState.load(session_id, agent_id)

        delegation = {
            "tool_use_uuid": tool_use_uuid,
            "subagent_type": subagent_type,
            "started_at": time.time(),
            "completed_at": None,
            "duration": None
        }

        state.delegations_this_drive.append(delegation)
        return state.save()
    except Exception:
        return False

def record_delegation_complete(
    session_id: str,
    tool_use_uuid: str,
    duration: float,
    agent_id: Optional[str] = None
) -> bool:
    """
    Mark delegation as complete with duration.

    Args:
        session_id: Session identifier
        tool_use_uuid: Task tool_use_id to match
        duration: Duration in seconds
        agent_id: Agent identifier (auto-detected if None)

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        state = SessionOperationalState.load(session_id, agent_id)

        # Find matching delegation by UUID
        for deleg in state.delegations_this_drive:
            if deleg['tool_use_uuid'] == tool_use_uuid:
                deleg['completed_at'] = time.time()
                deleg['duration'] = duration
                return state.save()

        # UUID not found - still return True (safe failure)
        return True
    except Exception:
        return False

def get_delegations_this_drive(
    session_id: str,
    agent_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all delegations for current DEV_DRV.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (auto-detected if None)

    Returns:
        List of delegation dicts (empty list on failure)
    """
    try:
        state = SessionOperationalState.load(session_id, agent_id)
        return state.delegations_this_drive
    except Exception:
        return []

def clear_delegations_this_drive(
    session_id: str,
    agent_id: Optional[str] = None
) -> bool:
    """
    Clear delegation list (called after DEV_DRV Complete reporting).

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (auto-detected if None)

    Returns:
        True if cleared successfully, False otherwise
    """
    try:
        state = SessionOperationalState.load(session_id, agent_id)
        state.delegations_this_drive = []
        return state.save()
    except Exception:
        return False
