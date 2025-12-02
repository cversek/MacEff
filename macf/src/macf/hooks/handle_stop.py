"""
handle_stop - Stop hook runner.

DEV_DRV completion tracking + stats display.
"""
import json
import traceback
from typing import Dict, Any

from ..utils import (
    get_temporal_context,
    format_macf_footer,
    get_rich_environment_string,
    get_current_session_id,
    complete_dev_drv,
    get_dev_drv_stats,
    format_duration,
    load_agent_state,
    save_agent_state,
    get_token_info,
    format_token_context_full,
    get_boundary_guidance,
    detect_auto_mode,
    get_breadcrumb
)
from ..agent_events_log import append_event
from .logging import log_hook_event


def run(stdin_json: str = "", testing: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Run Stop hook logic.

    Tracks DEV_DRV completion and displays stats.

    Side effects (ONLY when testing=False):
    - Increments DEV_DRV counter in session state
    - Records drive duration and aggregates stats
    - Updates last_session_ended_at timestamp in .maceff/project_state.json

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        testing: If True (DEFAULT), skip side-effects (read-only safe mode).
                 If False, apply mutations (production only).
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with DEV_DRV completion message
    """
    try:
        # Get current session
        session_id = get_current_session_id()

        # Get breadcrumb BEFORE completing (complete_dev_drv clears prompt_uuid)
        breadcrumb = get_breadcrumb()

        # Save UUID before completing (complete_dev_drv clears it)
        from ..utils import SessionOperationalState
        state = SessionOperationalState.load(session_id)
        prompt_uuid = state.current_dev_drv_prompt_uuid

        # Complete Development Drive (increments count, adds duration)
        success, duration = complete_dev_drv(session_id)

        # Append dev_drv_ended event
        append_event(
            event="dev_drv_ended",
            data={
                "session_id": session_id,
                "prompt_uuid": prompt_uuid if prompt_uuid else "unknown",
                "duration_seconds": duration if success else 0
            },
            hook_input=json.loads(stdin_json) if stdin_json else {}
        )

        # Get stats AFTER completing (now includes this drive)
        stats = get_dev_drv_stats(session_id)
        stats['prompt_uuid'] = prompt_uuid  # Restore UUID for display

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = get_rich_environment_string()

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
        project_state = load_agent_state()
        project_state['last_session_ended_at'] = time.time()
        save_agent_state(project_state)

        # Get token context and mode
        token_info = get_token_info(session_id)
        auto_mode, _, _ = detect_auto_mode(session_id)

        # Format token context using DRY utility
        token_section = format_token_context_full(token_info)
        boundary_guidance = get_boundary_guidance(token_info['cluac_level'], auto_mode)

        # Format message with full timestamp and DEV_DRV summary
        message = f"""🏗️ MACF | DEV_DRV Complete
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Breadcrumb: {breadcrumb}

Development Drive Stats:
- This Drive: {duration_str}
- Prompt: {uuid_display}
- Total Drives: {stats['count']}
- Total Duration: {total_duration_str}

{token_section}

{boundary_guidance if boundary_guidance else ""}

{format_macf_footer()}"""

        # Return with systemMessage only (Stop hook doesn't support hookSpecificOutput)
        return {
            "continue": True,
            "systemMessage": message
        }

    except Exception as e:
        # Log error for debugging
        log_hook_event({
            "hook_name": "stop",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        return {
            "continue": True,
            "systemMessage": f"🏗️ MACF | ❌ Stop hook error: {e}"
        }
