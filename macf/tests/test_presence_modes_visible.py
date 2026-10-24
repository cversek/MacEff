"""The operator sees the presence modes, and a message from their own channel while away sets
USER_REMOTE (the repo owner, 2026-10-24: "I haven't seen the USER_IDLE work mode show up ... If I
am IDLE and I send you a Telegram message -> the hooks should switch to USER_REMOTE mode")."""
import json

from macf.agent_events_log import append_event
from macf.hooks import handle_user_prompt_submit as hook
from macf.utils.statusline import format_statusline

CHANNEL = '<channel source="plugin:telegram:telegram" chat_id="1">on my way</channel>'


def _remote_changes(log):
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    return [r["data"] for r in rows if r.get("event") == "mode_change" and r["data"].get("mode") == "USER_REMOTE"]


def _denies(monkeypatch):
    calls = []
    monkeypatch.setattr("macf.utils.claude_settings.toggle_user_remote_deny_permissions",
                        lambda enable, project_root=None: calls.append(enable) or {"denied": []})
    return calls


def test_the_status_line_leads_with_the_modes():
    line = format_statusline("A@abc123", None, "Host", 1000, 1_000_000, 90, modes=" 🤖😴 🏃")
    assert line.startswith("🤖😴 🏃 | A@abc123")
    assert format_statusline("A@abc123", None, "Host", 1000, 1_000_000, 90).startswith("A@abc123")


def test_a_channel_message_while_away_from_the_cli_enters_user_remote(isolated_events_log, monkeypatch):
    denies = _denies(monkeypatch)
    recorded = hook.record_user_activity_from_payload(CHANNEL)
    assert hook.maybe_enter_user_remote(CHANNEL, recorded) is True
    assert [c["enabled"] for c in _remote_changes(isolated_events_log)] == [True]
    assert denies == [True]
    from macf.modes.detection import _detect_user_remote
    assert _detect_user_remote("")
    # A second message from the channel doesn't enter it again.
    assert hook.maybe_enter_user_remote(CHANNEL, hook.record_user_activity_from_payload(CHANNEL)) is False


def test_not_when_the_operator_just_typed_at_the_cli_or_for_a_typed_prompt(isolated_events_log, monkeypatch):
    denies = _denies(monkeypatch)
    typed = "check the indexer"
    assert hook.maybe_enter_user_remote(typed, hook.record_user_activity_from_payload(typed)) is False
    assert hook.maybe_enter_user_remote(CHANNEL, hook.record_user_activity_from_payload(CHANNEL)) is False
    assert _remote_changes(isolated_events_log) == [] and denies == []


def test_a_maceff_notice_never_enters_user_remote(isolated_events_log, monkeypatch):
    """The persistent layer's own channel is never the operator (R107), so its notice records no
    activity and can't switch the operator's presence."""
    denies = _denies(monkeypatch)
    notice = '<channel source="plugin:maceff-channel:maceff" notice_id="e-0123456789ab">x</channel>'
    assert hook.maybe_enter_user_remote(notice, hook.record_user_activity_from_payload(notice)) is False
    assert denies == []


def test_typing_at_the_cli_clears_user_remote_entered_this_way(isolated_events_log, monkeypatch):
    _denies(monkeypatch)
    monkeypatch.setattr("macf.utils.claude_settings.restore_user_remote_deny_if_active", lambda: {"restored": []})
    hook.maybe_enter_user_remote(CHANNEL, hook.record_user_activity_from_payload(CHANNEL))
    from macf.modes.detection import _detect_user_remote
    assert _detect_user_remote("")
    append_event("user_activity_detected", {"source": "direct", "detector": "test"})
    assert not _detect_user_remote("")
