"""A self-compacted agent gets one recovery prompt, and only when nothing else woke it.

A compaction opens no turn. An agent that ends its wind-down with ``inject compact``
otherwise sits at an empty input box, recovery unread, until something else wakes it.
"""
from unittest.mock import patch

from macf import compact_followup as cf

T0 = 1_000.0


def ev(name, ts):
    return {"event": name, "timestamp": ts}


def test_waits_until_the_compaction_is_in_the_log():
    assert cf.decide([ev("tool_call_started", T0 + 1)], T0, T0 + 60) == "wait"


def test_an_older_compaction_does_not_count():
    """The previous cycle's compaction is not the one this injection queued."""
    assert cf.decide([ev("compaction_detected", T0 - 5)], T0, T0 + 60) == "wait"


def test_waits_for_the_session_start_hook_to_settle():
    assert cf.decide([ev("compaction_detected", T0 + 10)], T0, T0 + 12) == "wait"


def test_sends_once_settled():
    assert cf.decide([ev("compaction_detected", T0 + 10)], T0, T0 + 10 + cf.SETTLE_SECONDS) == "send"


def test_skips_when_a_prompt_started_after_the_compaction():
    """A mail clock or the operator got there first: a second prompt would collide."""
    rows = [ev("compaction_detected", T0 + 10), ev("dev_drv_started", T0 + 11)]
    assert cf.decide(rows, T0, T0 + 60) == "skip"


def test_a_prompt_before_the_compaction_is_not_a_wake():
    """The turn that queued /compact started before it; that prompt must not cause a skip."""
    rows = [ev("dev_drv_started", T0 + 1), ev("compaction_detected", T0 + 10)]
    assert cf.decide(rows, T0, T0 + 60) == "send"


def _run(rows_by_call, timeout=10.0):
    sent, now = [], [T0]
    calls = iter(rows_by_call)

    def read(since):
        return next(calls, rows_by_call[-1])

    def sleep(s):
        now[0] += s

    outcome = cf.follow("seat", T0, "recover", timeout=timeout, poll=2.0, read=read,
                        send=lambda t, keys: sent.append((t, keys)) or 0,
                        clock=lambda: now[0], sleep=sleep)
    return outcome, sent


def test_follow_types_the_text_into_the_target_once():
    rows = [ev("compaction_detected", T0 + 1)]
    outcome, sent = _run([[], rows, rows, rows, rows])
    assert outcome == "sent"
    assert sent == [("seat", ["recover"])]


def test_follow_gives_up_without_typing_when_no_compaction_comes():
    outcome, sent = _run([[]], timeout=10.0)
    assert outcome.startswith("gave up")
    assert sent == []


def test_inject_compact_starts_the_follower_only_after_delivery():
    from macf import supervisor
    with patch.object(supervisor, "_find_own_supervisor", return_value={"name": "me"}), \
         patch.object(supervisor, "send_keys", return_value=0), \
         patch.object(supervisor, "_start_compact_followup") as start, \
         patch("macf.stop_bypass.arm"):
        assert supervisor.send_slash_to_self("compact", then="recover") == 0
    start.assert_called_once_with("me", "recover")


def test_no_follower_for_a_failed_send_another_command_or_no_then():
    from macf import supervisor
    cases = [(1, "compact", "recover"), (0, "help", "recover"), (0, "compact", None)]
    for rc, command, then in cases:
        with patch.object(supervisor, "_find_own_supervisor", return_value={"name": "me"}), \
             patch.object(supervisor, "send_keys", return_value=rc), \
             patch.object(supervisor, "_start_compact_followup") as start, \
             patch("macf.stop_bypass.arm"):
            supervisor.send_slash_to_self(command, then=then)
        assert not start.called, (rc, command, then)


def test_cli_defaults_to_the_recovery_text_and_no_then_turns_it_off():
    import argparse
    from macf import cli
    seen = []
    with patch("macf.supervisor.send_slash_to_self",
               side_effect=lambda c, target="", then=None: seen.append(then) or 0):
        cli._cmd_inject(argparse.Namespace(command="compact", target="", then=None, no_then=False))
        cli._cmd_inject(argparse.Namespace(command="compact", target="", then=None, no_then=True))
    assert seen == [cf.DEFAULT_TEXT, None]


def test_follow_types_nothing_when_something_else_woke_the_agent():
    rows = [ev("compaction_detected", T0 + 1), ev("dev_drv_started", T0 + 3)]
    outcome, sent = _run([[], rows])
    assert outcome.startswith("skipped")
    assert sent == []


def test_the_recovery_prompt_is_never_the_operators_activity(isolated_events_log):
    """Review of this PR: a prompt the framework types must not read as the operator at the
    keyboard, or every self-compaction would end remote mode for an operator still away. The
    follower types through send_keys, which records the keys first; the prompt hook then
    counts nothing for that text."""
    import subprocess
    from macf import supervisor
    from macf.hooks.handle_user_prompt_submit import record_user_activity_from_payload
    done = subprocess.CompletedProcess([], 0, "", "")
    with patch.object(supervisor, "_tmux_available", return_value=True), \
         patch.object(supervisor, "_find_supervisor", return_value={"tmux_session": "seat", "name": "s"}), \
         patch.object(supervisor.subprocess, "run", return_value=done):
        assert supervisor.send_keys("s", [cf.DEFAULT_TEXT], enter=True) == 0
    assert record_user_activity_from_payload(cf.DEFAULT_TEXT) is False
    # and an operator's own prompt still counts
    assert record_user_activity_from_payload("check the indexer") is True
