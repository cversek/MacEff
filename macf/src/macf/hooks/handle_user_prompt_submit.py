"""
handle_user_prompt_submit - UserPromptSubmit hook runner.

DEV_DRV start tracking + full temporal + token/CLUAC awareness injection.
"""
import json
from typing import Dict, Any

from ..utils import (
    get_temporal_context,
    format_macf_footer,
    detect_execution_environment,
    get_current_session_id,
    start_dev_drv,
    get_token_info,
    format_token_context_full,
    get_boundary_guidance,
    detect_auto_mode,
    get_breadcrumb
)


def run(stdin_json: str = "") -> Dict[str, Any]:
    """
    Run UserPromptSubmit hook logic.

    Tracks DEV_DRV start and injects temporal + token/CLUAC awareness.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)

    Returns:
        Dict with DEV_DRV started message + comprehensive awareness
    """
    try:
        # Parse stdin to get session_id from Claude Code (not filesystem discovery)
        try:
            hook_input = json.loads(stdin_json) if stdin_json else {}
            session_id = hook_input.get('session_id')
        except (json.JSONDecodeError, AttributeError):
            session_id = None

        # Fallback to filesystem discovery if stdin parsing failed
        if not session_id:
            session_id = get_current_session_id()

        # Start Development Drive tracking
        start_dev_drv(session_id)

        # Get breadcrumb
        breadcrumb = get_breadcrumb()

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = detect_execution_environment()

        # Get token context
        token_info = get_token_info(session_id)
        auto_mode, _, _ = detect_auto_mode(session_id)

        # Format temporal section with breadcrumb
        temporal_section = f"""🏗️ MACF | DEV_DRV Started
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Breadcrumb: {breadcrumb}"""

        # Format token section
        token_section = format_token_context_full(token_info)

        # Get boundary guidance (if CLUAC ≤ 10)
        boundary_guidance = get_boundary_guidance(token_info['cluac_level'], auto_mode)

        # Format footer
        footer = format_macf_footer(environment)

        # Combine sections
        sections = [
            temporal_section,
            token_section,
            boundary_guidance if boundary_guidance else "",
            footer
        ]

        message = f"""<system-reminder>
{chr(10).join([s for s in sections if s])}
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
