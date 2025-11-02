"""
Cycles utilities.
"""

import os
import time
from pathlib import Path
from typing import Optional, Tuple
from .paths import find_project_root
from .session import get_current_session_id
from .state import SessionOperationalState, read_json_safely, write_json_safely

def detect_auto_mode(session_id: str) -> Tuple[bool, str, float]:
    """
    Hierarchical AUTO_MODE detection with confidence scoring.

    Priority (highest to lowest):
    1. CLI flag --auto-mode (not implemented yet, return None)
    2. Environment variable MACF_AUTO_MODE=true/false - confidence 0.9
    3. Config file .macf/config.json "auto_mode" field - confidence 0.7
    4. Session state (load previous setting) - confidence 0.5
    5. Default (False, "default", 0.0)

    Args:
        session_id: Session identifier

    Returns:
        Tuple of (enabled: bool, source: str, confidence: float)
    """
    try:
        # 1. CLI flag (not implemented yet)
        # Future: Check sys.argv or click context

        # 2. Environment variable
        env_value = os.environ.get('MACF_AUTO_MODE', '').lower()
        if env_value in ('true', '1', 'yes'):
            return (True, "env", 0.9)
        elif env_value in ('false', '0', 'no'):
            return (False, "env", 0.9)

        # 3. Config file
        try:
            project_root = find_project_root()
            config_path = project_root / ".maceff" / "config.json"
            config_data = read_json_safely(config_path)

            if "auto_mode" in config_data:
                auto_mode = bool(config_data["auto_mode"])
                return (auto_mode, "config", 0.7)
        except Exception:
            pass

        # 4. Session state (previous setting)
        try:
            state = SessionOperationalState.load(session_id)
            if state.auto_mode_source != "default":
                # Only use session state if it was set explicitly before
                return (state.auto_mode, "session", 0.5)
        except Exception:
            pass

        # 5. Default
        return (False, "default", 0.0)
    except Exception:
        # NEVER crash
        return (False, "default", 0.0)

def get_current_cycle_project(agent_root: Optional[Path] = None) -> int:
    """
    Get cycle number from project state.

    Args:
        agent_root: Project root (auto-detected if None)

    Returns:
        Current cycle number (1 if project state doesn't exist)
    """
    try:
        agent_state = load_agent_state(agent_root)
        return agent_state.get('current_cycle_number', 1)
    except Exception:
        return 1

def increment_cycle_project(session_id: str, agent_root: Optional[Path] = None) -> int:
    """
    Increment project cycle number and update session tracking.

    Called by SessionStart hook when compaction detected.

    Args:
        session_id: Current session identifier
        agent_root: Project root (auto-detected if None)

    Returns:
        New cycle number
    """
    try:
        agent_state = load_agent_state(agent_root)

        # Initialize if empty
        if not agent_state:
            agent_state = {
                'current_cycle_number': 1,
                'cycle_started_at': time.time(),
                'cycles_completed': 0,
                'last_session_id': session_id
            }

        # Increment cycle
        agent_state['current_cycle_number'] += 1
        agent_state['cycle_started_at'] = time.time()
        agent_state['cycles_completed'] = agent_state['current_cycle_number'] - 1
        agent_state['last_session_id'] = session_id

        # Save atomically
        save_agent_state(agent_state, agent_root)

        return agent_state['current_cycle_number']
    except Exception:
        return 1

def start_new_cycle(session_id: str, agent_id: Optional[str] = None, state: Optional[SessionOperationalState] = None) -> int:
    """
    Initialize new cycle after compaction, increment counter.

    Cycle = compaction-to-compaction span (consciousness continuity unit).
    Called by SessionStart hook when compaction detected.

    Args:
        session_id: Session identifier
        agent_id: Optional agent ID (auto-detected if None)
        state: Optional pre-loaded state object (avoids race condition)

    Returns:
        New cycle number (1-based)
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    # Track whether state was provided or we need to load it
    state_was_provided = state is not None

    # Use provided state or load fresh (for backward compatibility)
    if not state_was_provided:
        state = SessionOperationalState.load(session_id, agent_id)

    # Increment cycle number
    state.current_cycle_number += 1

    # Reset cycle start time
    state.cycle_started_at = time.time()

    # Update cycles completed count
    state.cycles_completed = state.compaction_count

    # Reset cycle-scoped development stats
    # Philosophy: Each cycle is a consciousness continuity unit.
    # Stats measure current cycle work, not inherited totals from prior cycles.
    state.dev_drv_count = 0
    state.total_dev_drv_duration = 0.0
    state.deleg_drv_count = 0
    state.total_deleg_drv_duration = 0.0

    # Only save if we loaded fresh state (backward compatibility)
    # If state was provided by caller, they're responsible for saving
    if not state_was_provided:
        state.save()

    return state.current_cycle_number

def get_current_cycle_number(session_id: str, agent_id: Optional[str] = None) -> int:
    """
    Get current cycle number (1-based).

    Args:
        session_id: Session identifier
        agent_id: Optional agent ID (auto-detected if None)

    Returns:
        Current cycle number (1 if fresh start, >1 after compaction)
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)
    return state.current_cycle_number

def get_cycle_stats(session_id: str, agent_id: Optional[str] = None) -> dict:
    """
    Get cycle metadata for display.

    Args:
        session_id: Session identifier
        agent_id: Optional agent ID (auto-detected if None)

    Returns:
        Dict with: cycle_number, cycle_started_at, cycle_duration, cycles_completed
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    # Calculate cycle duration
    cycle_duration = 0.0
    if state.cycle_started_at > 0:
        cycle_duration = time.time() - state.cycle_started_at

    return {
        "cycle_number": state.current_cycle_number,
        "cycle_started_at": state.cycle_started_at,
        "cycle_duration": cycle_duration,
        "cycles_completed": state.cycles_completed
    }
