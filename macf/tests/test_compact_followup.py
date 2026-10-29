"""A self-compacted agent gets one recovery prompt, and only when nothing else woke it.

A compaction opens no turn. An agent that ends its wind-down with ``inject compact``
otherwise sits at an empty input box, recovery unread, until something else wakes it.
"""
from dataclasses import dataclass
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


RULE = "─" * 40


def screen(box):
    """An idle session's screen with *box* in its input box."""
    return f"some output\n{RULE}\n❯ {box}\n{RULE}\n  ⏵⏵ auto mode on\n"


@dataclass
class Run:
    outcome: str
    sent: list
    enters: list


def _run(rows_by_call, timeout=10.0, takes_on=1, box=None):
    """A pane whose Enter starts a turn on the *takes_on*-th press (0: never); until then
    the typed text stays in the box. *box* overrides what the box shows."""
    sent, enters, now = [], [], [T0]
    calls = iter(rows_by_call)
    typed = {}

    def read(since):
        rows = list(next(calls, rows_by_call[-1]))
        if takes_on and len(enters) >= takes_on:
            rows.append(ev("dev_drv_started", enters[takes_on - 1] + 0.5))
        return rows

    def capture():
        shown = box() if callable(box) else box
        if shown is not None:
            return screen(shown)
        done = takes_on and len(enters) >= takes_on
        return screen("" if done else typed.get("text", ""))

    def send(t, keys):
        sent.append((t, keys))
        typed["text"] = " ".join(keys)
        return 0

    def enter():
        enters.append(now[0])
        return 0

    def sleep(s):
        now[0] += s

    outcome = cf.follow("seat", T0, "recover", timeout=timeout, poll=2.0, read=read, send=send,
                        capture=capture, enter=enter, clock=lambda: now[0], sleep=sleep)
    return Run(outcome, sent, enters)


def test_follow_types_the_text_into_the_target_once():
    rows = [ev("compaction_detected", T0 + 1)]
    r = _run([[], rows, rows, rows, rows])
    assert r.outcome == "sent"
    assert r.sent == [("seat", ["recover"])] and len(r.enters) == 1


def test_follow_gives_up_without_typing_when_no_compaction_comes():
    r = _run([[]], timeout=10.0)
    assert r.outcome.startswith("gave up")
    assert r.sent == [] and r.enters == []


def test_an_enter_taken_into_the_text_is_pressed_again():
    """A seat's box held the prompt, unsent, for fourteen hours while the log said sent
    (Oct 14): the Enter had landed with the text. Enter is pressed again while the text
    is still in the box."""
    rows = [ev("compaction_detected", T0 + 1)]
    r = _run([[], rows, rows], takes_on=2)
    assert r.outcome == "sent" and len(r.enters) == 2


def test_without_a_turn_it_says_so_instead_of_sent():
    rows = [ev("compaction_detected", T0 + 1)]
    r = _run([[], rows, rows], takes_on=0)
    assert r.outcome.startswith("typed, but no turn started") and len(r.enters) == cf.MAX_ENTERS


def test_nothing_is_typed_after_a_draft():
    """Typed after a draft, the prompt is sent with it as one. A follower's unsent text sat in
    a box for 29 hours, and the next inject typed /compact onto its end (Oct 16)."""
    rows = [ev("compaction_detected", T0 + 1)]
    r = _run([[], rows, rows], takes_on=0, box="the operator was typing this")
    assert r.sent == [] and r.enters == []
    assert r.outcome == "gave up: the input box was never idle and empty (last seen: draft)"


def test_it_types_once_the_box_empties():
    rows = [ev("compaction_detected", T0 + 1)]
    boxes = iter(["a draft", "a draft"])
    r = _run([[], rows], timeout=30.0, box=lambda: next(boxes, None))
    assert r.outcome == "sent" and r.sent == [("seat", ["recover"])]


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
    r = _run([[], rows])
    assert r.outcome.startswith("skipped")
    assert r.sent == [] and r.enters == []


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


def test_remote_mode_holds_through_the_recovery_prompt_and_a_channel_message(isolated_events_log, monkeypatch):
    """Review of this PR: the prompt hook lifted USER_REMOTE's deny on every prompt. A prompt
    the framework typed, or a channel message, is not the operator back at the keyboard."""
    import subprocess
    from macf import supervisor
    from macf.hooks import handle_user_prompt_submit as hook
    restores = []
    monkeypatch.setattr("macf.utils.claude_settings.restore_user_remote_deny_if_active",
                        lambda: restores.append(1) or {"restored": False})
    done = subprocess.CompletedProcess([], 0, "", "")
    with patch.object(supervisor, "_tmux_available", return_value=True), \
         patch.object(supervisor, "_find_supervisor", return_value={"tmux_session": "seat", "name": "s"}), \
         patch.object(supervisor.subprocess, "run", return_value=done):
        supervisor.send_keys("s", [cf.DEFAULT_TEXT], enter=True, kind="compact-followup")
    follower = cf.DEFAULT_TEXT
    channel = '<channel source="plugin:telegram:telegram" chat_id="1">back soon</channel>'
    typed = "check the indexer"
    for prompt, expect in ((follower, False), (channel, False), (typed, True)):
        recorded = hook.record_user_activity_from_payload(prompt)
        assert hook.maybe_restore_user_remote(prompt, recorded) is expect, prompt[:20]
    assert len(restores) == 1          # only the typed prompt asked


def test_a_targeted_inject_starts_no_follower_and_says_so(capsys):
    with patch("macf.supervisor.send_keys", return_value=0) as send, \
         patch("macf.supervisor._start_compact_followup") as follower:
        from macf import supervisor
        assert supervisor.send_slash_to_self("compact", target="other", then="recover") == 0
    follower.assert_not_called()
    send.assert_called_once()
    assert "no recovery prompt follows" in capsys.readouterr().err


def test_inject_refuses_to_type_a_command_after_a_draft(capsys):
    """The client runs a slash command only when it is the whole prompt."""
    from macf import supervisor
    with patch.object(supervisor, "_find_own_supervisor", return_value={"name": "me"}), \
         patch.object(supervisor, "_draft_in_box", return_value="left over from a follower"), \
         patch.object(supervisor, "send_keys", return_value=0) as send, \
         patch.object(supervisor, "_start_compact_followup") as start, \
         patch("macf.stop_bypass.arm") as arm:
        assert supervisor.send_slash_to_self("compact", then="recover") == 1
    assert not send.called and not start.called and not arm.called
    assert "already holds text" in capsys.readouterr().err


def test_inject_types_when_the_box_is_empty_or_unreadable():
    from macf import supervisor
    for draft in ("", None):
        with patch.object(supervisor, "_find_own_supervisor", return_value={"name": "me"}), \
             patch.object(supervisor, "_draft_in_box", return_value=draft), \
             patch.object(supervisor, "send_keys", return_value=0) as send, \
             patch.object(supervisor, "_start_compact_followup"), \
             patch("macf.stop_bypass.arm"):
            assert supervisor.send_slash_to_self("compact", then="recover") == 0
        send.assert_called_once_with("me", ["/compact"], enter=True, kind="inject")
