"""The prompt hook transcribes this voice message's audio, never an older file left in the inbox (#1079)."""
import os
from datetime import datetime, timezone

from macf.hooks.handle_user_prompt_submit import voice_file_for_message


def _prompt(ts):
    return (f'<channel source="plugin:telegram:telegram" ts="{ts}" attachment_kind="voice" '
            f'attachment_file_id="AbC">(voice message)</channel>')


def _file(inbox, name, when):
    p = inbox / name
    p.write_bytes(b"audio")
    os.utime(p, (when, when))
    return p


def test_an_older_voice_file_is_not_taken_for_this_message(tmp_path):
    sent = datetime(2026, 11, 20, 21, 30, tzinfo=timezone.utc).timestamp()
    _file(tmp_path, "old.oga", sent - 200 * 86400)
    assert voice_file_for_message(_prompt("2026-11-20T21:30:00.000Z"), now_inbox=tmp_path) is None


def test_this_message_s_download_is_taken(tmp_path):
    sent = datetime(2026, 11, 20, 21, 30, tzinfo=timezone.utc).timestamp()
    _file(tmp_path, "old.oga", sent - 200 * 86400)
    mine = _file(tmp_path, "new.oga", sent + 20)
    assert voice_file_for_message(_prompt("2026-11-20T21:30:00.000Z"), now_inbox=tmp_path) == mine


def test_the_inbox_follows_the_plugin_state_dir(tmp_path, monkeypatch):
    sent = datetime(2026, 11, 20, 21, 30, tzinfo=timezone.utc).timestamp()
    (tmp_path / "inbox").mkdir()
    mine = _file(tmp_path / "inbox", "new.oga", sent + 1)
    monkeypatch.setenv("TELEGRAM_STATE_DIR", str(tmp_path))
    assert voice_file_for_message(_prompt("2026-11-20T21:30:00.000Z")) == mine


def test_a_message_with_no_time_gets_no_guess(tmp_path):
    assert voice_file_for_message('attachment_kind="voice"', now_inbox=tmp_path) is None
