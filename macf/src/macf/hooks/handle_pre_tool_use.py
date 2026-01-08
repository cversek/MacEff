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

        # TodoWrite collapse detection
        if tool_name == "TodoWrite":
            from macf.event_queries import get_latest_event, get_recent_events

            todos = tool_input.get("todos", [])
            new_count = len(todos)

            # Get previous TODO count from events
            prev_event = get_latest_event("todos_updated")
            prev_count = prev_event.get("data", {}).get("count", 0) if prev_event else 0

            # All-completed detection: when all items are completed, the TODO list disappears from UI
            if new_count > 0:
                pending_count = sum(1 for t in todos if t.get("status") != "completed")
                if pending_count == 0:
                    error_msg = (
                        f"❌ TODO Visibility Warning - All Items Completed\n\n"
                        f"Detected: All {new_count} items marked as completed.\n\n"
                        f"⚠️ When all TODOs are completed, the list disappears from Claude Code UI.\n"
                        f"This makes it impossible to see completed work or restore context after compaction.\n\n"
                        f"Recommended: Keep at least one pending item as an anchor:\n"
                        f'  {{"content": "Awaiting next task", "status": "pending", "activeForm": "Awaiting next task"}}\n\n'
                        f"Add this item to your TodoWrite call and retry."
                    )
                    # Use permissionDecision for user visibility
                    return {
                        "continue": False,
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": error_msg
                        }
                    }

            # Erasure detection: check if existing item CONTENT was removed (not just count reduction)
            # This catches when agent replaces items while keeping similar count
            # Note: Status changes allowed, breadcrumb additions allowed (prefix matching)
            if prev_count > 0 and prev_event:
                prev_todos = prev_event.get("data", {}).get("items", [])
                if prev_todos:
                    # Extract content text from todos
                    prev_contents = [t.get("content", "") for t in prev_todos if t.get("content")]
                    new_contents = [t.get("content", "") for t in todos if t.get("content")]

                    # For each previous content, check if ANY new content starts with it
                    # This allows adding breadcrumbs (e.g., "Phase 1" -> "Phase 1 [breadcrumb]")
                    erased_items = []
                    for prev_content in prev_contents:
                        # Check if any new content starts with this previous content
                        preserved = any(new_c.startswith(prev_content) or prev_content.startswith(new_c)
                                        for new_c in new_contents)
                        if not preserved:
                            erased_items.append(prev_content)

                    # Only block if items were truly erased AND no collapse was authorized
                    if erased_items and new_count >= prev_count:
                        # Check for item edit authorizations (supports multiple)
                        # Get the most recent cleared timestamp to filter out consumed auths
                        item_edit_cleared = get_latest_event("todos_auth_item_edit_cleared")
                        cleared_ts = item_edit_cleared.get("timestamp", 0) if item_edit_cleared else 0

                        # Get all recent authorizations newer than last clear
                        recent_auths = get_recent_events("todos_auth_item_edit", max_count=50)
                        authorized_indices = set()
                        auth_events_to_clear = []

                        for auth_event in recent_auths:
                            auth_ts = auth_event.get("timestamp", 0)
                            if auth_ts > cleared_ts:
                                auth_index = auth_event.get("data", {}).get("index", 0)
                                if auth_index >= 1:
                                    authorized_indices.add(auth_index)
                                    auth_events_to_clear.append(auth_event)

                        # Find indices of all erased items
                        erased_indices = set()
                        for erased_content in erased_items:
                            for i, prev_c in enumerate(prev_contents):
                                if prev_c == erased_content:
                                    erased_indices.add(i + 1)  # 1-based index
                                    break

                        # Check if ALL erased items have authorizations
                        item_edit_authorized = erased_indices and erased_indices.issubset(authorized_indices)

                        if item_edit_authorized:
                            # Clear all consumed authorizations
                            for auth_event in auth_events_to_clear:
                                auth_index = auth_event.get("data", {}).get("index", 0)
                                if auth_index in erased_indices:
                                    append_event(
                                        event="todos_auth_item_edit_cleared",
                                        data={"reason": "consumed_by_todowrite", "index": auth_index}
                                    )

                        if not item_edit_authorized:
                            erased_preview = [item[:50] + "..." if len(item) > 50 else item for item in erased_items[:3]]
                            more_count = len(erased_items) - 3 if len(erased_items) > 3 else 0
                            erased_str = "\n  - ".join(erased_preview)
                            if more_count > 0:
                                erased_str += f"\n  - ... and {more_count} more"

                            # Find indices of erased items for auth hint
                            erased_indices = []
                            for erased in erased_items[:1]:  # Just show first one for hint
                                for i, prev_c in enumerate(prev_contents):
                                    if prev_c == erased:
                                        erased_indices.append(i + 1)
                                        break

                            # Build authorization instructions
                            if erased_indices:
                                auth_cmd = f"macf_tools todos auth-item-edit --index {erased_indices[0]} --reason \"reason\""
                                auth_instructions = (
                                    f"\n\n🚨 AGENT: Ask the user for approval before running auth commands.\n\n"
                                    f"To authorize, USER may either:\n"
                                    f"  1. Run directly: {auth_cmd}\n"
                                    f"  2. Say \"granted!\" to allow agent to run the auth command\n\n"
                                    f"AGENT: After authorization, retry TodoWrite.\n\n"
                                    f"Why: Content replacement requires human oversight to prevent accidental data loss."
                                )
                            else:
                                auth_instructions = (
                                    f"\n\nTo proceed anyway, USER can say 'proceed' or agent can retry with preserved content."
                                )

                            warning_msg = (
                                f"⚠️ TODO Erasure Detected - Item Content Removed\n\n"
                                f"Previous: {prev_count} items → New: {new_count} items\n"
                                f"Erased content ({len(erased_items)} items):\n  - {erased_str}\n\n"
                                f"Status changes and breadcrumb additions are allowed.{auth_instructions}"
                            )
                            # Use permissionDecision for user visibility
                            return {
                                "continue": False,
                                "hookSpecificOutput": {
                                    "hookEventName": "PreToolUse",
                                    "permissionDecision": "deny",
                                    "permissionDecisionReason": warning_msg
                                }
                            }

            # Collapse detection: new < prev
            if prev_count > 0 and new_count < prev_count:
                # Check for authorization
                auth_event = get_latest_event("todos_auth_collapse")
                cleared_event = get_latest_event("todos_auth_cleared")

                # Check if auth is valid (not cleared)
                auth_valid = False
                if auth_event:
                    auth_ts = auth_event.get("timestamp", 0)
                    cleared_ts = cleared_event.get("timestamp", 0) if cleared_event else 0
                    if auth_ts > cleared_ts:
                        auth_data = auth_event.get("data", {})
                        auth_from = auth_data.get("from_count", 0)
                        auth_to = auth_data.get("to_count", 0)
                        # Validate counts match
                        if auth_from == prev_count and auth_to == new_count:
                            auth_valid = True
                            # Clear the auth (single use)
                            append_event(
                                event="todos_auth_cleared",
                                data={"reason": "consumed_by_todowrite"}
                            )

                if not auth_valid:
                    reduction = prev_count - new_count
                    error_msg = (
                        f"❌ TODO Collapse Blocked - User Authorization Required\n\n"
                        f"Detected: Reducing from {prev_count} items to {new_count} items (collapse of {reduction} items)\n\n"
                        f"🚨 AGENT: Ask the user for approval before running auth commands.\n\n"
                        f"To authorize, USER may either:\n"
                        f"  1. Run directly: macf_tools todos auth-collapse --from {prev_count} --to {new_count} --reason \"reason\"\n"
                        f"  2. Say \"granted!\" to allow agent to run the auth command\n\n"
                        f"AGENT: After authorization, retry TodoWrite.\n\n"
                        f"Why: TODO collapses are irreversible. Human oversight prevents accidental data loss."
                    )
                    # Use permissionDecision for user visibility (exit 2 stderr not shown for TodoWrite)
                    return {
                        "continue": False,
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": error_msg
                        }
                    }

        # Enhanced context based on tool type
        if tool_name == "Task":
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

