#!/usr/bin/env python3
"""
handle_session_end - SessionEnd hook runner.

Tracks session termination (clear, logout, etc.).
"""
import json
import traceback
from typing import Dict, Any

from macf.utils import (
    get_temporal_context,
    format_macf_footer,
    get_current_session_id,
    load_agent_state,
    get_token_info,
    get_breadcrumb
)
from macf.agent_events_log import append_event
from macf.hooks.hook_logging import log_hook_event


def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Run SessionEnd hook logic.

    Tracks session termination for forensic reconstruction.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        testing: If True (DEFAULT), skip side-effects (read-only safe mode).
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with session end acknowledgment
    """
    try:
        # Parse hook input
        data = json.loads(stdin_json) if stdin_json else {}

        # Get session context
        session_id = get_current_session_id()
        project_state = load_agent_state()
        cycle_number = project_state.get('current_cycle_number', 0)

        # Get temporal context and breadcrumb
        temporal_ctx = get_temporal_context()
        breadcrumb = get_breadcrumb()

        # Get token info for final stats
        token_info = get_token_info(session_id)

        # Append session_ended event for forensic reconstruction
        import time
        append_event(
            event="session_ended",
            data={
                "session_id": session_id,
                "cycle": cycle_number,
                "breadcrumb": breadcrumb,
                "timestamp": time.time(),
                "tokens_used": token_info.get('tokens_used', 0),
                "reason": data.get("reason", "unknown")
            },
            hook_input=data
        )

        # Format message
        # Note: SessionEnd hook doesn't support hookSpecificOutput
        # (only PreToolUse, UserPromptSubmit, PostToolUse do)
        message = f"""🏗️ MACF | Session Ended
Time: {temporal_ctx['timestamp_formatted']}
Session: {session_id[:8]}...
Breadcrumb: {breadcrumb}
{format_macf_footer()}"""

        return {
            "continue": True,
            "systemMessage": message
        }

    except Exception as e:
        # Log error for debugging
        log_hook_event({
            "hook_name": "session_end",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        return {
            "continue": True,
            "systemMessage": f"🏗️ MACF | ❌ SessionEnd hook error: {e}"
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

