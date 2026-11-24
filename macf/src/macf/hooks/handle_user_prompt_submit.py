#!/usr/bin/env python3
"""
handle_user_prompt_submit - UserPromptSubmit hook runner.

DEV_DRV start tracking + full temporal + token/CL awareness injection.
EXPERIMENT: Claude-mem associative memory injection (Cycle 337)
"""
import json
import re
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from macf.utils import (
    format_macf_brand,
    get_temporal_context,
    format_macf_footer,
    get_rich_environment_string,
    get_current_session_id,
    start_dev_drv,
    get_token_info,
    format_token_context_full,
    get_boundary_guidance,
    # Note: mode indicators imported separately below
    get_breadcrumb
)
from macf.modes import detect_auto_mode
from macf.hooks.hook_logging import log_hook_event
from macf.observability import Warning, emit_warning
from macf.agent_events_log import shared_event_reads
from macf.utils.input_origin import (
    entry_text,
    opening_channel_source,
    opens_with_harness_notice,
    opens_with_wake,
    operator_channel,
    typed_by_framework,
)
from macf.channels.channel_tag import CHANNEL_SOURCE, is_maceff_notice, opening_tag

# Lines that change on every prompt by design. The diff header carries them
# (clock, breadcrumb, CL); diffing them would report a change every time.
UPS_VOLATILE = ("Current Time:", "Breadcrumb:", "Tokens Used:", "CL Level:", "Remaining:", "Weekly usage:")

#: How much earlier than a message's own time a downloaded voice file may be and still be its audio.
_VOICE_CLOCK_SLACK_S = 5.0


def voice_file_for_message(prompt: str, now_inbox: Optional[Path] = None) -> Optional[Path]:
    """The downloaded audio of the voice message in ``prompt``, or None when it isn't downloaded yet.

    The newest ``.oga`` in an inbox is not necessarily this message's: the hook usually runs before the
    message is downloaded, and an older voice file then sat newest, so a clip from months before was
    transcribed as the message (#1079). A file counts only when it was written at or after the
    message's own ``ts``, and the oldest such file is taken: a later voice message's file is written after
    this one's. The inbox is the plugin's state directory: ``TELEGRAM_STATE_DIR``, else the
    account default."""
    import datetime as _dt
    m = re.search(r'\bts="([^"]+)"', prompt)
    if not m:
        return None
    try:
        sent = _dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).timestamp()
    except ValueError as e:
        print(f"⚠️ MACF: voice message time unreadable ({e}); not guessing its audio file", file=sys.stderr)
        return None
    state = os.environ.get("TELEGRAM_STATE_DIR")
    inbox = now_inbox or ((Path(state) if state else Path.home() / ".claude" / "channels" / "telegram") / "inbox")
    try:
        fresh = [f for f in inbox.glob("*.oga") if f.stat().st_mtime >= sent - _VOICE_CLOCK_SLACK_S]
    except OSError as e:
        print(f"⚠️ MACF: voice inbox unreadable ({e})", file=sys.stderr)
        return None
    return min(fresh, key=lambda f: f.stat().st_mtime) if fresh else None


#: How much of the transcript's end is read to find the entry for a prompt.
_TRANSCRIPT_TAIL_BYTES = 64 * 1024


def scheduled_prompt(prompt: str, transcript_path: Optional[str]) -> bool:
    """True when the transcript's newest entry for ``prompt`` says the client fired it on a schedule.

    The payload carries a prompt's text and nothing about where it came from.
    A session's scheduled prompt is written to the transcript, marked
    ``turnOrigin: scheduled``, before this hook runs, so the end of the file
    can say. When it cannot (no path, no entry yet, an unreadable file), the
    prompt is read as typed, as it was before.
    """
    if not transcript_path:
        return False
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - _TRANSCRIPT_TAIL_BYTES))
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError as e:
        print(f"⚠️ MACF: cannot read the transcript's end to place a prompt: {e}", file=sys.stderr)
        return False
    wanted = prompt.strip()
    for line in reversed(tail.splitlines()):
        if '"turnOrigin"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:  # noqa: S112 - the window's first line is cut mid-object on every read, so a warning would fire on every prompt
            continue  # only the window's first line can be cut short
        message = entry.get("message")
        if entry.get("type") == "user" and isinstance(message, dict) \
                and entry_text(message.get("content", "")) == wanted:
            return entry.get("turnOrigin") == "scheduled"
    return False


