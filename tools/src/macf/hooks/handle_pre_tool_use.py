"""
handle_pre_tool_use - PreToolUse hook runner.

DELEG_DRV start tracking + tool operation awareness.
"""
import json
from typing import Dict, Any

from ..utils import (
    get_minimal_timestamp,
    get_current_session_id,
    start_deleg_drv
)


def run(stdin_json: str = "") -> Dict[str, Any]:
    """
    Run PreToolUse hook logic.

    Tracks tool operations with minimal overhead:
    - Task tool: Start DELEG_DRV tracking
    - File operations: Show filename only
    - Bash: Truncate long commands
    - Minimal timestamp for high-frequency hook

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)

    Returns:
        Dict with tool awareness message
    """
    try:
        # Parse hook input
        data = json.loads(stdin_json) if stdin_json else {}

        # Get tool details
        tool_name = data.get("tool_name", "unknown")
        tool_input = data.get("tool_input", {})
        session_id = get_current_session_id()

        # Base temporal message
        timestamp = get_minimal_timestamp()
        message_parts = [f"🏗️ MACF | {timestamp}"]

        # Enhanced context based on tool type
        if tool_name == "Task":
            # DELEG_DRV start tracking
            subagent_type = tool_input.get("subagent_type", "unknown")
            start_deleg_drv(session_id)
            message_parts.append(f"⚡ Delegating to: {subagent_type}")

        elif tool_name in ["Read", "Write", "Edit"]:
            # File operation tracking
            file_path = tool_input.get("file_path", "")
            if file_path:
                # Show just filename for brevity
                filename = file_path.split("/")[-1] if "/" in file_path else file_path
                message_parts.append(f"📄 {tool_name}: {filename}")

        elif tool_name == "Bash":
            # Command tracking (first 40 chars)
            command = tool_input.get("command", "")
            if command:
                short_cmd = command[:40] + "..." if len(command) > 40 else command
                message_parts.append(f"⚙️ {short_cmd}")

        # Format message (single line for user visibility)
        message = " | ".join(message_parts)

        return {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": f"<system-reminder>\n{message}\n</system-reminder>"
            }
        }

    except Exception:
        # Silent failure - never disrupt session
        return {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse"
            }
        }
