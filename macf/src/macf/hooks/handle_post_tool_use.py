"""
handle_post_tool_use - PostToolUse hook runner.

Tool completion awareness + TodoWrite tracking.
"""
import json
from typing import Dict, Any

from ..utils import (
    get_minimal_timestamp,
    get_current_session_id,
    SessionOperationalState,
    get_token_info,
    format_token_context_minimal
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
    - Stable breadcrumb: C{cycle}/{session_short}/{prompt_short}
    - Minimal token context (CLUAC indicator)

    Breadcrumb format: C60/4107604e/5539d35
    - Cycle number from state
    - Session ID (first 8 chars)
    - DEV_DRV prompt UUID (last 7 chars) - stable for entire drive

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

        # Load session state for DEV_DRV prompt UUID
        state = SessionOperationalState.load(session_id)

        # Load agent state for cycle number (persists across sessions)
        from pathlib import Path
        from ..utils import read_json_safely, find_project_root
        project_root = find_project_root()
        agent_state_path = project_root / ".maceff" / "agent_state.json" if project_root else None
        agent_state = read_json_safely(agent_state_path) if agent_state_path else {}
        cycle_num = agent_state.get("current_cycle_number", 1)

        # Base temporal message
        timestamp = get_minimal_timestamp()

        # Build stable breadcrumb from agent + session state
        # Format: C{cycle}/{session_short}/{prompt_short}
        session_short = session_id[:8] if session_id else "unknown"
        prompt_uuid = state.current_dev_drv_prompt_uuid
        prompt_short = prompt_uuid[-7:] if prompt_uuid else "none"
        breadcrumb = f"C{cycle_num}/{session_short}/{prompt_short}"

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