def maybe_restore_user_remote(prompt: str, recorded: bool) -> bool:
    """Lift USER_REMOTE's deny only for a prompt the operator typed: one that counted as
    activity (so not framework-typed, not a wake or a harness notice) and arrived directly
    rather than through a channel. Returns whether a restore was asked for."""
    if not recorded or opening_channel_source(prompt) is not None:
        return False
    try:
        from macf.utils.claude_settings import restore_user_remote_deny_if_active
        restored = restore_user_remote_deny_if_active()
        if restored and restored.get("restored"):
            from macf.agent_events_log import append_event
            append_event("mode_change", {
                "mode": "USER_REMOTE",
                "enabled": False,
                "source": "auto_restore_on_cli_activity",
            })
    except Exception as e:  # noqa: BLE001 - a failed restore is reported, never fatal to the prompt
        emit_warning(Warning(source="user_prompt_submit",
                             kind="user_remote_auto_restore_failed",
                             detail=str(e)))
    return True


def maybe_enter_user_remote(prompt: str, recorded: bool) -> bool:
    """Enter USER_REMOTE when the operator writes from their own channel while away from the
    CLI: a prompt that counted as activity (so from a channel the declaration lists as the
    operator's, never the MacEff channel, a wake or framework-typed keys), with no message typed
    at the CLI inside the idle window. The operator is present but the CLI is unattended, which
    is what USER_REMOTE means, so it is entered as ``mode set USER_REMOTE`` would: the event,
    then the Ask-list flipped to Deny. Their next message at the CLI clears it, as before.
    Returns whether it was entered."""
    if not recorded or opening_channel_source(prompt) is None:
        return False
    try:
        import time

        from macf.config import resolve_setting
        from macf.modes.detection import _CLI_ACTIVITY_SOURCES, _detect_user_remote, _had_user_activity_since
        if _detect_user_remote(""):
            return False
        idle_mins, _ = resolve_setting("MACF_USER_IDLE_TIMEOUT_MINS", "session.user_idle_timeout_mins", 10, coerce=int)
        if _had_user_activity_since(time.time() - idle_mins * 60, sources=_CLI_ACTIVITY_SOURCES):
            return False   # typed at the CLI just now: the operator is here, writing from both
        from macf.agent_events_log import append_event
        append_event("mode_change", {"mode": "USER_REMOTE", "enabled": True,
                                     "source": "auto_on_operator_channel_while_away"})
        from macf.utils.claude_settings import toggle_user_remote_deny_permissions
        toggle_user_remote_deny_permissions(True)
        return True
    except Exception as e:  # noqa: BLE001 - a failed switch is reported, never fatal to the prompt
        emit_warning(Warning(source="user_prompt_submit", kind="user_remote_auto_enter_failed", detail=str(e)))
        return False


