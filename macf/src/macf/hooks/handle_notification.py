"""
handle_notification - Notification hook runner.

Tracks Claude Code notifications (permission prompts, idle prompts, auth success, etc.).
"""
import json
import traceback
from typing import Dict, Any

from ..utils import (
    get_minimal_timestamp,
    get_current_session_id,
    get_breadcrumb
)
from ..agent_events_log import append_event
from .logging import log_hook_event


def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Run Notification hook logic.

    Tracks Claude Code notifications for forensic reconstruction.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        testing: If True (DEFAULT), skip side-effects (read-only safe mode).
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with notification acknowledgment
    """
    try:
        # Parse hook input
        data = json.loads(stdin_json) if stdin_json else {}

        # Get session context
        session_id = get_current_session_id()

        # Extract notification details
        notification_type = data.get("type", "unknown")
        message_content = data.get("message", "")

        # Truncate long messages
        MAX_MSG_LEN = 200
        msg_truncated = message_content[:MAX_MSG_LEN]
        if len(message_content) > MAX_MSG_LEN:
            msg_truncated += f" [...{len(message_content)} chars]"

        # Append notification_received event
        import time
        append_event(
            event="notification_received",
            data={
                "session_id": session_id,
                "notification_type": notification_type,
                "message_preview": msg_truncated,
                "timestamp": time.time()
            },
            hook_input=data
        )

        # Format message (Pattern C: top-level for user + hookSpecificOutput for agent)
        timestamp = get_minimal_timestamp()
        breadcrumb = get_breadcrumb()
        message = f"🏗️ MACF | {timestamp} | {breadcrumb} | 📢 Notification: {notification_type}"

        return {
            "continue": True,
            "systemMessage": message,  # User sees this
            "hookSpecificOutput": {
                "hookEventName": "Notification",
                "additionalContext": f"<system-reminder>\n{message}\n</system-reminder>"
            }
        }

    except Exception as e:
        # Log error for debugging
        log_hook_event({
            "hook_name": "notification",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        return {
            "continue": True,
            "systemMessage": f"🏗️ MACF | ❌ Notification hook error: {e}"
        }
