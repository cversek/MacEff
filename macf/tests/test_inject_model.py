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


def test_no_then_arms_no_stop_passage(isolated_events_log, pane):
    """With nothing to wake the agent afterwards, the turn must not end through a sprint's scope gate."""
    assert supervisor.switch_own_model("opus", "a reason", then="") == 0
    assert stop_bypass.consume() is None
    assert not [e for e in read_events() if e.get("event") == "stop_gate_suspend_once"]


def test_answering_the_switch_dialog_is_opt_in(isolated_events_log, pane):
    _, followers = pane
    supervisor.switch_own_model("opus", "a reason")
    assert followers[-1][1].get("confirm_model") is None, "by default the cost dialog is left for a person"
    supervisor.switch_own_model("opus", "a reason", confirm=True)
    assert followers[-1][1].get("confirm_model") == "opus"


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


# The client asks "Switch model?" above the input box when the conversation is cached for the old model
# (2.1.322). On 2026-11-15 the follower read the box below as empty, since it held only a faint suggestion,
# typed its prompt into the dialog, and the session waited on the dialog until the operator answered it.
RULE = chr(0x2500) * 80


def switch_screen(offered="Fable 5.2"):
    return "\n".join([
        "● earlier output", RULE, "  Switch model?", "  Your next response will be slower and use more tokens", "",
        "  This conversation is cached for the current model.", "",
        f"  {chr(0x276F)} 1. Yes, switch to {offered}", "    2. No, go back", "",
        chr(0x2500) * 60 + " THM_ee5cs8 " + chr(0x2500),
        chr(0x276F) + " \x1b[2mPress up to edit queued messages\x1b[0m", chr(0x2500) * 40])


IDLE = "\n".join(["● done", RULE, chr(0x276F) + " ", RULE])


def test_a_dialog_drawn_above_the_box_is_a_dialog_not_an_empty_box():
    from macf.pd import wake
    assert wake.classify(switch_screen()) == wake.DIALOG, "nothing may be typed into it"
    assert wake.switch_dialog_model(switch_screen()) == "Fable 5.2"
    assert wake.switch_dialog_model(IDLE) is None and wake.classify(IDLE) == wake.IDLE_EMPTY


@pytest.mark.parametrize("asked,shown,same", [
    ("fable", "Fable 5.2", True), ("opus", "Opus 5.5", True), ("claude-opus-5-5", "Opus 5.5", True),
    ("opus[1m]", "Opus 5.5", True), ("opus", "Fable 5.2", False), ("default", "Opus 5.5", False),
    ("claude-opus-4-1", "Opus 5.5", False)])
def test_the_dialog_is_matched_to_the_model_asked(asked, shown, same):
    assert compact_followup.same_model(asked, shown) is same


def _follow(screens, confirm_model):
    """Run the follower over a turn that has ended, with *screens* captured in turn; the keys it pressed."""
    pressed, typed, now = [], [], [1000.0]
    shown = iter(screens)
    last = [None]

    def capture():
        last[0] = next(shown, last[0])
        return last[0]

    def read(since):
        events = [{"event": "dev_drv_ended", "timestamp": 900.0}]
        return events + ([{"event": "dev_drv_started", "timestamp": now[0]}] if typed else [])

    def sleep(s):
        now[0] += s
    outcome = compact_followup.follow(
        "sup:1", 899.0, "wake text", read=read, send=lambda t, keys: typed.append(keys) or 0, capture=capture,
        enter=lambda: pressed.append("Enter") or 0, width=lambda: 120, clock=lambda: now[0], sleep=sleep,
        timeout=60.0, after=compact_followup.TURN_END_EVENT, confirm_model=confirm_model)
    return {"outcome": outcome, "pressed": pressed, "typed": typed}


def test_the_follower_answers_the_switch_dialog_for_the_model_asked_then_wakes_the_agent():
    run = _follow([switch_screen(), IDLE], "fable")
    assert run["pressed"][:1] == ["Enter"] and run["typed"] == [["wake text"]] and run["outcome"] == "sent"


def test_a_dialog_for_another_model_is_left_for_a_person():
    run = _follow([switch_screen("Opus 5.5")], "fable")
    assert run["pressed"] == [] and run["typed"] == [] and "left for a person" in run["outcome"]


def test_with_no_confirm_the_dialog_is_left_for_a_person():
    run = _follow([switch_screen()], None)
    assert run["pressed"] == [] and run["typed"] == [] and "waits for a person" in run["outcome"]


def test_the_follower_says_what_it_will_do_after_a_switch_not_after_a_compaction():
    notice = supervisor._followup_notice(compact_followup.TURN_END_EVENT, "fable")
    assert "compaction" not in notice and "Switch model?" in notice and "fable" in notice
    assert "compaction" in supervisor._followup_notice(None, None), "inject compact keeps its notice"


def test_a_dialog_still_drawn_just_after_the_answer_gets_a_grace_period_not_a_second_enter():
    run = _follow([switch_screen(), switch_screen(), IDLE], "fable")
    assert run["pressed"].count("Enter") >= 1 and run["typed"] == [["wake text"]] and run["outcome"] == "sent"
    assert run["pressed"][:2] != ["Enter", "Enter"] or run["typed"], "the dialog is never answered twice"


def test_a_dialog_that_never_closes_is_left_for_a_person_after_one_answer():
    run = _follow([switch_screen()] * 40, "fable")
    assert run["pressed"] == ["Enter"] and run["typed"] == [] and "still drawn" in run["outcome"]


def test_a_numbered_list_echoed_above_an_empty_box_is_not_a_dialog():
    from macf.pd import wake
    echo = "\n".join(["● Here are the options I see:", f"  {chr(0x276F)} 1. keep the branch", "    2. merge it",
                      RULE, chr(0x276F) + " ", RULE])
    assert wake.classify(echo) == wake.IDLE_EMPTY, "no question line above the list, so a wake may still be typed"
