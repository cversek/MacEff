"""
handle_post_tool_use - PostToolUse hook runner.

Tool completion awareness + TodoWrite tracking.
"""
import json
from typing import Dict, Any

from ..utils import (
    get_minimal_timestamp,
    get_current_session_id,
    get_token_info,
    format_token_context_minimal,
    get_breadcrumb
)


def run(stdin_json: str = "") -> Dict[str, Any]:
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

    Enhanced breadcrumb format (Cycle 61+): c_61/s_4107604e/p_b037708
    - c_61: Cycle number from agent_state.json (self-describing prefix)
    - s_4107604e: Session ID (first 8 chars, self-describing prefix)
    - p_b037708: DEV_DRV prompt UUID (last 7 chars) - stable for entire drive
    - No t_ timestamp in PostToolUse (only added when TODO completed)

    Old format (Cycle 60): C60/4107604e/5539d35

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)

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

        # Base temporal message
        timestamp = get_minimal_timestamp()

        # Get full 5-component breadcrumb (auto-gathered)
        breadcrumb = get_breadcrumb()

        # Token awareness (minimal for high-frequency hook)
        token_info = get_token_info(session_id)
        token_context_minimal = format_token_context_minimal(token_info)

        message_parts = [f"🏗️ MACF | {timestamp} | {breadcrumb}"]

        # Enhanced context based on tool type
        if tool_name == "Task":
            # Show delegation completion
            subagent_type = tool_input.get("subagent_type", "unknown")
            message_parts.append(f"✅ Delegated to: {subagent_type}")

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

        elif tool_name in ["Grep", "Glob"]:
            # Search operation tracking
            pattern = tool_input.get("pattern", "")
            if pattern:
                # Show pattern (truncate if long)
                short_pattern = pattern[:30] + "..." if len(pattern) > 30 else pattern
                message_parts.append(f"🔍 {tool_name}: '{short_pattern}'")

        elif tool_name == "TodoWrite":
            # Todo list operations
            todos = tool_input.get("todos", [])
            if todos:
                # Count by status
                pending = sum(1 for t in todos if t.get("status") == "pending")
                in_progress = sum(1 for t in todos if t.get("status") == "in_progress")
                completed = sum(1 for t in todos if t.get("status") == "completed")
                message_parts.append(f"📝 Todos: {completed}✅ {in_progress}🔄 {pending}⏳")

        # Format message (single line for user visibility)
        message = " | ".join(message_parts)

        # Append token context
        message = f"{message} | {token_context_minimal}"

        return {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"<system-reminder>\n{message}\n</system-reminder>"
            }
        }

    except Exception:
        # Silent failure - never disrupt session
        return {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse"
            }
        }
