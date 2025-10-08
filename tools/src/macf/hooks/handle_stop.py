"""
handle_stop - Stop hook runner.

DEV_DRV completion tracking + stats display.
"""
import json
from typing import Dict, Any

from ..utils import (
    get_temporal_context,
    format_macf_footer,
    detect_execution_environment,
    get_current_session_id,
    complete_dev_drv,
    get_dev_drv_stats,
    get_current_cycle_project
)


def run(stdin_json: str = "") -> Dict[str, Any]:
    """
    Run Stop hook logic.

    Tracks DEV_DRV completion and displays stats.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)

    Returns:
        Dict with DEV_DRV completion message
    """
    try:
        # Get current session
        session_id = get_current_session_id()

        # Get stats BEFORE completing (complete_dev_drv clears UUID!)
        stats = get_dev_drv_stats(session_id)

        # Complete Development Drive
        success, duration = complete_dev_drv(session_id)

        # Get cycle number for display
        cycle_number = get_current_cycle_project()

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = detect_execution_environment()

        # Format UUID for display
        prompt_uuid = stats.get('prompt_uuid')
        if prompt_uuid:
            uuid_display = f"{prompt_uuid[:8]}..."
        else:
            uuid_display = "N/A"

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

        # Format message with full timestamp and DEV_DRV summary
        message = f"""<system-reminder>
🏗️ MACF | DEV_DRV Complete
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Cycle: {cycle_number} | Session: {session_id[:8]}...

Development Drive Stats:
- This Drive: {duration_str}
- Prompt: {uuid_display}
- Total Drives: {stats['count']}
- Total Duration: {total_duration_str}

{format_macf_footer(environment)}
</system-reminder>"""

        # Return with hookSpecificOutput.additionalContext
        return {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": message
            }
        }

    except Exception:
        # Silent failure
        return {"continue": True}