def record_user_activity_from_payload(prompt: str, transcript_path: Optional[str] = None) -> bool:
    """Record user activity when *this* invocation carries a typed prompt.

    USER_IDLE is derived from ``user_activity_detected`` events, which the
    Transcript Monitor writes on an interval. This hook fires the instant the
    user submits — before TM has polled — so a staleness computation here reads
    the *previous* activity and can render 😴 on the very prompt that disproves
    it (cversek/MacEff#181). The hook does not need to ask a monitor whether
    the user is active: the user just acted, and the payload proves it.

    ``dev_drv_started`` was deliberately removed as an idle source because it
    fires on *all* UserPromptSubmit invocations, including system-generated
    ones, which reset the idle timer from the agent's own activity. That
    constraint still holds, so the discrimination is made from the payload
    rather than by trusting every invocation: a typed prompt (direct, slash
    command, or channel message) is user input. A non-empty prompt is not
    always one: the client also delivers a background task's completion
    notice and another session's message as prompts, and those open with
    the client's own notice forms, so they record nothing. Nor does a wake,
    which the persistent layer types into the input box with its own opening
    (MIS-0002-R106), or a prompt the session's own schedule fired, which the
    transcript marks before the hook runs, or keys the framework typed, which
    their sender recorded before sending.

    Emitting here (rather than only suppressing the indicator) also corrects
    the clock for the renders that follow — Stop, PreToolUse — instead of
    leaving them a TM poll interval behind.

    Args:
        prompt: The ``prompt`` field of the hook payload.
        transcript_path: The payload's ``transcript_path``, where a scheduled
            prompt's entry is looked up.

    Returns:
        True when an activity event was recorded.
    """
    if not prompt or not prompt.strip():
        return False
    if opens_with_harness_notice(prompt) or opens_with_wake(prompt):
        return False
    if scheduled_prompt(prompt, transcript_path):
        return False
    # One keystroke record per arrival, with this session's hook as the consumer.
    if typed_by_framework(prompt, consumer=f"prompt_hook:{transcript_path or ''}"):
        return False

    channel_source = opening_channel_source(prompt)
    # A channel counts as the operator only by a name the agent declares as theirs,
    # and the MacEff channel, the persistent layer's, never does (R107). The
    # transcript monitor asks the same of the same name.
    if channel_source is not None and not operator_channel(channel_source):
        return False

    source = "channel" if channel_source is not None else "direct"
    try:
        from macf.agent_events_log import append_event
        append_event("user_activity_detected", {
            "source": source,
            "detector": "user_prompt_submit_hook",
        })
        return True
    except (OSError, ValueError, ImportError) as e:
        emit_warning(Warning(
            source="user_prompt_submit",
            kind="user_activity_emit_failed",
            detail=f"could not record user activity from payload: {e}",
        ))
        return False


def record_channel_receipt(prompt: str) -> bool:
    """Record that this session took a MacEff channel notice, and when.

    Claude Code acknowledges nothing to a channel, so the received time of a notice
    (the third time of MIS-0002-R39 (notice_MUST_carry_three_times)) has to come from
    inside the session. This hook runs on the event 26 ms after the channel sent it,
    measured on 2.1.296 (MIS-0002-R120 (prompt_hook_MUST_record_notice_receipt)). On a
    busy session the hook runs when the client hands the event to the turn, and that is
    the time recorded.

    Returns:
        True when a receipt event was recorded.
    """
    if not is_maceff_notice(prompt):
        return False
    attrs = opening_tag(prompt) or {}
    try:
        from macf.agent_events_log import append_event
        append_event("notice_received", {
            "notice_id": attrs.get("notice_id"),
            "notice_source": attrs.get("notice_source"),
            "channel": CHANNEL_SOURCE,
            "sent_at": attrs.get("sent_at"),
            "received_at": f"{time.time():.3f}",
        })
        return True
    except (OSError, ValueError, ImportError) as e:
        emit_warning(Warning(
            source="user_prompt_submit",
            kind="notice_receipt_emit_failed",
            detail=f"could not record a channel notice's receipt: {e}",
        ))
        return False


