"""
handle_user_prompt_submit - UserPromptSubmit hook runner.

DEV_DRV start tracking + full temporal awareness injection.
"""
import json
from typing import Dict, Any

from ..utils import (
    get_temporal_context,
    format_macf_footer,
    detect_execution_environment,
    get_current_session_id,
    start_dev_drv,
    get_current_cycle_project
)


def run(stdin_json: str = "") -> Dict[str, Any]:
    """
    Run UserPromptSubmit hook logic.

    Tracks DEV_DRV start and injects temporal awareness.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)

    Returns:
        Dict with DEV_DRV started message
    """
    try:
        # Get current session
        session_id = get_current_session_id()

        # Start Development Drive tracking
        start_dev_drv(session_id)

        # Get cycle number from project state
        cycle_number = get_current_cycle_project()

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = detect_execution_environment()

        # Format message with full timestamp
        message = f"""<system-reminder>
🏗️ MACF | DEV_DRV Started
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Cycle: {cycle_number} | Session: {session_id[:8]}...

{format_macf_footer(environment)}
</system-reminder>"""

        # Return with both additionalContext (agent) and systemMessage (user)
        return {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": message,
                "systemMessage": message
            }
        }

    except Exception:
        # Silent failure
        return {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit"
            }
        }
