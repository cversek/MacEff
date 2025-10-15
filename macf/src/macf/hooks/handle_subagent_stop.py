"""
handle_subagent_stop - SubagentStop hook runner.

DELEG_DRV completion tracking + delegation stats.
"""
import json
from typing import Dict, Any

from ..utils import (
    get_temporal_context,
    format_macf_footer,
    detect_execution_environment,
    get_current_session_id,
    complete_deleg_drv,
    get_deleg_drv_stats,
    format_duration,
    get_token_info,
    format_token_context_full,
    get_boundary_guidance,
    detect_auto_mode
)


def run(stdin_json: str = "") -> Dict[str, Any]:
    """
    Run SubagentStop hook logic.

    Tracks DELEG_DRV completion and displays delegation stats.

    ⚠️  WARNING: SIDE EFFECTS - DO NOT CALL DIRECTLY FOR TESTING ⚠️

    This hook MUTATES SESSION STATE on every execution:
    - Increments DELEG_DRV counter in session state
    - Records delegation duration and aggregates stats
    - Clears current delegation tracking variables

    Calling this hook directly (e.g., for testing) will cause:
    - DELEG_DRV counts to increment incorrectly
    - Inaccurate delegation duration statistics
    - Lost tracking of current delegation context

    For testing: Mock complete_deleg_drv() or use unit tests that isolate
    stat computation from state mutation.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)

    Returns:
        Dict with DELEG_DRV completion message
    """
    try:
        # Get current session
        session_id = get_current_session_id()

        # Get stats BEFORE completing (complete_deleg_drv clears current tracking!)
        stats = get_deleg_drv_stats(session_id)

        # Complete Delegation Drive
        success, duration = complete_deleg_drv(session_id)

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = detect_execution_environment()

        # Get token context and auto_mode
        token_info = get_token_info(session_id)
        auto_mode, _, _ = detect_auto_mode(session_id)

        # Format duration from seconds
        def format_duration(seconds):
            if seconds < 60:
                return f"{int(seconds)}s"
            minutes = int(seconds // 60)
            if minutes < 60:
                return f"{minutes}m"
            hours = minutes // 60
            remaining_minutes = minutes % 60
            return f"{hours}h {remaining_minutes}m"

        duration_str = format_duration(duration) if success else "N/A"
        total_duration_str = format_duration(stats['total_duration'])

        # Format token context sections
        token_section = format_token_context_full(token_info)
        boundary_guidance = get_boundary_guidance(token_info['cluac_level'], auto_mode)

        # Format message with full timestamp and DELEG_DRV summary
        message = f"""🏗️ MACF | DELEG_DRV Complete
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Session: {session_id[:8]}...

Delegation Drive Stats:
- This Delegation: {duration_str}
- Total Delegations: {stats['count']}
- Total Duration: {total_duration_str}

{token_section}

{boundary_guidance if boundary_guidance else ""}

{format_macf_footer(environment)}"""

        # Return with systemMessage (user display only - SubagentStop hook doesn't support hookSpecificOutput)
        return {
            "continue": True,
            "systemMessage": message
        }

    except Exception:
        # Silent failure
        return {"continue": True}
