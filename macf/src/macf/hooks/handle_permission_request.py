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


def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Run PermissionRequest hook logic.

    Tracks permission dialogs for forensic reconstruction.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        testing: If True (DEFAULT), skip side-effects (read-only safe mode).
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
    import os
    import sys
    # MACF_TESTING_MODE env var enables safe testing via subprocess
    testing_mode = os.environ.get('MACF_TESTING_MODE', '').lower() in ('true', '1', 'yes')
    try:
        output = run(sys.stdin.read(), testing=testing_mode)
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"continue": True}))
        print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)

