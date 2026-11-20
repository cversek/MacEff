"""`inject exit` says what it knows about the exit, and no more (cversek/MacEff#854, point 3).

It used to report the keystrokes as the result. A client that stopped on a dialog nobody is there to
answer was still running, and the caller believed the restart was under way. #967 refuses up front
while the session has scheduled jobs; this reads the screen after /exit is typed, for the dialog a
refusal could not foresee, and names what does confirm an exit.

The screen holds the agent's own conversation too, which may quote the dialog's title, so a dialog is
its title with a menu line, and only one that wasn't there before the keys went in.
"""
from unittest.mock import patch

import pytest

from macf import supervisor

DIALOG = """  Background work is running
  The following will stop when you exit:
  > Exit and stop tasks
    Move to background and exit
    Stay
"""
CLEAN = "> \n"
QUOTING = ("I'll check why the 'Background work is running' dialog stops inject exit.\n"
           "That is the title the client shows when a session has scheduled jobs.\n> \n")


def screens(*seen):
    """A capture_pane that gives each screen in turn, then the last one for every read after."""
    queue = list(seen)
    return lambda target: queue.pop(0) if len(queue) > 1 else queue[0]


@pytest.fixture
def typed(monkeypatch):
    """/exit gets typed into a pane that has no draft, no unsent feedback and no scheduled jobs."""
    monkeypatch.setattr(supervisor.time, "sleep", lambda s: None)
    monkeypatch.setattr(supervisor, "_unsent_feedback_drafts", lambda: [])
    monkeypatch.setattr(supervisor, "_scheduled_jobs", lambda: [])
    with patch.object(supervisor, "own_pane_target", return_value="seat"), \
         patch.object(supervisor, "_draft_in_box", return_value=""), \
         patch.object(supervisor, "send_keys", return_value=0), \
         patch("macf.stop_bypass.arm"):
        yield


def test_a_client_stopped_on_the_dialog_is_an_error_that_names_it(typed, capsys):
    with patch.object(supervisor, "capture_pane", side_effect=screens(CLEAN, DIALOG)):
        assert supervisor.send_slash_to_self("exit") == 1
    err = capsys.readouterr().err
    assert "Background work is running" in err and "has not exited" in err


def test_a_clean_screen_is_not_taken_for_an_exit(typed, capsys):
    with patch.object(supervisor, "capture_pane", side_effect=screens(CLEAN)):
        assert supervisor.send_slash_to_self("exit") == 0
    err = capsys.readouterr().err
    assert "not confirmed" in err and "pd_carried" in err and "pd status" in err


def test_a_dialog_that_appears_after_a_moment_is_still_seen(typed):
    with patch.object(supervisor, "capture_pane", side_effect=screens(CLEAN, CLEAN, CLEAN, DIALOG)):
        assert supervisor.send_slash_to_self("exit") == 1


def test_a_conversation_that_quotes_the_title_is_not_a_dialog(typed, capsys):
    """The agent's own messages are on the screen. An agent working on this very issue reads and
    writes the dialog's title, and a clean /exit must not be reported as stuck (the #1038 review)."""
    with patch.object(supervisor, "capture_pane", side_effect=screens(QUOTING)):
        assert supervisor.send_slash_to_self("exit") == 0
    err = capsys.readouterr().err
    assert "has not exited" not in err and "not confirmed" in err


def test_a_dialog_already_on_the_screen_before_the_keys_is_not_reported_as_new(typed, capsys):
    with patch.object(supervisor, "capture_pane", side_effect=screens(DIALOG)):
        assert supervisor.send_slash_to_self("exit") == 0
    assert "has not exited" not in capsys.readouterr().err


def test_a_dialog_with_the_title_quoted_before_it_is_still_seen(typed):
    """What was on the screen before is judged as a dialog, not as the words in it."""
    with patch.object(supervisor, "capture_pane", side_effect=screens(QUOTING, QUOTING + DIALOG)):
        assert supervisor.send_slash_to_self("exit") == 1


def test_an_unreadable_screen_says_it_does_not_know_and_does_not_wait(typed, capsys):
    sleeps = []
    with patch.object(supervisor.time, "sleep", sleeps.append), \
         patch.object(supervisor, "capture_pane", return_value=None):
        assert supervisor.send_slash_to_self("exit") == 0
    assert "whether the client exited is unknown" in capsys.readouterr().err
    assert sleeps == []


def test_other_commands_are_not_watched(typed):
    with patch.object(supervisor, "capture_pane", side_effect=AssertionError("read the screen")) as cap:
        assert supervisor.send_slash_to_self("compact") == 0
    cap.assert_not_called()


def test_quit_is_watched_like_exit(typed):
    with patch.object(supervisor, "capture_pane", side_effect=screens(CLEAN, DIALOG)):
        assert supervisor.send_slash_to_self("quit") == 1
