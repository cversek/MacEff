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
    complete_deleg_drv_by_agent,
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
from macf.observability import Warning, emit_warning


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """
    Run SubagentStop hook logic.

    Tracks DELEG_DRV completion and displays delegation stats.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with DELEG_DRV completion message
    """
    try:
        # Get current session
        session_id = get_current_session_id()

        # Parse stdin. CC's SubagentStop payload fields:
        #   agent_id, agent_type, agent_transcript_path, last_assistant_message
        # (the field name is `agent_type`, NOT `subagent_type` — earlier
        # versions of this handler read the wrong field name and got
        # "unknown" back).
        try:
            hook_input = json.loads(stdin_json) if stdin_json else {}
            agent_id = hook_input.get('agent_id', '')
            agent_type_from_hook = hook_input.get('agent_type', '')
            agent_transcript_path = hook_input.get('agent_transcript_path', '')
            last_assistant_message = hook_input.get('last_assistant_message', '')
        except json.JSONDecodeError as e:
            emit_warning(Warning(source="subagent_stop", kind="stdin_parse_failed", detail=f"subagent_stop stdin parse failed: {e}"))
            hook_input = {}
            agent_id = ''
            agent_type_from_hook = ''
            agent_transcript_path = ''
            last_assistant_message = ''

        # Get breadcrumb BEFORE completing
        breadcrumb = get_breadcrumb()

        # Get stats BEFORE completing
        stats = get_deleg_drv_stats(session_id)

        # Complete via the SubagentStart bridge when agent_id is available
        # (current CC versions always send it). The bridge lookup is
        # parallel-safe: matching is by agent_id, not "most recent unended".
        # Falls back to the legacy by-most-recent path if agent_id is empty
        # (extremely old CC, or transient hook-input issue).
        if agent_id:
            success, duration, tool_use_id, correlation_id, resolved_subagent_type = (
                complete_deleg_drv_by_agent(
                    session_id,
                    agent_id=agent_id,
                    agent_transcript_path=agent_transcript_path,
                    last_assistant_message=last_assistant_message,
                )
            )
        else:
            # Legacy fallback (no agent_id in hook input).
            success, duration, correlation_id, resolved_subagent_type = complete_deleg_drv(
                session_id, subagent_type=agent_type_from_hook or "unknown",
            )
            tool_use_id = ""

        # Display name resolution: prefer the started-event-derived value
        # (more reliable than hook_input's agent_type), falling back to
        # hook_input.agent_type if the bridge lookup came up empty.
        subagent_type = resolved_subagent_type or agent_type_from_hook or 'unknown'

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
        auto_mode, _ = detect_auto_mode(session_id)

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
        boundary_guidance = get_boundary_guidance(token_info['cl_level'], auto_mode)

        # Format message with full timestamp and DELEG_DRV summary.
        # `Total Delegations` was dropped — the aggregate count across a
        # session doesn't carry actionable signal. Per-call duration plus
        # session-aggregate duration remain.
        tag_line = (
            f"[{subagent_type}@{correlation_id}]"
            if correlation_id else f"[{subagent_type}]"
        )
        message = f"""🏗️ MACF | DELEG_DRV Complete {tag_line}
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Breadcrumb: {breadcrumb}

Delegation Drive Stats:
- This Delegation: {duration_str}
- Total Duration: {total_duration_str}

{token_section}

{boundary_guidance if boundary_guidance else ""}

{format_macf_footer()}"""

        # Notify Telegram (non-blocking). Tag matches the format used by
        # the matching Started message in handle_pre_tool_use so observers
        # can visually pair the boundary in the channel. Includes agent_id
        # (CC AgentId) and a short preview of the subagent's final reply
        # for at-a-glance remote observability.
        try:
            from macf.channels.telegram import send_telegram_notification
            tag = (
                f"[{subagent_type}@{correlation_id}|{agent_id[:8]}]"
                if correlation_id and agent_id else
                f"[{subagent_type}@{correlation_id}]" if correlation_id else
                f"[{subagent_type}|{agent_id[:8]}]" if agent_id else
                f"[{subagent_type}]"
            )
            reply_preview = (last_assistant_message or "").strip().replace("\n", " ")[:120]
            body_lines = [
                tag,
                f"Duration: {duration_str}",
                f"CL: {token_info.get('cl_level', 'N/A')}",
            ]
            if reply_preview:
                body_lines.append(f"Reply: {reply_preview}")
            send_telegram_notification(
                "\n".join(body_lines),
                prefix="\U0001f4dc DELEG_DRV Complete",
            )
        except (ImportError, OSError, ConnectionError) as e:
            emit_warning(Warning(source="subagent_stop", kind="deleg_drv_telegram_failed", detail=f"DELEG_DRV telegram notification failed (non-blocking): {e}"))

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
    import sys
    try:
        output = run(sys.stdin.read())
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"continue": True}))
        print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)

