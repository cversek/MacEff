#!/usr/bin/env python3
"""
handle_post_tool_use - PostToolUse hook runner.

Silent hook: emits tool_call_completed events for forensics, no message output.
"""
import json
import sys
import traceback
from typing import Dict, Any

from macf.utils import (
    get_current_session_id,
)
from macf.agent_events_log import append_event
from macf.hooks.hook_logging import log_hook_event


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """
    Run PostToolUse hook logic.

    Silent: emits tool_call_completed event for forensics, returns no message.
    PreToolUse handles all user/agent awareness output.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with continue=True (no hookSpecificOutput)
    """
    try:
        # Parse hook input
        data = json.loads(stdin_json) if stdin_json else {}

        # Get tool details
        tool_name = data.get("tool_name", "unknown")
        tool_input = data.get("tool_input", {})
        session_id = get_current_session_id()

        # Append tool_call_completed event
        event_data = {
            "tool": tool_name,
            "session_id": session_id,
            "success": True  # PostToolUse means tool completed (may have errors in output but call completed)
        }

        # Sanitize hook_input: replace large content with size metadata
        sanitized_data = data.copy()
        if "tool_response" in sanitized_data:
            tr = sanitized_data["tool_response"]
            if isinstance(tr, dict) and "stdout" in tr:
                stdout = tr.get("stdout", "")
                if len(stdout) > 500:  # Threshold for "large" content
                    sanitized_data["tool_response"] = {
                        **tr,
                        "stdout": f"[{len(stdout)} bytes]",
                        "stdout_size": len(stdout)
                    }

        append_event(
            event="tool_call_completed",
            data=event_data,
            hook_input=sanitized_data
        )

        # Silent: no message output (PreToolUse handles user/agent awareness)
        return {
            "continue": True,
        }

    except Exception as e:
        # Log error for debugging
        log_hook_event({
            "hook_name": "post_tool_use",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        return {
            "continue": True,
        }



if __name__ == "__main__":
    import json
    import sys
    try:
        output = run(sys.stdin.read())
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"continue": True}))
        print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)

