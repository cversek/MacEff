#!/usr/bin/env python3
"""
handle_subagent_stop - SubagentStop hook runner.

DELEG_DRV completion tracking + delegation stats.
"""
import json
import sys
import traceback
from typing import Dict, Any

from macf.utils import (
    get_temporal_context,
    format_macf_footer,
    get_rich_environment_string,
    get_current_session_id,
    complete_deleg_drv,
    get_deleg_drv_stats,
    format_duration,
    get_token_info,
    format_token_context_full,
    get_boundary_guidance,
    detect_auto_mode,
    get_breadcrumb
)
from macf.agent_events_log import append_event
from macf.hooks.hook_logging import log_hook_event


def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Run SubagentStop hook logic.

    Tracks DELEG_DRV completion and displays delegation stats.

    Side effects (ONLY when testing=False):
    - Increments DELEG_DRV counter in session state
    - Records delegation duration and aggregates stats
    - Clears current delegation tracking variables

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        testing: If True (DEFAULT), skip side-effects (read-only safe mode).
                 If False, apply mutations (production only).
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with DELEG_DRV completion message
    """
    try:
        # Get current session
        session_id = get_current_session_id()

        # Parse stdin to get subagent type
        try:
            hook_input = json.loads(stdin_json) if stdin_json else {}
            subagent_type = hook_input.get('subagent_type', 'unknown')
        except Exception:
            hook_input = {}
            subagent_type = 'unknown'

        # Get breadcrumb BEFORE completing (complete_deleg_drv may clear tracking state)
        breadcrumb = get_breadcrumb()

        # Get stats BEFORE completing (complete_deleg_drv clears current tracking!)
        stats = get_deleg_drv_stats(session_id)

        # Complete Delegation Drive (skip if testing)
        if not testing:
            success, duration = complete_deleg_drv(session_id)
        else:
            # Testing mode: read-only, don't mutate state
            success, duration = True, 0.0

        # Append delegation_completed event
        append_event(
            event="delegation_completed",
            data={
                "session_id": session_id,
                "agent_type": subagent_type,
                "success": success,
                "duration_seconds": duration
            },
            hook_input=hook_input
        )

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = get_rich_environment_string()

        # Get token context and auto_mode
        token_info = get_token_info(session_id)
        auto_mode, _, _ = detect_auto_mode(session_id)

        # Format duration from seconds
        def format_duration_local(seconds):
            if seconds < 60:
                return f"{int(seconds)}s"
            minutes = int(seconds // 60)
            if minutes < 60:
                return f"{minutes}m"
            hours = minutes // 60
            remaining_minutes = minutes % 60
            return f"{hours}h {remaining_minutes}m"

        duration_str = format_duration_local(duration) if success else "N/A"
        total_duration_str = format_duration_local(stats['total_duration'])

        # Format token context sections
        token_section = format_token_context_full(token_info)
        boundary_guidance = get_boundary_guidance(token_info['cluac_level'], auto_mode)

        # Format message with full timestamp and DELEG_DRV summary
        message = f"""🏗️ MACF | DELEG_DRV Complete
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Breadcrumb: {breadcrumb}

Delegation Drive Stats:
- This Delegation: {duration_str}
- Total Delegations: {stats['count']}
- Total Duration: {total_duration_str}

{token_section}

{boundary_guidance if boundary_guidance else ""}

{format_macf_footer()}"""

        # Return with systemMessage (user display only - SubagentStop hook doesn't support hookSpecificOutput)
        return {
            "continue": True,
            "systemMessage": message
        }

    except Exception as e:
        # Log error for debugging
        log_hook_event({
            "hook_name": "subagent_stop",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        # Note: SubagentStop hook doesn't support hookSpecificOutput
        # (only PreToolUse, UserPromptSubmit, PostToolUse do)
        error_msg = f"🏗️ MACF | ❌ SubagentStop hook error: {e}"
        return {
            "continue": True,
            "systemMessage": error_msg
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

