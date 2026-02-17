#!/usr/bin/env python3
"""
handle_post_tool_use - PostToolUse hook runner.

Tool completion awareness + TodoWrite tracking.
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

    Tracks tool completions with minimal overhead:
    - Task tool: Show delegation completion
    - File operations: Show filename only
    - Bash: Truncate long commands
    - Grep/Glob: Show search patterns
    - TodoWrite: Count status summary
    - Minimal timestamp for high-frequency hook
    - Stable breadcrumb (enhanced format)
    - Minimal token context (CLUAC indicator)

    Enhanced breadcrumb format (Cycle 42+): c_42/s_abc12345/p_def6789
    - c_42: Cycle number from event log (self-describing prefix)
    - s_abc12345: Session ID (first 8 chars, self-describing prefix)
    - p_def6789: DEV_DRV prompt UUID (last 7 chars) - stable for entire drive
    - No t_ timestamp in PostToolUse (only added when TODO completed)

    Old format (Cycle 40): C40/abc12345/5539d35

    Side effects: None (PostToolUse is read-only, no state mutations)

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
                 Currently no side-effects in PostToolUse.
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with tool completion message including stable breadcrumb
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

