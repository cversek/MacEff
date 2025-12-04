"""
Hook logging infrastructure with unified agent-scoped paths.

All logging uses /tmp/macf/{agent_id}/{session_id}/hooks/
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Import from centralized utils
from macf.utils import (
    get_current_session_id,
    get_hooks_dir,
    get_formatted_timestamp
)
from macf.config import ConsciousnessConfig


def log_hook_event(
    event_data: dict,
    raw_input: Optional[dict] = None
) -> None:
    """
    Log structured event to hooks/hook_events.log.

    Args:
        event_data: Event information with fields:
            - hook_name: str
            - event_type: str (HOOK_START, HOOK_COMPLETE, HOOK_ERROR, etc.)
            - session_id: str (optional, auto-detected)
            - agent_id: str (optional, auto-detected)
        raw_input: Complete raw JSON from stdin (optional, for START events)

    Event written as single-line JSON (JSONL format) with:
    - ISO 8601 timestamp with timezone
    - Agent and session identification
    - Duration timing when available
    """
    try:
        # Get required fields
        hook_name = event_data.get("hook_name", "unknown")
        event_type = event_data.get("event_type", "UNKNOWN")

        # Get session_id (auto-detect if not provided)
        session_id = event_data.get("session_id")
        if not session_id or session_id == "unknown":
            session_id = get_current_session_id()

        # Get agent_id (auto-detect if not provided)
        agent_id = event_data.get("agent_id")
        if not agent_id:
            try:
                config = ConsciousnessConfig()
                agent_id = config.agent_id
            except Exception:
                agent_id = 'unknown_agent'

        # Get hooks directory using unified path
        hooks_dir = get_hooks_dir(session_id, create=True)
        if not hooks_dir:
            return  # Silent failure

        log_file = hooks_dir / "hook_events.log"

        # Build log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hook_name": hook_name,
            "event_type": event_type,
            "session_id": session_id,
            "agent_id": agent_id,
            **event_data  # Merge all other fields
        }

        # Add raw_input only for START events (reduce redundancy)
        if raw_input and event_type == "HOOK_START":
            log_entry["raw_input"] = raw_input

        # Write as single-line JSON (JSONL)
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

    except Exception as e:
        # Silent failure - never disrupt hook execution
        print(f"Logging error: {e}", file=sys.stderr)


def setup_hook_logger(hook_name: str, session_id: str) -> logging.Logger:
    """
    Configure Python logger for hook with file and stderr handlers.

    Args:
        hook_name: Name of the hook
        session_id: Session identifier

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(f"macf.hooks.{hook_name}")
    logger.setLevel(logging.INFO)

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler (stderr only)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler in hooks/ subdirectory
    try:
        hooks_dir = get_hooks_dir(session_id, create=True)
        if hooks_dir:
            file_handler = logging.FileHandler(
                hooks_dir / f"{hook_name}.log",
                mode='a'
            )
            file_handler.setLevel(logging.INFO)
            file_formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
    except Exception:
        pass  # Silent failure on file handler

    return logger