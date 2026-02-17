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
from macf.event_queries import get_active_policy_injections_from_events
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

        # Build policy injection content (if any active injections)
        # DESIGN: One-shot injection — policies fire ONCE then auto-clear.
        # additionalContext persists in CC message history forever, so
        # re-injection is unnecessary and would create redundant copies.
        # Proxy message_rewriter handles dedup as safety net.
        injection_content = ""
        injection_errors = []
        injected_policies = []  # Track successful injections for auto-clear
        active_injections = get_active_policy_injections_from_events()
        for inj in active_injections:
            policy_path = inj.get("policy_path", "")
            policy_name = inj.get("policy_name", "unknown")
            if policy_path:
                from pathlib import Path
                p = Path(policy_path)
                if p.exists():
                    try:
                        policy_text = p.read_text()
                        # Extract CEP Navigation Guide only (above boundary marker)
                        # Full policy available via: macf_tools policy read <name>
                        boundary = "=== CEP_NAV_BOUNDARY ==="
                        if boundary in policy_text:
                            policy_text = policy_text[:policy_text.index(boundary)].rstrip()
                        injection_content += f'<macf-policy-nav-guide-injection policy="{policy_name}">\n{policy_text}\n</macf-policy-nav-guide-injection>\n'
                        injected_policies.append(policy_name)
                    except Exception as e:
                        injection_errors.append(f"{policy_name}: {e}")
                else:
                    injection_errors.append(f"{policy_name}: file not found at {policy_path}")

        # Auto-clear after injection fires (all sources treated equally)
        for policy_name in injected_policies:
            append_event(
                event="policy_injection_cleared",
                data={
                    "policy_name": policy_name,
                    "reason": "auto_clear_after_fire",
                    "session_id": session_id
                }
            )

        # Base temporal message with breadcrumb
        timestamp = get_minimal_timestamp()
        breadcrumb = get_breadcrumb()
        message_parts = [f"🏗️ MACF | {timestamp} | {breadcrumb}"]

        # Surface any injection errors to user
        if injection_errors:
            message_parts.append(f"❌ Policy injection errors: {'; '.join(injection_errors)}")

        # TaskCreate DENIED - redirect to CLI
        if tool_name == "TaskCreate":
            subject = tool_input.get("subject", "")
            error_msg = (
                "❌ TaskCreate Blocked - Use CLI commands instead\n\n"
                "The CLI embeds business logic (MTMD, breadcrumbs, folder creation).\n"
                "Native TaskCreate is a primitive that misses framework requirements.\n\n"
                "✅ Use these commands instead:\n"
                "  macf_tools task create mission \"Title\"      # MISSION with roadmap\n"
                "  macf_tools task create experiment \"Title\"   # EXPERIMENT with protocol\n"
                "  macf_tools task create detour \"Title\"       # DETOUR for urgent work\n"
                "  macf_tools task create phase --parent N \"Title\"  # Phase under parent\n"
                "  macf_tools task create bug --parent N \"Title\"    # Bug under parent\n"
                "  macf_tools task create task \"Title\"         # Standalone task\n\n"
                "📚 For guidance: macf_tools policy navigate task_management"
            )
            return {
                "continue": False,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": error_msg
                }
            }

        # TaskUpdate DENIED - redirect to CLI
        elif tool_name == "TaskUpdate":
            task_id_str = tool_input.get("taskId", "")
            status = tool_input.get("status")

            # Build context-aware redirect message
            if status == "completed":
                hint = (
                    "✅ For completion, use:\n"
                    f"  macf_tools task complete #{task_id_str} --report \"Work done. Difficulties. Committed: hash\""
                )
            elif status == "in_progress":
                hint = (
                    "✅ For status change, use:\n"
                    f"  macf_tools task edit #{task_id_str} status in_progress"
                )
            elif status == "deleted":
                hint = (
                    "✅ For deletion, use:\n"
                    f"  macf_tools task delete #{task_id_str}"
                )
            else:
                hint = (
                    "✅ Use these commands instead:\n"
                    f"  macf_tools task edit #{task_id_str} status <status>       # Change status\n"
                    f"  macf_tools task edit #{task_id_str} subject \"New title\"   # Change subject\n"
                    f"  macf_tools task metadata set #{task_id_str} <field> <value>  # Edit MTMD\n"
                    f"  macf_tools task complete #{task_id_str} --report \"...\"    # Mark complete"
                )

            error_msg = (
                "❌ TaskUpdate Blocked - Use CLI commands instead\n\n"
                "The CLI provides audit trails, breadcrumbs, and proper MTMD updates.\n"
                "Native TaskUpdate bypasses framework requirements.\n\n"
                f"{hint}\n\n"
                "📚 For guidance: macf_tools policy navigate task_management"
            )
            return {
                "continue": False,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": error_msg
                }
            }

        # TaskList/TaskGet nudge - encourage CLI for richer formatting (not blocked)
        elif tool_name == "TaskList":
            message_parts.append(
                "📋 TaskList | 💡 CLI has richer formatting: macf_tools task list --display tree"
            )

        elif tool_name == "TaskGet":
            task_id_str = tool_input.get("taskId", "")
            message_parts.append(
                f"📋 TaskGet #{task_id_str} | 💡 CLI shows MTMD: macf_tools task get #{task_id_str}"
            )

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
            message_parts.append("📜")

        elif tool_name in ["Read", "Write", "Edit"]:
            message_parts.append("📄")

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

                message_parts.append("⚙️")

        # Format message (compact single line)
        message = " ".join(message_parts)

        # Add minimal token context (high-frequency hook = minimal overhead)
        token_context_minimal = format_token_context_minimal(token_info)

        # Pattern C: top-level systemMessage for user + hookSpecificOutput for agent
        user_message = f"{message} {token_context_minimal}"
        # Build additionalContext with policy injections prepended
        base_context = f"<system-reminder>\n{user_message}\n</system-reminder>"
        full_context = injection_content + base_context if injection_content else base_context

        return {
            "continue": True,
            "systemMessage": user_message,  # TOP LEVEL - user sees this
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": full_context
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

