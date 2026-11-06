"""A dialog nobody can answer is denied at once, when the agent has opted in and only then."""
import json
from unittest.mock import patch

import pytest

from macf import permission_watch as pw
from macf.hooks import handle_permission_request as hook


@pytest.mark.parametrize("modes, play_time, permission_mode, denied", [
    ({"AUTO_MODE"}, False, "auto", False),                   # the operator attends in AUTO_MODE
    ({"AUTO_MODE", "USER_IDLE"}, False, "auto", True),
    ({"AUTO_MODE", "USER_REMOTE"}, False, "auto", True),
    ({"AUTO_MODE", "SPRINT"}, False, "auto", True),
    ({"AUTO_MODE"}, True, "auto", True),
    ({"USER_IDLE", "SPRINT"}, True, "auto", False),          # MANUAL_MODE: the operator drives
    ({"AUTO_MODE", "USER_IDLE"}, False, "default", False),   # every write prompts: it would block all work
])
def test_who_can_answer_decides(modes, play_time, permission_mode, denied):
    assert bool(pw.full_autonomy_denial(modes, play_time, permission_mode)) is denied


def run_hook(monkeypatch, enabled, modes):
    monkeypatch.setattr(hook, "get_current_session_id", lambda: "s")
    monkeypatch.setattr(hook, "_deny_enabled", lambda: enabled)
    monkeypatch.setattr(hook, "_autonomy_state", lambda session_id: (modes, False))
    with patch("macf.channels.telegram.send_telegram_notification") as notify:
        result = hook.run(json.dumps({"tool_name": "Bash", "permission_mode": "auto",
                                      "tool_input": {"command": "x"}}))
    return result, notify


def test_the_hook_denies_with_a_reason_and_records_it(monkeypatch, isolated_events_log):
    result, _ = run_hook(monkeypatch, True, {"AUTO_MODE", "USER_IDLE"})
    decision = result["hookSpecificOutput"]["decision"]
    assert result["hookSpecificOutput"]["hookEventName"] == "PermissionRequest"
    assert decision["behavior"] == "deny" and "operator" in decision["message"]
    events = [json.loads(line)["event"] for line in isolated_events_log.read_text().splitlines()]
    assert "permission_requested" in events and "permission_auto_denied" in events


def test_off_by_default_the_dialog_stays_up(monkeypatch, isolated_events_log):
    result, _ = run_hook(monkeypatch, False, {"AUTO_MODE", "USER_IDLE"})
    assert "hookSpecificOutput" not in result


def test_a_failed_check_leaves_the_dialog_up(monkeypatch, isolated_events_log):
    monkeypatch.setattr(hook, "get_current_session_id", lambda: "s")
    monkeypatch.setattr(hook, "_deny_enabled", lambda: True)

    def broken(session_id):
        raise OSError("no state")

    monkeypatch.setattr(hook, "_autonomy_state", broken)
    assert "hookSpecificOutput" not in hook.run(json.dumps({"tool_name": "Bash", "permission_mode": "auto"}))
