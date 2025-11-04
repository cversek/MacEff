"""
handle_pre_tool_use - PreToolUse hook runner.

DELEG_DRV start tracking + tool operation awareness.
"""
import json
from typing import Dict, Any

from ..utils import (
    get_minimal_timestamp,
    get_current_session_id,
    start_deleg_drv,
    get_token_info,
    format_token_context_minimal,
    get_breadcrumb
)


def _is_bare_cd_command(command: str) -> bool:
    """
    Check if command is a bare 'cd' that changes working directory.

    Bare cd is dangerous because it breaks relative hook paths.
    Allow cd in subshells: (cd dir && cmd) or $(cd dir && cmd)

    Args:
        command: Bash command string

    Returns:
        True if bare cd detected, False if safe
    """
    # Strip whitespace
    cmd = command.strip()

    # Check if command starts with 'cd ' (bare cd)
    if cmd.startswith("cd "):
        # Check if it's in a subshell (starts with parenthesis)
        if not cmd.startswith("("):
            return True  # Bare cd detected

    # Check for cd with && (chained commands without subshell)
    # e.g., "cd /path && ls" is still bare cd that changes working dir
    if " && " in cmd:
        # Check if cd appears before && without being in subshell
        parts = cmd.split(" && ")
        first_part = parts[0].strip()
        if first_part.startswith("cd ") and not first_part.startswith("("):
            return True  # Bare cd in chain

    # Safe: no bare cd detected
    return False


def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Run PreToolUse hook logic.

    Tracks tool operations with minimal overhead:
    - Task tool: Start DELEG_DRV tracking
    - File operations: Show filename only
    - Bash: Truncate long commands
    - Minimal timestamp for high-frequency hook

    Side effects (ONLY when testing=False):
    - Starts DELEG_DRV tracking when Task tool invoked
    - Records delegation start timestamp in session state

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        testing: If True (DEFAULT), skip side-effects (read-only safe mode).
                 If False, apply mutations (production only).
        **kwargs: Additional parameters for future extensibility

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

        # Get token info for smoke test
        token_info = get_token_info(session_id)

        # Base temporal message with breadcrumb
        timestamp = get_minimal_timestamp()
        breadcrumb = get_breadcrumb()
        message_parts = [f"🏗️ MACF | {timestamp} | {breadcrumb}"]

        # Enhanced context based on tool type
        if tool_name == "Task":
            # DELEG_DRV start tracking (skip if testing)
            subagent_type = tool_input.get("subagent_type", "unknown")
            if not testing:
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
                # Block bare 'cd' commands that change working directory
                # Allow cd in subshells: (cd dir && cmd) or $(...) contexts
                if _is_bare_cd_command(command):
                    return {
                        "continue": False,
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "message": (
                                "❌ Bare 'cd' command blocked - changes working directory and breaks hook paths.\n"
                                "Use subshell instead: (cd /path && command)\n"
                                "Or use absolute paths without cd."
                            )
                        }
                    }

                short_cmd = command[:40] + "..." if len(command) > 40 else command
                message_parts.append(f"⚙️ {short_cmd}")

        # Format message (single line for user visibility)
        message = " | ".join(message_parts)

        # Add minimal token context (high-frequency hook = minimal overhead)
        token_context_minimal = format_token_context_minimal(token_info)

        return {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": f"<system-reminder>\n{message} | {token_context_minimal}\n</system-reminder>"
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
