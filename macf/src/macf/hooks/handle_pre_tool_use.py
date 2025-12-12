#!/usr/bin/env python3
"""
handle_pre_tool_use - PreToolUse hook runner.

DELEG_DRV start tracking + tool operation awareness.
"""
import json
import traceback
from typing import Dict, Any

from macf.utils import (
    get_minimal_timestamp,
    get_current_session_id,
    start_deleg_drv,
    get_token_info,
    format_token_context_minimal,
    get_breadcrumb,
    detect_auto_mode
)
from macf.agent_events_log import append_event
from macf.hooks.hook_logging import log_hook_event


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

        # Append tool_call_started event
        event_data = {
            "tool": tool_name,
            "session_id": session_id
        }
        # Add file_path if it's a file operation
        if "file_path" in tool_input:
            event_data["file_path"] = tool_input["file_path"]

        append_event(
            event="tool_call_started",
            data=event_data,
            hook_input=data
        )

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
            description = tool_input.get("description", "")
            prompt = tool_input.get("prompt", "")
            if not testing:
                start_deleg_drv(session_id)

            # Truncate long fields for event log (similar to tool output handling)
            MAX_DESC_LEN = 100
            MAX_PROMPT_LEN = 500
            desc_truncated = description[:MAX_DESC_LEN] + f" [...{len(description)} chars]" if len(description) > MAX_DESC_LEN else description
            prompt_truncated = prompt[:MAX_PROMPT_LEN] + f" [...{len(prompt)} chars]" if len(prompt) > MAX_PROMPT_LEN else prompt

            # Append delegation_started event for forensic reconstruction
            append_event(
                event="delegation_started",
                data={
                    "session_id": session_id,
                    "subagent_type": subagent_type,
                    "description": desc_truncated,
                    "prompt_preview": prompt_truncated
                },
                hook_input=data
            )
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
                # Mode-aware bare cd detection (per autonomous_operation.md policy)
                # AUTO_MODE: warn but continue (safeguards warn, don't block)
                # MANUAL_MODE: block violation
                if _is_bare_cd_command(command):
                    auto_mode, _, _ = detect_auto_mode(session_id)
                    violation_msg = (
                        "Bare 'cd' command detected - changes working directory and breaks hook paths.\n"
                        "Use subshell instead: (cd /path && command)\n"
                        "Or use absolute paths without cd."
                    )
                    if auto_mode:
                        # AUTO_MODE: warn but continue
                        message_parts.append(f"⚠️ {violation_msg}")
                    else:
                        # MANUAL_MODE: block
                        return {
                            "continue": False,
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "message": f"❌ {violation_msg}"
                            }
                        }

                short_cmd = command[:40] + "..." if len(command) > 40 else command
                message_parts.append(f"⚙️ {short_cmd}")

        # Format message (single line for user visibility)
        message = " | ".join(message_parts)

        # Add minimal token context (high-frequency hook = minimal overhead)
        token_context_minimal = format_token_context_minimal(token_info)

        # Pattern C: top-level systemMessage for user + hookSpecificOutput for agent
        user_message = f"{message} | {token_context_minimal}"
        return {
            "continue": True,
            "systemMessage": user_message,  # TOP LEVEL - user sees this
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": f"<system-reminder>\n{user_message}\n</system-reminder>"
            }
        }

    except Exception as e:
        # Log error for debugging
        log_hook_event({
            "hook_name": "pre_tool_use",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        error_msg = f"🏗️ MACF | ❌ PreToolUse hook error: {e}"
        return {
            "continue": True,
            "systemMessage": error_msg,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": f"<system-reminder>\n{error_msg}\n</system-reminder>"
            }
        }



if __name__ == "__main__":
    import json
    import sys
    try:
        output = run(sys.stdin.read(), testing=False)
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"continue": True}))
        print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)