@shared_event_reads
def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """
    Run UserPromptSubmit hook logic.

    Tracks DEV_DRV start and injects temporal + token/CL awareness.

    Args:
        stdin_json: JSON string from stdin (Claude Code hook input)
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
        from macf.utils.session import get_last_user_prompt_uuid
        current_prompt_uuid = get_last_user_prompt_uuid(session_id, transcript_path=transcript_path)

        # Capture the FULL operator prompt for forensic recovery and prompt-content
        # analysis (#119). This was truncated to the first 200 chars, which silently
        # biased any analysis of prompt content — 35% of prompts hit the cap exactly,
        # so anything said mid-message was invisible and unrecoverable once logged.
        # Follow-up (idea): store a transcript pointer rather than inlining full text,
        # per 'Index Metadata, Not Content' — the transcript already holds the text.
        prompt = hook_input.get('prompt', '') if hook_input else ''
        prompt_preview = prompt if prompt else None

        # Record activity from the payload in hand before anything derives
        # staleness from the event log, so this render and the ones after it
        # agree with the event that produced them (#181).
        recorded = record_user_activity_from_payload(prompt, transcript_path)
        try:
            from macf.agent_events_log import append_event as _append_cause
            from macf.usage_meter import classify_prompt
            _append_cause("turn_cause", {"cause": classify_prompt(prompt or "")})
        except (ImportError, OSError, ValueError, TypeError) as _ce:
            emit_warning(Warning(source="user_prompt_submit", kind="turn_cause_failed",
                                 detail=f"turn cause not recorded ({_ce}); usage metering will read the previous cause"))
        record_channel_receipt(prompt)

        # USER_REMOTE auto-restore: a prompt the operator typed at the keyboard means
        # they are back, which auto-clears USER_REMOTE; restore the deny'd permissions
        # too. Only that prompt: one the framework typed (a wake, a recovery prompt)
        # or a channel message is not the operator at the keyboard, and lifting the
        # deny for it ended remote mode for an operator still away.
        maybe_restore_user_remote(prompt, recorded)
        # USER_REMOTE auto-enter: a message from the operator's own channel while nothing was
        # typed at the CLI inside the idle window means they are present, but not at the CLI.
        maybe_enter_user_remote(prompt, recorded)

        # Start Development Drive tracking with current UUID and prompt preview
        # Note: start_dev_drv() emits dev_drv_started event internally
        start_dev_drv(session_id, prompt_uuid=current_prompt_uuid, prompt_preview=prompt_preview)

        # Get breadcrumb
        breadcrumb = get_breadcrumb()

        # Get temporal context
        temporal_ctx = get_temporal_context()
        environment = get_rich_environment_string()

        # Get token context
        token_info = get_token_info(session_id)
        auto_mode, _ = detect_auto_mode(session_id)

        # Mode indicators for status line
        try:
            from macf.modes import detect_active_modes, format_mode_indicators
            active_modes = detect_active_modes(session_id, token_info)
            mode_indicator = format_mode_indicators(active_modes)
        except (OSError, ValueError, ImportError) as e:
            emit_warning(Warning(source="user_prompt_submit", kind="mode_detection_failed", detail=f"mode detection failed in UPS hook: {e}"))
            mode_indicator = " 🤖" if auto_mode else ""

        # Format temporal section with breadcrumb
        temporal_section = f"""{format_macf_brand(indicators=mode_indicator)} | DEV_DRV Started
