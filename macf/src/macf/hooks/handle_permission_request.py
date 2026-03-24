#!/usr/bin/env python3
"""
handle_permission_request - PermissionRequest hook runner.

Tracks when permission dialogs are shown to user.
"""
import json
import sys
import traceback
from typing import Dict, Any

from macf.utils import (
    get_minimal_timestamp,
    get_current_session_id,
    get_breadcrumb
)
from macf.agent_events_log import append_event
from macf.hooks.hook_logging import log_hook_event


def _send_permission_preview(tool_name, tool_input, send_notification, send_document, html_escape):
    """Format and send file preview to Telegram based on tool type."""
    import os

    if tool_name == "Write":
        file_path = tool_input.get("file_path", "unknown")
        content = tool_input.get("content", "")
        fname = os.path.basename(file_path)

        # HTML message with truncated preview
        preview = html_escape(content[:3000])
        if len(content) > 3000:
            preview += f"\n\n... ({len(content)} chars total)"
        msg = f"\U0001f4dd <b>Write</b>: <code>{html_escape(file_path)}</code>\n\n<pre>{preview}</pre>"
        send_notification(msg, parse_mode="HTML")

        # Full file as document attachment
        if len(content) > 3000:
            send_document(content, fname, caption=f"Full content: {file_path}")

    elif tool_name == "Edit":
        file_path = tool_input.get("file_path", "unknown")
        old_str = tool_input.get("old_string", "")
        new_str = tool_input.get("new_string", "")

        old_preview = html_escape(old_str[:1500])
        new_preview = html_escape(new_str[:1500])
        msg = (
            f"\u270f\ufe0f <b>Edit</b>: <code>{html_escape(file_path)}</code>\n\n"
            f"<b>Replace:</b>\n<pre>{old_preview}</pre>\n\n"
            f"<b>With:</b>\n<pre>{new_preview}</pre>"
        )
        send_notification(msg, parse_mode="HTML")

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        msg = f"\u2699\ufe0f <b>Bash</b>"
        if desc:
            msg += f": {html_escape(desc)}"
        msg += f"\n\n<pre>{html_escape(command[:3000])}</pre>"
        send_notification(msg, parse_mode="HTML")


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """
    Run PermissionRequest hook logic.

    Tracks permission dialogs for forensic reconstruction.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with permission request acknowledgment
    """
    try:
        # Parse hook input
        data = json.loads(stdin_json) if stdin_json else {}

        # Get session context
        session_id = get_current_session_id()

        # Extract permission details
        tool_name = data.get("tool_name", "unknown")
        permission_type = data.get("type", "unknown")

        # Truncate tool_input if present (may contain large payloads)
        tool_input = data.get("tool_input", {})
        tool_input_preview = str(tool_input)[:200]
        if len(str(tool_input)) > 200:
            tool_input_preview += f" [...{len(str(tool_input))} chars]"

        # Append permission_requested event
        import time
        append_event(
            event="permission_requested",
            data={
                "session_id": session_id,
                "tool_name": tool_name,
                "permission_type": permission_type,
                "tool_input_preview": tool_input_preview,
                "timestamp": time.time()
            },
            hook_input=data
        )

        # Format message
        # Note: PermissionRequest hook doesn't support hookSpecificOutput
        # (only PreToolUse, UserPromptSubmit, PostToolUse do)
        timestamp = get_minimal_timestamp()
        breadcrumb = get_breadcrumb()
        message = f"🏗️ MACF | {timestamp} | {breadcrumb} | 🔐 Permission: {tool_name}"

        # Send file preview to Telegram (non-blocking, never fails the hook)
        try:
            from macf.channels.telegram import (
                send_telegram_notification, send_telegram_document, _html_escape
            )
            _send_permission_preview(tool_name, tool_input,
                                     send_telegram_notification,
                                     send_telegram_document,
                                     _html_escape)
        except Exception as e:
            print(f"MACF: Permission preview Telegram error: {e}", file=sys.stderr)

        return {
            "continue": True,
            "systemMessage": message
        }

    except Exception as e:
        # Log error for debugging, don't fail silently
        error_msg = f"PermissionRequest hook error: {e}\n{traceback.format_exc()}"
        log_hook_event({
            "hook_name": "permission_request",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        return {
            "continue": True,
            "systemMessage": f"🏗️ MACF | ❌ PermissionRequest hook error: {e}"
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

