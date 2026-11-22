"""Tests for the idle-stop failsafe the Stop hook's gates share (BUG #1022).

Coverage target: macf/src/macf/task/scope_gate_failsafe.py

The count lives in the (per-test, isolated) event log. A blocked Stop counts as
progress only when a tool call since the previous one is new, or returned something
new; repeating an earlier check with the same answer is churn.
"""

import json
from unittest.mock import patch

from macf.agent_events_log import append_event
from macf.task import scope_gate_failsafe as sgf


def _call(command, stdout, tool="Bash", description="free text"):
    append_event("tool_call_completed", {"tool": tool}, hook_input={
        "tool_name": tool, "tool_input": {"command": command, "description": description},
        "tool_response": {"stdout": stdout, "stderr": ""}})


def test_consecutive_stops_with_no_calls_count_down_to_fail_open():
    sgf.reset()
    results = [sgf.decrement_and_check() for _ in range(sgf.COUNT_INIT)]
    assert [r for r, _ in results] == list(range(sgf.COUNT_INIT - 1, -1, -1))
    assert [f for _, f in results] == [False] * (sgf.COUNT_INIT - 1) + [True]
    assert sgf.decrement_and_check() == (0, True), "the floor is 0, never negative"


def test_repeating_the_same_check_with_the_same_answer_is_churn():
    """The 11-22 loop: each forced turn ran one cheap status check, which used to
    reset the count. Same call, same result: it must still count down."""
    sgf.reset()
    _call("watch.sh 1116", "#1116 OPEN approvals[a]")
    assert sgf.decrement_and_check() == (sgf.COUNT_INIT, False), "the first sighting is progress"
    for expected in range(sgf.COUNT_INIT - 1, 0, -1):
        _call("watch.sh 1116", "#1116 OPEN approvals[a]")
        assert sgf.decrement_and_check() == (expected, False)
    _call("watch.sh 1116", "#1116 OPEN approvals[a]")
    assert sgf.decrement_and_check() == (0, True)


def test_a_clock_reading_in_the_output_does_not_make_a_check_new():
    """Clock times, ISO stamps, a breadcrumb's t_<epoch> and run durations all vary between
    two runs of the same check with the same answer."""
    sgf.reset()
    _call("status", "11:21:04 AM wk 75% at 2026-11-22T16:21:04Z s_ab/c_1/t_1795364464 171 passed in 20.00s")
    sgf.decrement_and_check()
    _call("status", "11:26:40 AM wk 75% at 2026-11-22T16:26:40Z s_ab/c_1/t_1795364800 171 passed in 18.31s")
    assert sgf.decrement_and_check()[0] == sgf.COUNT_INIT - 1


def test_a_new_description_on_the_same_call_is_not_new():
    """The description is free text the agent writes each time; the call is the command."""
    sgf.reset()
    _call("watch.sh 1116", "same", description="Check the PR")
    sgf.decrement_and_check()
    _call("watch.sh 1116", "same", description="Look at the PR again")
    assert sgf.decrement_and_check()[0] == sgf.COUNT_INIT - 1


def test_the_idle_streak_restarts_after_progress():
    sgf.reset()
    sgf.decrement_and_check()
    sgf.decrement_and_check()
    assert sgf.idle_streak() == 2
    _call("a", "new")
    sgf.decrement_and_check()
    assert sgf.idle_streak() == 0
    sgf.decrement_and_check()
    assert sgf.idle_streak() == 1


def test_a_monitor_seeing_activity_does_not_start_an_episode():
    """Only the operator's prompt starts an episode, not another detector's sighting."""
    sgf.reset()
    _call("a", "1")
    sgf.decrement_and_check()
    append_event("user_activity_detected", {"source": "direct", "detector": "transcript_monitor"})
    _call("a", "1")
    assert sgf.decrement_and_check()[0] == sgf.COUNT_INIT - 1


def test_the_same_check_with_a_new_result_is_progress():
    sgf.reset()
    _call("watch.sh 1116", "#1116 OPEN approvals[a]")
    sgf.decrement_and_check()
    sgf.decrement_and_check()
    _call("watch.sh 1116", "#1116 OPEN approvals[a,b]")
    assert sgf.decrement_and_check() == (sgf.COUNT_INIT, False)


def test_the_operators_prompt_starts_a_fresh_episode():
    _call("watch.sh 1116", "same")
    sgf.decrement_and_check()
    sgf.decrement_and_check()
    append_event("user_activity_detected", {"source": "direct", "detector": "user_prompt_submit_hook"})
    _call("watch.sh 1116", "same")
    assert sgf.decrement_and_check() == (sgf.COUNT_INIT, False)
    assert sgf.current() == sgf.COUNT_INIT


def test_conserve_yields_on_the_first_idle_stop():
    sgf.reset()
    with patch("macf.budget.current_mode", return_value={"mode": "conserve"}):
        assert sgf.decrement_and_check() == (0, True)
    assert sgf.idle_streak() == 1, "the churn record counts one forced turn, not five"


def test_the_held_event_records_what_was_repeated():
    from macf.agent_events_log import read_events
    sgf.reset()
    _call("a", "1")
    sgf.decrement_and_check()
    _call("a", "1")
    _call("b", "2")
    sgf.decrement_and_check()
    held = next(e for e in read_events(reverse=True) if e["event"] == sgf.HELD)
    assert held["data"]["calls"] == 2 and held["data"]["repeated"] == 1 and held["data"]["progressed"]
    assert len(held["data"]["seen"]) == 2


def test_the_scope_gate_fail_open_pauses_the_scope_with_a_churn_record():
    """At 0 the stop passes and the scope is paused, so the next stop is free too."""
    from macf.hooks.handle_stop import run
    from macf.task.scope import get_scope_check, set_scope
    sgf.reset()
    set_scope(["4242"])
    with patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(True, "test")):
        results = [run(json.dumps({"stop_reason": "end_turn", "session_id": "s"}))
                   for _ in range(sgf.COUNT_INIT)]
    assert all(r.get("decision") == "block" for r in results[:-1])
    last = results[-1]
    assert last.get("decision") != "block" and "Paused the scope (#4242)" in last["systemMessage"]
    assert "task scope unpause 4242" in last["systemMessage"], "the hint must be a command that exists"
    check = get_scope_check()
    assert check["active_count"] == 0 and check["paused_count"] == 1
    from macf.agent_events_log import read_events
    paused = next(e for e in read_events(reverse=True) if e["event"] == "scope_paused")
    assert f"churn: {sgf.COUNT_INIT} forced turn(s)" in json.dumps(paused["data"]), \
        "the paused task's record says why, with the real streak"


def test_under_conserve_the_churn_record_counts_the_one_turn():
    """With COUNT_INIT in the record instead of the streak, this would say five."""
    from macf.agent_events_log import read_events
    from macf.hooks.handle_stop import run
    from macf.task.scope import set_scope
    sgf.reset()
    set_scope(["4243"])
    with patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(True, "test")), \
            patch("macf.budget.current_mode", return_value={"mode": "conserve"}):
        r = run(json.dumps({"stop_reason": "end_turn", "session_id": "s"}))
    assert r.get("decision") != "block" and "1 forced turn(s)" in r["systemMessage"]
    paused = next(e for e in read_events(reverse=True) if e["event"] == "scope_paused")
    assert "churn: 1 forced turn(s)" in json.dumps(paused["data"])
