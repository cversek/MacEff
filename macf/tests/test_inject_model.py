"""inject model: an agent switches its own model, says why, and is woken on the new one.

The operator, 2026-11-14: "Give yourself the ability to change models with the inject command and PR it." A
model switch, like a compaction, opens no turn, so the follower that wakes an agent after a compaction is reused,
waiting for the turn's end instead.
"""
from unittest.mock import patch

import pytest

from macf import compact_followup, stop_bypass, supervisor
from macf.agent_events_log import read_events


@pytest.fixture
def pane():
    """The pane and the keys sent to it, and the followers started, with nothing really typed."""
    sent, followers = [], []
    with patch.object(supervisor, "own_pane_target", return_value="sup:1"), \
            patch.object(supervisor, "_draft_in_box", return_value=""), \
            patch.object(supervisor, "send_keys", side_effect=lambda t, keys, **k: sent.append((t, keys)) or 0), \
            patch.object(supervisor, "_start_compact_followup",
                         side_effect=lambda *a, **k: followers.append((a, k)) or True):
        yield sent, followers


def test_a_named_switch_is_typed_recorded_armed_and_followed(isolated_events_log, pane):
    sent, followers = pane
    assert supervisor.switch_own_model("opus", "the operator: execution with Opus") == 0
    assert sent == [("sup:1", ["/model opus"])]
    asked = [e for e in read_events() if e.get("event") == "model_change_asked"]
    assert [e["data"]["model"] for e in asked] == ["opus"]
    assert asked[0]["data"]["reason"] == "the operator: execution with Opus"
    assert stop_bypass.consume() is not None, "the queued /model can only run if the turn may end"
    (target, text), options = followers[0]
    assert target == "sup:1" and options["after"] == compact_followup.TURN_END_EVENT
    assert text.startswith("🏗️ MACF") and "opus" in text, "the wake is the framework's, and names the model"


@pytest.mark.parametrize("name", ["", "gpt-5", "opus /exit", "opus\n/exit", "claude-", "fable; rm"])
def test_nothing_but_a_model_name_is_typed(isolated_events_log, pane, name):
    sent, _ = pane
    assert supervisor.switch_own_model(name, "a reason") == 1
    assert sent == [], "a refused name types nothing"


@pytest.mark.parametrize("name", ["opus", "fable", "sonnet[1m]", "claude-opus-5-5", "claude-sonnet-5-5[1m]"])
def test_aliases_and_model_ids_are_accepted(isolated_events_log, pane, name):
    sent, _ = pane
    assert supervisor.switch_own_model(name, "a reason") == 0 and sent[-1][1] == [f"/model {name}"]


def test_a_switch_without_a_reason_is_refused(isolated_events_log, pane):
    sent, _ = pane
    assert supervisor.switch_own_model("opus", "   ") == 1 and sent == []
    assert not [e for e in read_events() if e.get("event") == "model_change_asked"]


def test_no_then_starts_no_follower(isolated_events_log, pane):
    _, followers = pane
    assert supervisor.switch_own_model("opus", "a reason", then="") == 0 and followers == []


def test_the_follower_waits_for_the_turn_to_end_not_for_a_compaction():
    since = 100.0
    ended = [{"event": "dev_drv_ended", "timestamp": 110.0}]
    assert compact_followup.decide(ended, since, 120.0, after="dev_drv_ended") == "send"
    assert compact_followup.decide(ended, since, 120.0) == "wait", "inject compact still waits for its compaction"
    assert compact_followup.decide(ended + [{"event": "dev_drv_started", "timestamp": 112.0}], since, 120.0,
                                   after="dev_drv_ended") == "skip", "someone woke the agent first"


def test_the_command_line_refuses_a_bare_switch_and_another_pane(capsys):
    from macf.cli import _cmd_inject
    from types import SimpleNamespace
    base = dict(command="model", expect="", then=None, no_then=False, reason="r")
    assert _cmd_inject(SimpleNamespace(**base, value=None, target="")) == 1
    assert "picker" in capsys.readouterr().err
    assert _cmd_inject(SimpleNamespace(**base, value="opus", target="other")) == 1
    assert _cmd_inject(SimpleNamespace(**{**base, "command": "compact"}, value="opus", target="")) == 1, \
        "only model takes an argument"


def test_the_switch_is_always_allowed():
    from macf.utils.claude_settings import _PERMANENT_ALLOW
    assert "Bash(macf_tools inject model:*)" in _PERMANENT_ALLOW
