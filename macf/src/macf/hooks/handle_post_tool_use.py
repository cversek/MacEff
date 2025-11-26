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
from ..agent_events_log import append_event


def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
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
    - c_42: Cycle number from agent_state.json (self-describing prefix)
    - s_abc12345: Session ID (first 8 chars, self-describing prefix)
    - p_def6789: DEV_DRV prompt UUID (last 7 chars) - stable for entire drive
    - No t_ timestamp in PostToolUse (only added when TODO completed)

    Old format (Cycle 40): C40/abc12345/5539d35

    Side effects: None (PostToolUse is read-only, no state mutations)

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        testing: If True (DEFAULT), skip side-effects (safe mode).
                 If False, apply mutations (production only).
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
