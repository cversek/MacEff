#!/usr/bin/env python3
"""
handle_pre_compact - PreCompact hook runner.

Tracks imminent compaction before it occurs.
"""
import json
import sys
import traceback
from typing import Dict, Any

from macf.utils import (
    get_temporal_context,
    format_macf_footer,
    get_current_session_id,
    get_token_info,
    get_breadcrumb
)
from macf.agent_events_log import append_event
from macf.event_queries import get_cycle_number_from_events
from macf.hooks.hook_logging import log_hook_event


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """
    Run PreCompact hook logic.

    Tracks imminent compaction for forensic reconstruction.
    This fires RIGHT BEFORE compaction occurs.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with pre-compact acknowledgment
    """
    try:
        # Parse hook input
        data = json.loads(stdin_json) if stdin_json else {}

        # Get session context
        session_id = get_current_session_id()
        cycle_number = get_cycle_number_from_events()

        # Get breadcrumb before compaction
        breadcrumb = get_breadcrumb()

        # Get token info (should be near limit)
        token_info = get_token_info(session_id)

        # Get temporal context
        temporal_ctx = get_temporal_context()

        # Append pre_compact event for forensic reconstruction
        import time
        append_event(
            event="pre_compact",
            data={
                "session_id": session_id,
                "cycle": cycle_number,
                "breadcrumb": breadcrumb,
                "timestamp": time.time(),
                "tokens_used": token_info.get('tokens_used', 0),
                "cluac_level": token_info.get('cluac_level', 0),
                "source": data.get("source", "auto")  # "auto" or "manual"
            },
            hook_input=data
        )

        # Format message
        # Note: PreCompact hook doesn't support hookSpecificOutput
        # (only PreToolUse, UserPromptSubmit, PostToolUse do)
        message = f"""🏗️ MACF | Pre-Compact
Time: {temporal_ctx['timestamp_formatted']}
Breadcrumb: {breadcrumb}
CLUAC: {token_info.get('cluac_level', 'N/A')}
{format_macf_footer()}"""

        return {
            "continue": True,
            "systemMessage": message
        }

    except Exception as e:
        # Log error for debugging
        log_hook_event({
            "hook_name": "pre_compact",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        return {
            "continue": True,
            "systemMessage": f"🏗️ MACF | ❌ PreCompact hook error: {e}"
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