Current Time: {temporal_ctx['timestamp_formatted']}
Day: {temporal_ctx['day_of_week']}
Time of Day: {temporal_ctx['time_of_day']}
Breadcrumb: {breadcrumb}"""

        # Format token section
        token_section = format_token_context_full(token_info)
        # The subscription budget: one line only when a limit crosses a band (credit_budget policy)
        from macf.budget import hook_lines
        budget_line = hook_lines("prompt")
        if budget_line:
            token_section = f"{token_section}\n{budget_line}"
        # The week's usage from the newest sample (the record `budget status`
        # reports), read after hook_lines has had its chance to refresh it. It
        # moves on its own, so it is carried like the clock: at the end of the
        # one-line header, and as a line the diff never compares.
        from macf.budget import _usage, usage_brief, usage_line
        reading = _usage()  # one reading for both forms
        usage = usage_brief(reading=reading)  # "wk 38%", or "5h 4%" on a seat whose plan has no all-models week
        usage_long = usage_line(reading=reading)
        if usage_long:
            token_section = f"{token_section}\n{usage_long}"

        # Voice message detection: if prompt contains channel voice metadata,
        # inject a transcription directive for the agent
        voice_transcript = ""
        if prompt and 'attachment_kind="voice"' in prompt:
            try:
                file_id_match = re.search(r'attachment_file_id="([^"]+)"', prompt)
                if file_id_match:
                    file_id = file_id_match.group(1)
                    latest_voice = voice_file_for_message(prompt)
                    if latest_voice:
                        from macf.voice.transcribe import transcribe
                        result = transcribe(audio_path=str(latest_voice), language="en")
                        voice_transcript = (
                            f"\n🎤 VOICE TRANSCRIPTION (auto):\n"
                            f"[{result.engine}/{result.model} | "
                            f"{result.duration_audio:.1f}s audio | "
                            f"{result.duration_transcribe:.1f}s transcribe]\n"
                            f'"{result.text}"\n'
                        )
                    else:
                        # This message's audio isn't downloaded yet: say how to fetch it (#1079).
                        voice_transcript = (
                            f"\n🎤 VOICE MESSAGE DETECTED: Use `mcp__plugin_telegram_telegram__download_attachment` "
                            f"with file_id `{file_id}`, then `macf_tools voice transcribe <path>` to transcribe.\n"
                        )
            except Exception as e:
                voice_transcript = f"\n⚠️ Voice auto-transcription failed: {e}\n"

        # Get boundary guidance (if CL ≤ 10)
        boundary_guidance = get_boundary_guidance(token_info['cl_level'], auto_mode)

        # Per-prompt policy-recommendation injection removed (GH#211). Policy
        # discovery in MacEff is pull, not push: agents consult the corpus on
        # recognised demand (task/phase orientation, before shipping a fix, when
        # a bug resists the first hypothesis) via `macf_tools policy
        # search`/`recommend`, and task-start still auto-surfaces CEP nav guides.
        # A recommender fired into every turn was stale noise with a maintenance
        # burden; see policy_awareness §2.5.

        # Focused role: one line when something is due today/overdue or a
        # review is inside its horizon; nothing otherwise (roles policy, the
        # habituation budget). Never breaks the hook.
        focus_line = ""
        try:
            from macf.roles.hooks import prompt_line
            focus_line = prompt_line()
        except (OSError, ValueError, ImportError, AttributeError) as e:
            emit_warning(Warning(source="user_prompt_submit", kind="focus_line_failed", detail=f"focus line skipped: {e}"))

        # Format footer
        footer = format_macf_footer()

        # Combine sections into plain content (DRY - single source)
        sections = [
            temporal_section,
            token_section,
            voice_transcript if voice_transcript else "",  # Voice auto-transcription
            boundary_guidance if boundary_guidance else "",
            focus_line,
            footer
        ]
        plain_content = chr(10).join([s for s in sections if s])

        # Send only what changed since this hook last spoke (#407). The header
        # carries the lines that change every prompt; the full block goes out
        # after compaction, on a new session, and when the last one is stale.
        agent_content = operator_content = plain_content
        try:
            from macf.hooks.emission import emit
            from macf.utils import get_minimal_timestamp
            header = (f"{format_macf_brand(indicators=mode_indicator)} | DEV_DRV Started | "
                      f"{get_minimal_timestamp()} | {breadcrumb} | CL{token_info['cl_level']}"
                      + (f" | {usage}" if usage else ""))
            emission = emit("user_prompt_submit", session_id, plain_content, header, UPS_VOLATILE)
            agent_content, operator_content = emission.agent, emission.operator
        except (ImportError, OSError, ValueError, KeyError) as e:
            emit_warning(Warning(source="user_prompt_submit", kind="emission_diff_failed",
                                 detail=f"sending the full block: {e}"))

        # Notify Telegram (non-blocking)
        try:
            from macf.channels.telegram import send_telegram_notification
            send_telegram_notification(
                f"{token_section}",
                prefix="\U0001f4ac DEV_DRV Started",
                background=True,
                trace=True,
            )
        except (ImportError, OSError, ConnectionError) as e:
            emit_warning(Warning(source="user_prompt_submit", kind="telegram_send_failed", detail=f"DEV_DRV telegram notification failed (non-blocking): {e}"))

        # Pattern C: top-level systemMessage for user + hookSpecificOutput for agent
        return {
            "continue": True,
            "systemMessage": operator_content,  # TOP LEVEL - user sees this
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"<system-reminder>\n{agent_content}\n</system-reminder>"
            }
        }

    except Exception as e:
        # Log error for debugging
        log_hook_event({
            "hook_name": "user_prompt_submit",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        error_msg = f"{format_macf_brand()} | ❌ UserPromptSubmit hook error: {e}"
        return {
            "continue": True,
            "systemMessage": error_msg,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"<system-reminder>\n{error_msg}\n</system-reminder>"
            }
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

