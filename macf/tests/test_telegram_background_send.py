"""A background send starts a detached process and returns without the network.

Hooks are short-lived processes the client waits on. A thread would die with the
hook before its request finished, so the send runs in a detached child that
resolves its own credentials and records its own failures.
"""

import io
import json
import sys
import urllib.error
import urllib.parse
from unittest.mock import MagicMock, patch

from macf.channels import telegram


def test_nothing_is_started_when_no_channel_is_configured():
    """An unconfigured host, and every test, must spawn no process at all."""
    with patch("subprocess.Popen") as popen:
        result = telegram.send_telegram_notification("hello", background=True)
    assert not result and not result.deferred
    popen.assert_not_called()


def test_a_configured_send_is_handed_off_without_the_token(monkeypatch):
    monkeypatch.setattr(telegram, "resolve_telegram_config", lambda: ("SECRET-TOKEN", "42"))
    child = MagicMock()
    with patch("subprocess.Popen", return_value=child) as popen, \
         patch.object(telegram, "_urlopen_with_walltime") as urlopen:
        result = telegram.send_telegram_notification("hello", prefix="p", background=True)

    assert result.success and result.deferred
    urlopen.assert_not_called()
    args, kwargs = popen.call_args
    assert args[0] == [sys.executable, "-m", "macf.channels.telegram"]
    assert kwargs["start_new_session"] is True
    sent = child.stdin.write.call_args[0][0].decode()
    assert json.loads(sent)["text"] == "hello"
    assert "SECRET-TOKEN" not in sent and "SECRET-TOKEN" not in json.dumps(args)


def test_the_child_sends_what_it_was_handed(monkeypatch):
    monkeypatch.setattr(telegram, "resolve_telegram_config", lambda: ("tok", "42"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"text": "hello", "prefix": "p"})))
    posted = []

    def fake_urlopen(req, data=None, **_):
        posted.append(urllib.parse.parse_qs(data.decode()))
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"ok": true}'
        return response

    monkeypatch.setattr(telegram, "_urlopen_with_walltime", fake_urlopen)
    assert telegram._run_background_send() == 0
    assert posted and posted[0]["text"][0] == "p\n\nhello"


def test_a_failure_in_the_child_is_recorded_where_it_can_be_found(isolated_events_log, monkeypatch):
    """Nobody reads the child's stderr, so a failure that only printed would be lost."""
    from macf.agent_events_log import read_events
    monkeypatch.setattr(telegram, "resolve_telegram_config", lambda: ("tok", "42"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"text": "hello"})))

    def refused(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(telegram, "_urlopen_with_walltime", refused)
    assert telegram._run_background_send() == 1
    failures = [e for e in read_events(reverse=True) if e["event"] == "telegram_send_failed"]
    assert failures and failures[0]["data"]["deferred"] is True
