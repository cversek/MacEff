"""The hooks' trace on the Telegram channel can be turned off, and alerts cannot (GH #477).

The operator follows an agent's progress elsewhere and keeps Telegram for
conversation. The trace is marked at each call site (``trace=True``); anything
unmarked is an alert and is sent whatever the setting says.
"""
import argparse
import ast
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from macf.channels import telegram
from macf.channels.telegram import HOOK_TRACE_ENV, hook_trace_setting, send_telegram_notification
from macf.cli import _build_parser, cmd_channel_telegram_hook_trace

PACKAGE = Path(telegram.__file__).resolve().parents[1]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.delenv(HOOK_TRACE_ENV, raising=False)
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        yield tmp_path


def _write_config(home, config):
    (home / ".maceff").mkdir(exist_ok=True)
    (home / ".maceff" / "config.json").write_text(json.dumps(config))


def _read_config(home):
    return json.loads((home / ".maceff" / "config.json").read_text())


TRACE_OFF = {"channels": {"telegram": {"hook_trace": False}}}


# --- the setting -----------------------------------------------------------

def test_the_trace_is_on_by_default(home):
    assert hook_trace_setting() == (True, "default")


def test_off_in_the_config_turns_it_off(home):
    _write_config(home, TRACE_OFF)
    assert hook_trace_setting() == (False, "config")


def test_the_environment_overrides_the_config(home, monkeypatch):
    _write_config(home, {"channels": {"telegram": {"hook_trace": True}}})
    monkeypatch.setenv(HOOK_TRACE_ENV, "off")
    assert hook_trace_setting() == (False, "env")


# --- the send --------------------------------------------------------------

def test_a_trace_is_not_sent_while_the_trace_is_off(home):
    _write_config(home, TRACE_OFF)
    with patch.object(telegram, "resolve_telegram_config") as resolve, \
            patch.object(telegram, "_send_in_background") as background:
        result = send_telegram_notification("x", prefix="p", background=True, trace=True)
    assert result.suppressed and not result and result.warning is None
    resolve.assert_not_called()
    background.assert_not_called()


def test_an_alert_is_sent_while_the_trace_is_off(home):
    _write_config(home, TRACE_OFF)
    handed_off = telegram.NotifyResult(success=True, deferred=True)
    with patch.object(telegram, "resolve_telegram_config", return_value=("t", "c")), \
            patch.object(telegram, "_send_in_background", return_value=handed_off) as background:
        result = send_telegram_notification("x", prefix="p", background=True)
    assert result.success and not result.suppressed
    background.assert_called_once()


def test_a_trace_is_sent_while_the_trace_is_on(home):
    handed_off = telegram.NotifyResult(success=True, deferred=True)
    with patch.object(telegram, "resolve_telegram_config", return_value=("t", "c")), \
            patch.object(telegram, "_send_in_background", return_value=handed_off) as background:
        result = send_telegram_notification("x", prefix="p", background=True, trace=True)
    assert result.success and not result.suppressed
    background.assert_called_once()


# --- the command -----------------------------------------------------------

def _run(state):
    return cmd_channel_telegram_hook_trace(argparse.Namespace(state=state))


def test_the_command_parses_on_off_and_bare():
    parser = _build_parser()
    for argv, state in ((["off"], "off"), (["on"], "on"), ([], None)):
        args = parser.parse_args(["channel", "telegram", "hook-trace", *argv])
        assert args.func is cmd_channel_telegram_hook_trace and args.state == state
    with pytest.raises(SystemExit):
        parser.parse_args(["channel", "telegram", "hook-trace", "maybe"])


def test_off_then_on_keeps_every_other_key_and_is_recorded(home, capsys):
    _write_config(home, {"task_store": {"mode": "home"}})
    with patch("macf.cli.append_event") as event:
        assert _run("off") == 0
        assert _read_config(home) == {"task_store": {"mode": "home"}, **TRACE_OFF}
        event.assert_called_once_with("channel_setting_changed", {
            "channel": "telegram", "setting": "hook_trace", "value": False, "previous": None})
        assert _run("on") == 0
    assert _read_config(home)["channels"]["telegram"]["hook_trace"] is True
    assert event.call_args.args[1]["previous"] is False


def test_bare_shows_the_setting_and_its_source(home, capsys):
    _write_config(home, TRACE_OFF)
    assert _run(None) == 0
    out = capsys.readouterr().out
    assert "hook-trace: off  (from config)" in out
    assert "Alerts still are" in out


def test_an_unreadable_config_is_refused_and_left_alone(home, capsys):
    _write_config(home, {})
    config = home / ".maceff" / "config.json"
    config.write_text("{not json")
    with patch("macf.cli.append_event") as event:
        assert _run("off") == 1
    assert config.read_text() == "{not json"
    event.assert_not_called()
    assert "refusing to overwrite" in capsys.readouterr().err


# --- which sends are trace -------------------------------------------------

TRACE = ("DELEG_DRV Started", "DELEG_DRV Booted", "DELEG_DRV Complete", "DEV_DRV Started",
         "Scope gate", "Timer gate", "Session Started", "Session Ended", "⚙")
ALERTS = ("COMPACTION IMMINENT", "Error gate", "Stop hook error")


def _sends():
    """Every call to send_telegram_notification in the package: (file, prefix, trace)."""
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "send_telegram_notification":
                continue
            keywords = {k.arg: k.value for k in node.keywords}
            prefix = keywords.get("prefix")
            if isinstance(prefix, ast.Constant):
                prefix_text = prefix.value
            else:
                prefix_text = ast.unparse(prefix) if prefix is not None else ""
            trace = keywords.get("trace")
            yield path.name, prefix_text, ast.unparse(trace) if trace is not None else None


def test_every_trace_send_is_marked_and_no_alert_is():
    sends = list(_sends())
    seen = {name for _, prefix, _ in sends for name in TRACE + ALERTS if name in prefix}
    assert seen == set(TRACE + ALERTS), "the walk missed a known send"
    for file, prefix, trace in sends:
        if any(name in prefix for name in TRACE):
            assert trace == "True", (file, prefix)
        if any(name in prefix for name in ALERTS):
            assert trace is None, (file, prefix)


def test_a_turn_end_is_trace_and_an_error_stop_is_an_alert():
    stops = [t for f, p, t in _sends() if f == "handle_stop.py" and "Agent stopped" in p]
    assert stops == ["not is_error"]


def test_the_transcript_mirror_is_trace():
    mirrors = [t for f, _, t in _sends() if f == "daemon.py"]
    assert mirrors == ["True"]
