"""
Cycles utilities.
"""

import os
import time
from pathlib import Path
from typing import Optional, Tuple
from .paths import find_project_root
from .session import get_current_session_id
from .state import load_agent_state, save_agent_state, SessionOperationalState, read_json_safely
# NOTE: event_queries imported lazily inside functions to avoid circular import
# (cycles.py -> event_queries -> agent_events_log -> utils -> cycles.py)

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

        # 4. Event log (previous setting) - EVENT-FIRST: Query events instead of mutable state
        try:
            from ..event_queries import get_auto_mode_from_events
            auto_mode, source, confidence = get_auto_mode_from_events(session_id)
            if source != "default":
                # Only use if it was set explicitly before
                return (auto_mode, "session", 0.5)
        except Exception:
            pass

        # 5. Default
        return (False, "default", 0.0)
    except Exception:
        # NEVER crash
        return (False, "default", 0.0)

def get_agent_cycle_number(agent_root: Optional[Path] = None) -> int:
    """
    Get current cycle number from event log (primary) or agent state (fallback).

    EVENT-FIRST: Queries event log for cycle number. Falls back to agent_state.json
    if no events exist (historical data predating event logging).

    Operates on agent state (.maceff/agent_state.json) which persists
    across sessions and projects (in container) or within project (on host).

    Args:
        agent_root: Agent root path (auto-detected if None)
            Container: Uses Path.home() (agent-scoped)
            Host: Uses find_project_root() (project-scoped)

    Returns:
        Current cycle number (1 if no events or agent state exist)
    """
    try:
        # EVENT-FIRST: Try event log query (lazy import to avoid circular)
        from ..event_queries import get_cycle_number_from_events
        cycle_from_events = get_cycle_number_from_events()
        if cycle_from_events > 0:
            return cycle_from_events

        # FALLBACK: Agent state file (historical data predating event log)
        agent_state = load_agent_state(agent_root)
        return agent_state.get('current_cycle_number', 1)
    except Exception:
        return 1

def increment_agent_cycle(
    session_id: str,
    agent_root: Optional[Path] = None,
    testing: bool = True
) -> int:
    """
    Increment agent cycle number and update session tracking.

    Called by SessionStart hook when compaction detected.
    Operates on agent state which persists across sessions.

    Side effects (ONLY when testing=False):
    - Increments cycle counter in .maceff/agent_state.json
    - Updates cycle_started_at, cycles_completed, last_session_id

    Args:
        session_id: Current session identifier
        agent_root: Agent root path (auto-detected if None)
        testing: If True, return current+1 without mutating state (safe-by-default)

    Returns:
        New cycle number (or current+1 if testing=True, without saving)
    """
    try:
        agent_state = load_agent_state(agent_root)

        # Testing mode: Return what would be the new value, but don't mutate
        if testing:
            current = agent_state.get('current_cycle_number', 1) if agent_state else 1
            return current + 1

        # Production mode: Initialize if empty
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
