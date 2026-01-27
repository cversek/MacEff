#!/usr/bin/env python3
"""
handle_pre_tool_use - PreToolUse hook runner.

DELEG_DRV start tracking + tool operation awareness.
"""
import json
import sys
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


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """
    Run PreToolUse hook logic.

    Tracks tool operations with minimal overhead:
    - Task tool: Start DELEG_DRV tracking
    - File operations: Show filename only
    - Bash: Truncate long commands
    - Minimal timestamp for high-frequency hook

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
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

        # TaskCreate protection: MISSION/EXPERIMENT/DETOUR require plan_ca_ref
        if tool_name == "TaskCreate":
            from macf.task.protection import check_task_create, check_grant_in_events

            subject = tool_input.get("subject", "")
            description = tool_input.get("description", "")
            auto_mode_flag, _, _ = detect_auto_mode(session_id)

            result = check_task_create(subject, description, auto_mode_flag)

            if not result.allowed:
                # Check for grant
                has_grant, _ = check_grant_in_events("create")
                if not has_grant:
                    error_msg = (
                        f"❌ TaskCreate Blocked - {result.reason}\n\n"
                        f"{result.grant_hint or ''}"
                    )
                    return {
                        "continue": False,
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": error_msg
                        }
                    }

            message_parts.append(f"📝 TaskCreate: {subject[:40]}...")

        # TaskUpdate protection: description modifications require grant (with exceptions)
        elif tool_name == "TaskUpdate":
            from macf.task.protection import check_task_update_description, check_grant_in_events, clear_grant
            from macf.task.reader import TaskReader

            task_id_str = tool_input.get("taskId", "")
            new_description = tool_input.get("description")

            # Only check if description is being updated
            if new_description is not None:
                try:
                    task_id = int(task_id_str)
                    auto_mode_flag, _, _ = detect_auto_mode(session_id)

                    # Get current task description
                    reader = TaskReader()
                    current_task = None
                    for task in reader.read_tasks():
                        if task.id == task_id:
                            current_task = task
                            break

                    if current_task:
                        # Check for grant
                        has_grant, grant_event = check_grant_in_events("update", task_id)

                        result = check_task_update_description(
                            task_id,
                            current_task.description,
                            new_description,
                            auto_mode_flag,
                            has_grant
                        )

                        if not result.allowed:
                            error_msg = (
                                f"❌ TaskUpdate Blocked - {result.reason}\n\n"
                                f"{result.grant_hint or ''}"
                            )
                            return {
                                "continue": False,
                                "hookSpecificOutput": {
                                    "hookEventName": "PreToolUse",
                                    "permissionDecision": "deny",
                                    "permissionDecisionReason": error_msg
                                }
                            }

                        # Clear grant if it was used
                        if has_grant and result.level.value == "HIGH":
                            clear_grant("update", task_id, "consumed_by_taskupdate")

                except (ValueError, TypeError):
                    pass  # Invalid task_id, let CC handle the error

            message_parts.append(f"📝 TaskUpdate: #{task_id_str}")

        # Enhanced context based on tool type
        elif tool_name == "Task":
            # DELEG_DRV start tracking
            subagent_type = tool_input.get("subagent_type", "unknown")
            description = tool_input.get("description", "")
            prompt = tool_input.get("prompt", "")
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

                    # Truncate command for display
                    cmd_preview = command[:80] + "..." if len(command) > 80 else command

                    violation_msg = (
                        f"❌ Bare 'cd' Command Blocked\n\n"
                        f"Command: {cmd_preview}\n\n"
                        f"⚠️ Bare 'cd' changes working directory and breaks relative hook paths.\n\n"
                        f"✅ Alternatives that work:\n"
                        f"  1. Subshell: (cd /path && command)\n"
                        f"  2. Absolute paths: pytest /full/path/to/tests\n"
                        f"  3. Tool flags: git -C /path status\n\n"
                        f"Simply wrap in subshell or use absolute paths, then retry."
                    )

                    if auto_mode:
                        # AUTO_MODE: warn but continue
                        message_parts.append(f"⚠️ Bare cd detected - use subshell or absolute paths")
                    else:
                        # MANUAL_MODE: Use permissionDecision pattern (like TodoWrite)
                        # This shows as permission dialog, not scary "Error:"
                        return {
                            "continue": False,
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "deny",
                                "permissionDecisionReason": violation_msg
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
        output = run(sys.stdin.read())
        # Exit code 2 is the ONLY way to block tool execution in Claude Code
        # JSON "continue": false is ignored due to known bugs (#4362, #4669, #3514)
        # When blocking: NO stdout JSON, ONLY stderr message + exit 2
        if not output.get("continue", True):
            # Check if using permissionDecision (needs JSON output, exit 0)
            hook_output = output.get("hookSpecificOutput", {})
            if hook_output.get("permissionDecision") == "deny":
                # permissionDecision requires JSON on stdout, exit 0
                print(json.dumps(output))
                sys.exit(0)
            else:
                # Exit 2 blocks without dialog, stderr shown (works for Bash)
                message = output.get("systemMessage") or hook_output.get("message", "Tool blocked by PreToolUse hook")
                print(message, file=sys.stderr)
                sys.exit(2)
        # Only print JSON for non-blocking cases
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"continue": True}))
        print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)

