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
    format_duration
)


def run(stdin_json: str = "") -> Dict[str, Any]:
    """
    Run SubagentStop hook logic.

    Tracks DELEG_DRV completion and displays delegation stats.

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

{format_macf_footer(environment)}"""

        # Return with systemMessage (user display only - SubagentStop hook doesn't support hookSpecificOutput)
        return {
            "continue": True,
            "systemMessage": message
        }

    except Exception:
        # Silent failure
        return {"continue": True}
