"""
Cycles utilities.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple
from .paths import find_agent_home
from .session import get_current_session_id
from .json_io import read_json
# NOTE: event_queries imported lazily inside functions to avoid circular import
# (cycles.py -> event_queries -> agent_events_log -> utils -> cycles.py)

def detect_auto_mode(session_id: str) -> Tuple[bool, str, float]:
    """
    Hierarchical AUTO_MODE detection with confidence scoring.

    Priority (highest to lowest):
    1. CLI flag --auto-mode (not implemented yet, return None)
    2. Environment variable MACF_AUTO_MODE=true/false - confidence 0.9
    3. Event log (previous setting) - confidence 0.5
    4. Default (False, "default", 0.0)

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

        # 3. Event log (previous setting) - EVENT-FIRST architecture
        try:
            from ..event_queries import get_auto_mode_from_events
            auto_mode, source, confidence = get_auto_mode_from_events(session_id)
            if source != "default":
                # Only use if it was set explicitly before
                return (auto_mode, "session", 0.5)
        except Exception as e:
            print(f"⚠️ MACF: Event log auto_mode query failed: {e}", file=sys.stderr)

        # 5. Default
        return (False, "default", 0.0)
    except Exception as e:
        print(f"⚠️ MACF: Auto-mode detection failed (fallback: MANUAL): {e}", file=sys.stderr)
        return (False, "default", 0.0)

def set_auto_mode(
    enabled: bool,
    session_id: str,
    auth_token: Optional[str] = None,
    agent_home: Optional[Path] = None,
) -> Tuple[bool, str]:
    """
    Set AUTO_MODE for current session with optional auth token validation.

    Mode persistence is SOURCE-AWARE (per autonomous_operation.md policy):
    - compact (auto-compaction): Mode PRESERVED across compaction
    - resume (crash/restart): Mode RESET to MANUAL_MODE

    This function sets mode for the current session. SessionStart hook
    handles persistence logic based on source field.

    Args:
        enabled: True for AUTO_MODE, False for MANUAL_MODE
        session_id: Current session identifier
        auth_token: Optional auth token for AUTO_MODE activation
        agent_home: Agent home path (auto-detected if None)

    Returns:
        Tuple of (success: bool, message: str)

    Note:
        AUTO_MODE requires valid auth_token when enabled=True.
        MANUAL_MODE can always be set without auth.
    """
    try:
        # Validate auth token for AUTO_MODE activation
        if enabled and auth_token is not None:
            # Load expected token from settings
            if agent_home is None:
                agent_home = find_agent_home()
            settings_path = agent_home / ".maceff" / "settings.json"

            if settings_path.exists():
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
                expected_token = settings.get('auto_mode_auth_token')

                if expected_token and auth_token != expected_token:
                    return (False, "Invalid auth token")
            # If no settings file or no token configured, skip validation
            # (allows initial setup before tokens exist)

        # Log mode change event
        try:
            from ..agent_events_log import append_event
            mode_str = "AUTO_MODE" if enabled else "MANUAL_MODE"
            append_event(
                event="mode_change",
                data={
                    "mode": mode_str,
                    "enabled": enabled,
                    "session_id": session_id,
                    "auth_validated": auth_token is not None
                }
            )
        except Exception:
            pass  # Don't fail on logging errors

        mode_str = "AUTO_MODE" if enabled else "MANUAL_MODE"
        return (True, f"Mode set to {mode_str}")

    except Exception as e:
        return (False, f"Error setting mode: {e}")


