#!/usr/bin/env python3
"""
handle_stop - Stop hook runner.

DEV_DRV completion tracking + stats display.
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
    complete_dev_drv,
    get_dev_drv_stats,
    format_duration,
    get_token_info,
    format_token_context_full,
    get_boundary_guidance,
    detect_auto_mode,
    get_breadcrumb
)
from macf.agent_events_log import append_event
from macf.hooks.hook_logging import log_hook_event
from macf.modes import (
    detect_active_modes, get_current_work_mode,
    sample_next_work_mode, format_recommendation,
    should_self_manage_closeout, format_mode_indicators,
    should_suppress_markov, format_low_context_directive,
)


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """
    Run Stop hook logic.

    Tracks DEV_DRV completion and displays stats.

    - Increments DEV_DRV counter in session state
    - Records drive duration and aggregates stats
    - Updates last_session_ended_at timestamp in .maceff/project_state.json

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
        **kwargs: Additional parameters for future extensibility

    Returns:
        Dict with DEV_DRV completion message
    """
    try:
        # Get current session
        session_id = get_current_session_id()

        # Get breadcrumb BEFORE completing (complete_dev_drv clears prompt_uuid)
        breadcrumb = get_breadcrumb()

        # EVENT-FIRST: Get prompt_uuid from event log (lazy import to avoid circular)
        prompt_uuid = None
        try:
            from macf.event_queries import get_dev_drv_stats_from_events
            stats = get_dev_drv_stats_from_events(session_id)
            prompt_uuid = stats.get("current_prompt_uuid")
        except Exception as e:
            print(f"⚠️ MACF: DEV_DRV stats query failed: {e}", file=sys.stderr)
            try:
                append_event("error", {
                    "source": "handle_stop.run",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "fallback": "state_file_lookup"
                })
            except Exception as log_e:
                print(f"⚠️ MACF: Event logging also failed: {log_e}", file=sys.stderr)

        # No fallback - event log is sole source of truth
        # If event query failed, prompt_uuid stays empty/unknown

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

        # dev_drv_ended event captures timestamp - state write removed

        # Get token context and mode
        token_info = get_token_info(session_id)
        auto_mode, _ = detect_auto_mode(session_id)

        # TODO v0.3.1: AUTO_MODE task verification
        # When in AUTO_MODE, verify completed work against roadmap validation checklist
        # _check_auto_mode_completion(session_id, auto_mode)

        # TODO v0.3.1: AUTO_MODE notification system
        # When in AUTO_MODE with significant milestone, send notification
        # (configurable channels: system notification, webhook, etc.)
        # _send_auto_mode_notification(session_id, auto_mode, stats)

        # Format token context using DRY utility
        token_section = format_token_context_full(token_info)
        boundary_guidance = get_boundary_guidance(token_info['cl_level'], auto_mode)

        # Mode indicators for status line
        mode_indicator = ""
        try:
            active_modes = detect_active_modes(session_id, token_info)
            mode_indicator = format_mode_indicators(active_modes)
        except Exception as e:
            print(f"⚠️ MACF: mode detection failed in stop hook: {e}", file=sys.stderr)
            mode_indicator = " 🤖" if auto_mode else ""

        # Format message with full timestamp and DEV_DRV summary
        message = f"""🏗️ MACF{mode_indicator} | DEV_DRV Complete
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

        # Notify Telegram unconditionally (non-blocking to main return)
        try:
            from macf.channels.telegram import send_telegram_notification
            input_data = json.loads(stdin_json) if stdin_json else {}
            stop_reason = input_data.get('stop_reason', '')
            is_error = 'error' in stop_reason.lower() if stop_reason else False
            symbol = "\u274c" if is_error else "\u23f9\ufe0f"
            # Use last_assistant_message if available, otherwise DEV_DRV stats
            last_msg = input_data.get('last_assistant_message', '')
            if last_msg:
                notify_text = last_msg
            else:
                notify_text = f"DEV_DRV #{stats['count']} complete ({duration_str})"
            send_telegram_notification(notify_text, prefix=f"{symbol} Agent stopped")
        except Exception as e:
            print(f"⚠️ MACF: Stop hook Telegram notification error: {e}", file=sys.stderr)

        # --- Error-resilience gate (ANY mode) ---
        # If the agent stopped due to a tool error, nudge it to investigate.
        # In AUTO_MODE: hard block. In MANUAL_MODE: soft nudge via systemMessage.
        input_data = json.loads(stdin_json) if stdin_json else {}
        stop_reason = input_data.get('stop_reason', '')
        is_error_stop = 'error' in stop_reason.lower() if stop_reason else False

        # --- Scope gate: block stop if active scoped tasks remain ---
        try:
            from macf.task.scope import get_scope_check
            from macf.task.scope_gate_failsafe import decrement_and_check, COUNT_INIT
            scope = get_scope_check()
            has_active_scope = scope["active_count"] > 0
            paused_count = scope.get("paused_count", 0)

            if has_active_scope and auto_mode:
                # FAILSAFE (BUG #1022 + #1067): if the agent keeps stopping
                # with active scope and no useful work between stops, decrement
                # an idle counter. At 0 we let the stop succeed so the agent
                # escapes the deadlock loop. PreToolUse activity resets the
                # counter, so a working agent keeps the gate active.
                #
                # BUG #1067: countdown is now SURFACED to agent (not silent).
                # Each gate firing with counter < COUNT_INIT shows the count
                # in the reason text (visible to agent) AND warns about the
                # Idle-Loop Shrinking anti-pattern when counter ≤ 2.
                _idle_remaining, _fail_open = decrement_and_check()
                if _fail_open:
                    # NOISY fail-open: stderr (existing) + systemMessage so
                    # agent SEES it (BUG #1067).
                    fail_open_msg = (
                        f"⚠️ MACF SCOPE GATE FAILSAFE — {scope['active_count']} scoped "
                        f"task(s) still active but no useful work in last {COUNT_INIT} "
                        f"stops. Allowing stop to break deadlock.\n\n"
                        f"This is the Idle-Loop Shrinking anti-pattern "
                        f"(autonomous_sprint.md §5). The agent failed to either "
                        f"(a) find substantive work, (b) pause genuinely-blocked "
                        f"items with --justification, OR (c) de-escalate to "
                        f"MANUAL_MODE. The failsafe rescued the deadlock.\n\n"
                        f"Recovery: invoke any tool to reset counter, OR pause "
                        f"blocked items via `macf_tools task scope pause <ids> "
                        f"--justification <reason>` (BUG #1067 — paused items "
                        f"don't count toward gate)."
                    )
                    print(fail_open_msg, file=sys.stderr)
                    return {"continue": True, "systemMessage": fail_open_msg}
                # ── END if _fail_open: failsafe early-return ──

                # ── Build countdown warning suffix for gate reason text ──
                # Only when counter has decremented (the agent is approaching
                # idle-loop territory). At full count (COUNT_INIT), suffix is empty.
                _countdown_suffix = ""
                if _idle_remaining < COUNT_INIT:
                    if _idle_remaining <= 2:
                        # Critical: actively warn about Idle-Loop Shrinking
                        _countdown_suffix = (
                            f"\n\n🚨 IDLE-LOOP SHRINKING WARNING 🚨\n"
                            f"   Idle-stop counter: {_idle_remaining} of {COUNT_INIT} remaining.\n"
                            f"   You have produced {COUNT_INIT - _idle_remaining} consecutive "
                            f"responses without tool calls while scope is open. This is the "
                            f"Idle-Loop Shrinking anti-pattern (autonomous_sprint.md §5).\n"
                            f"   In {_idle_remaining} more idle stops, the failsafe will "
                            f"fail-open and let the stop succeed — leaving scoped work in an "
                            f"undocumented incomplete state.\n"
                            f"   Resolve NOW by ONE of:\n"
                            f"   (a) Find substantive work (substrate maintenance always "
                            f"available: design drafts, telemetry, learning curation)\n"
                            f"   (b) Pause genuinely-blocked items: `macf_tools task scope "
                            f"pause <ids> --justification <reason>` — paused items satisfy "
                            f"the gate without forcing completion\n"
                            f"   (c) De-escalate: `macf_tools mode set MANUAL_MODE "
                            f"--justification <reason>` (emergency only)\n"
                            f"   Single-token / acknowledgment-only responses are a "
                            f"discipline failure, NOT a graceful exit."
                        )
                    else:
                        # Soft countdown: just the count
                        _countdown_suffix = (
                            f"\n\n⚠️ Idle-stop counter: {_idle_remaining} of {COUNT_INIT} "
                            f"remaining (failsafe will trigger at 0). Invoke any tool to "
                            f"reset, OR pause blocked items, OR de-escalate."
                        )
                # ── END countdown surfacing ──

                # ── BEGIN scope-gate dispatch (sibling of failsafe, NOT nested inside it) ──
                task_list = "\n".join(
                    f"  - #{t['id']}: {t['subject']}" for t in scope["active"]
                )

                # --- SPRINT / PLAY_TIME dispatch (Phase 4 of MISSION 1010) ---
                # Detect autonomous-work task types in scope and route to
                # type-specific gate behavior before the generic Markov path.
                try:
                    from macf.task.sprint_gate import (
                        get_sprint_play_time_in_scope,
                        emit_scope_nag,
                        emit_chain_advance_suggestion,
                        should_fire_markov_for_play_time,
                        parse_play_time_custom,
                    )
                    autowork = get_sprint_play_time_in_scope()

                    # SPRINT: emit scope-completion nag, no Markov, no mode rotation
                    if autowork["sprint_task"] and autowork["open_children"]:
                        _nag_text = emit_scope_nag(
                            autowork["sprint_task"],
                            autowork["open_children"],
                        )
                        # Append paused summary (BUG #1067)
                        if paused_count > 0:
                            _nag_text += (
                                f"\n\n⏸️  Paused (excluded from gate): {paused_count} task(s)"
                            )
                        # Append idle countdown warning (BUG #1067)
                        _nag_text += _countdown_suffix
                        return {
                            "continue": True,
                            "decision": "block",
                            "reason": _nag_text,
                        }

                    # PLAY_TIME with chain not yet exhausted: suggest chain advance
                    if autowork["play_time_task"]:
                        pt_custom = parse_play_time_custom(autowork["play_time_task"])
                        if pt_custom and not pt_custom.chain_exhausted and (
                            pt_custom.chain_position + 1 < len(pt_custom.predetermined_chain)
                        ):
                            return {
                                "continue": True,
                                "decision": "block",
                                "reason": emit_chain_advance_suggestion(
                                    autowork["play_time_task"],
                                    pt_custom.chain_position,
                                    pt_custom.predetermined_chain,
                                ),
                            }
                        # Chain exhausted (or last step): fall through to Markov path below
                except (ImportError, OSError, ValueError) as e:
                    print(f"⚠️ MACF: sprint_gate dispatch failed: {e}", file=sys.stderr)

                # Check if a timer is active — changes the gate message
                timer_info = scope.get("timer", {})
                timer_active = timer_info.get("active", False)
                timer_remaining = timer_info.get("remaining_min", 0)

                # Notify Telegram — unique emoji: 🛡️👀 (scope + watching)
                try:
                    from macf.channels.telegram import send_telegram_notification
                    gate_msg = (f"{scope['active_count']} scoped task(s), {timer_remaining}m remaining"
                                if timer_active else f"{scope['active_count']} scoped task(s) remaining")
                    send_telegram_notification(gate_msg, prefix="\U0001f6e1\ufe0f\U0001f440 Scope gate")
                except Exception as e:
                    print(f"⚠️ MACF: Scope gate Telegram error: {e}", file=sys.stderr)

                error_context = ""
                if is_error_stop:
                    error_context = (
                        "An error occurred but you MUST NOT stop — debug and fix it. "
                        "Read the error, form a hypothesis, and try again. "
                    )

                # Timer-active scope gate: engage Markov recommender for work continuation
                if timer_active:
                    recommendation = ""
                    try:
                        active_modes = detect_active_modes(session_id, token_info)
                        current_wm = get_current_work_mode(active_modes)
                        # BUG #1081: when LOW_CONTEXT is active, suppress Markov
                        # entirely and emit the mandatory wind-down directive
                        # instead. Markov sampling at low context produces
                        # out-of-phase mode-change suggestions that compete
                        # with closeout discipline.
                        if should_suppress_markov(active_modes, current_wm) and "LOW_CONTEXT" in active_modes:
                            recommendation = "\n" + format_low_context_directive()
                        else:
                            op_modes = {m for m in active_modes if m in ("AUTO_MODE", "USER_IDLE", "QUIET_MODE", "LOW_CONTEXT")}
                            selected, dist = sample_next_work_mode(current_wm, op_modes)
                            recommendation = "\n" + format_recommendation(current_wm, selected, dist, "maceff")
                    except (OSError, ValueError, ImportError) as e:
                        print(f"⚠️ MACF: recommender failed: {e}", file=sys.stderr)

                    _paused_summary = f"\n⏸️  Paused (excluded from gate): {paused_count} task(s)" if paused_count > 0 else ""
                    return {
                        "continue": True,
                        "decision": "block",
                        "reason": (
                            f"SCOPE GATE (timer active): {timer_remaining} min remaining. "
                            f"{error_context}"
                            f"Scoped tasks: {task_list}\n"
                            f"Complete finished tasks with `macf_tools task complete <id> --report '...'` to clear them from scope. "
                            f"Only the last scoped task is timer-gated. "
                            f"ULTRATHINK about the recommendation below, then invoke the suggested skill "
                            f"(or override with justification in task notes).\n"
                            f"{recommendation}\n"
                            f"Emergency escape: macf_tools mode set MANUAL_MODE --justification <reason>"
                            f"{_paused_summary}{_countdown_suffix}"
                        ),
                    }

                # Non-timer scope gate: standard "complete these tasks" message
                _paused_summary = f"\n⏸️  Paused (excluded from gate): {paused_count} task(s)" if paused_count > 0 else ""
                return {
                    "continue": True,
                    "decision": "block",
                    "reason": (
                        f"SCOPE GATE: {scope['active_count']} scoped task(s) remaining. "
                        f"{error_context}"
                        f"Complete these tasks: {task_list} "
                        f"Emergency escape: macf_tools mode set MANUAL_MODE --justification <reason>"
                        f"{_paused_summary}{_countdown_suffix}"
                    ),
                }
                # ── END scope-gate dispatch ──

            # --- Error-resilience in ANY mode ---
            # Soft nudge when stopping on error with active tasks (scoped or in_progress)
            if is_error_stop and has_active_scope:
                # Notify Telegram — unique emoji: 🔥⚠️ (error + warning)
                try:
                    from macf.channels.telegram import send_telegram_notification
                    send_telegram_notification(
                        f"Error stop with {scope['active_count']} active task(s)",
                        prefix="\U0001f525\u26a0\ufe0f Error gate"
                    )
                except Exception as e:
                    print(f"⚠️ MACF: Error gate Telegram error: {e}", file=sys.stderr)
                task_list = "\n".join(
                    f"  - #{t['id']}: {t['subject']}" for t in scope["active"]
                )
                # MANUAL_MODE: soft nudge (systemMessage, not decision:block)
                # Agent CAN stop, but gets a strong hint to investigate first
                message += (
                    f"\n\n⚠️ ERROR DETECTED — You stopped after a tool error. "
                    f"Active scoped tasks remain:\n{task_list}\n"
                    f"Investigate the error and fix it before stopping. "
                    f"Read the error output, form a hypothesis, and retry."
                )
        except Exception as e:
            print(f"⚠️ MACF: Scope gate error (non-blocking): {e}", file=sys.stderr)

        # --- Timer gate: block stop if autonomous work timer is still active ---
        # This fires when scope is EMPTY (all tasks done) but timer hasn't expired.
        # It's the HARD enforcement of reflexive self-motivation: the agent MUST
        # scope new work and continue, not stop because "work is done."
        try:
            import time
            from macf.agent_events_log import read_events
            # Find the most recent scope_timer_set event
            for event in read_events(limit=None, reverse=True):
                if event.get("event") == "scope_timer_set":
                    timer_end = event.get("data", {}).get("timer_end_epoch", 0)
                    remaining_sec = timer_end - time.time()
                    if remaining_sec > 0:
                        remaining_min = int(remaining_sec / 60)
                        # Notify Telegram — unique emoji: ⏱️🔄 (timer + continue)
                        try:
                            from macf.channels.telegram import send_telegram_notification
                            send_telegram_notification(
                                f"{remaining_min} min remaining",
                                prefix="\u23f1\ufe0f\U0001f504 Timer gate"
                            )
                        except Exception as e:
                            print(f"⚠️ MACF: Timer gate Telegram error: {e}", file=sys.stderr)
                        # Markov recommender: suggest next work mode transition
                        # (suppressed in LOW_CONTEXT — BUG #1081 — replaced
                        # with mandatory wind-down directive).
                        recommendation = ""
                        try:
                            active_modes = detect_active_modes(session_id, token_info)
                            current_wm = get_current_work_mode(active_modes)
                            if should_suppress_markov(active_modes, current_wm) and "LOW_CONTEXT" in active_modes:
                                recommendation = "\n" + format_low_context_directive()
                            else:
                                op_modes = {m for m in active_modes if m in ("AUTO_MODE", "USER_IDLE", "QUIET_MODE", "LOW_CONTEXT")}
                                selected, dist = sample_next_work_mode(current_wm, op_modes)
                                recommendation = "\n" + format_recommendation(current_wm, selected, dist, "maceff")
                        except (OSError, ValueError, ImportError) as e:
                            print(f"⚠️ MACF: recommender failed: {e}", file=sys.stderr)

                        return {
                            "continue": True,
                            "decision": "block",
                            "reason": (
                                f"TIMER GATE: {remaining_min} min remaining on autonomous work timer. "
                                f"Scoped tasks are complete but your allotted time is NOT. "
                                f"Scope completion is a TRANSITION, not a stop signal. "
                                f"ULTRATHINK about the recommendation below, then invoke the suggested skill "
                                f"(or override with justification in task notes).\n"
                                f"{recommendation}\n"
                                f"Emergency escape: macf_tools mode set MANUAL_MODE --justification <reason>"
                            ),
                        }
                    break  # Timer expired — don't block
                elif event.get("event") == "scope_cleared":
                    break  # Scope was cleared after timer — don't search further
        except Exception as e:
            print(f"⚠️ MACF: Timer gate error (non-blocking): {e}", file=sys.stderr)

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
        # Notify Telegram about error (non-blocking)
        try:
            from macf.channels.telegram import send_telegram_notification
            send_telegram_notification(str(e), prefix="\u274c Stop hook error")
        except (ImportError, OSError, ConnectionError) as tg_e:
            print(f"⚠️ MACF: Telegram error notification also failed: {tg_e}", file=sys.stderr)
        return {
            "continue": True,
            "systemMessage": f"🏗️ MACF | ❌ Stop hook error: {e}"
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

