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
from macf.agent_events_log import append_event, elide_large_values
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

        # Replace oversized values with their size before the event is written.
        #
        # This used to test whether tool_response was a dict containing
        # "stdout" — the shape one tool happens to return. Measured against a
        # real log that predicate fired on 70% of records and caught 1.7% of the
        # bytes: every other tool's response walked past it, and a single field
        # holding whole-file content accounted for most of the remainder.
        # elide_large_values tests size instead, which no unanticipated payload
        # shape can escape.
        append_event(
            event="tool_call_completed",
            data=event_data,
            hook_input=elide_large_values(data)
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

