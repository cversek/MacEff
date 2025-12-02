"""
handle_user_prompt_submit - UserPromptSubmit hook runner.

DEV_DRV start tracking + full temporal + token/CLUAC awareness injection.
"""
import json
from typing import Dict, Any

from ..utils import (
    get_temporal_context,
    format_macf_footer,
    get_rich_environment_string,
    get_current_session_id,
    start_dev_drv,
    get_token_info,
    format_token_context_full,
    get_boundary_guidance,
    detect_auto_mode,
    get_breadcrumb
)
from ..agent_events_log import append_event


def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Run UserPromptSubmit hook logic.

    Tracks DEV_DRV start and injects temporal + token/CLUAC awareness.

    Side effects (ONLY when testing=False):
    - Starts DEV_DRV tracking in session state
    - Records prompt UUID and start timestamp
    - Updates session operational state

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        testing: If True (DEFAULT), skip side-effects (read-only safe mode).
                 If False, apply mutations (production only).
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with DEV_DRV started message + comprehensive awareness
    """
    try:
        # Parse stdin to get session_id and transcript_path from Claude Code
        try:
            hook_input = json.loads(stdin_json) if stdin_json else {}
            session_id = hook_input.get('session_id')
            transcript_path = hook_input.get('transcript_path')
        except (json.JSONDecodeError, AttributeError):
            session_id = None
            transcript_path = None

        # Fallback to filesystem discovery if stdin parsing failed
        if not session_id:
            session_id = get_current_session_id()

        # Get current message UUID from JSONL (message written before hook fires)
        from ..utils.session import get_last_user_prompt_uuid
        current_prompt_uuid = get_last_user_prompt_uuid(session_id)

        # Start Development Drive tracking with current UUID (skip if testing)
        if not testing:
            start_dev_drv(session_id, prompt_uuid=current_prompt_uuid)

        # Append dev_drv_started event
        append_event(
            event="dev_drv_started",
            data={
                "session_id": session_id,
                "prompt_uuid": current_prompt_uuid if current_prompt_uuid else "unknown"
            },
            hook_input=hook_input
        )

        # Get breadcrumb
        breadcrumb = get_breadcrumb()

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = get_rich_environment_string()

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
        footer = format_macf_footer()

        # Combine sections into plain content (DRY - single source)
        sections = [
            temporal_section,
            token_section,
            boundary_guidance if boundary_guidance else "",
            footer
        ]
        plain_content = chr(10).join([s for s in sections if s])

        # Pattern C: top-level systemMessage for user + hookSpecificOutput for agent
        return {
            "continue": True,
            "systemMessage": plain_content,  # TOP LEVEL - user sees this
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"<system-reminder>\n{plain_content}\n</system-reminder>"
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
