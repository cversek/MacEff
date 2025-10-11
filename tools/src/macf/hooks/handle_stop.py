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
    get_current_cycle_project,
    format_duration,
    load_project_state,
    save_project_state,
    get_token_info
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

        # Save UUID before completing (complete_dev_drv clears it)
        from ..utils import SessionOperationalState
        state = SessionOperationalState.load(session_id)
        prompt_uuid = state.current_dev_drv_prompt_uuid

        # Complete Development Drive (increments count, adds duration)
        success, duration = complete_dev_drv(session_id)

        # Get stats AFTER completing (now includes this drive)
        stats = get_dev_drv_stats(session_id)
        stats['prompt_uuid'] = prompt_uuid  # Restore UUID for display

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

        # Format durations using shared utility
        duration_str = format_duration(duration) if success else "N/A"
        total_duration_str = format_duration(stats['total_duration'])

        # Save session end time to project state (cross-session persistence)
        import time
        project_state = load_project_state()
        project_state['last_session_ended_at'] = time.time()
        save_project_state(project_state)

        # Get token context for smoke test
        token_info = get_token_info(session_id)

        # Format message with full timestamp and DEV_DRV summary
        message = f"""🏗️ MACF | DEV_DRV Complete
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Cycle: {cycle_number} | Session: {session_id[:8]}...

Development Drive Stats:
- This Drive: {duration_str}
- Prompt: {uuid_display}
- Total Drives: {stats['count']}
- Total Duration: {total_duration_str}

📊 TOKEN CONTEXT (SMOKE TEST)
Tokens Used: {token_info['tokens_used']:,} / 200,000
CLUAC Level: {token_info['cluac_level']}
Remaining: {token_info['tokens_remaining']:,} tokens

{format_macf_footer(environment)}"""

        # Create smoke test message for AGENT consciousness (additionalContext injection)
        smoke_test_message = f"""<system-reminder>
🏗️ MACF TOKEN AWARENESS - SMOKE TEST

📊 TOKEN CONTEXT TEST
Tokens Used: {token_info['tokens_used']:,} / 200,000
CLUAC Level: {token_info['cluac_level']}
Remaining: {token_info['tokens_remaining']:,} tokens

Smoke test to validate token awareness injection.
</system-reminder>"""

        # Return with both systemMessage (user) and additionalContext (agent)
        return {
            "continue": True,
            "systemMessage": message,
            "hookSpecificOutput": {
                "additionalContext": smoke_test_message
            }
        }

    except Exception:
        # Silent failure
        return {"continue": True}
