"""`inject exit` says what it knows about the exit, and no more (cversek/MacEff#854, point 3).

It used to report the keystrokes as the result. A client that stopped on a dialog nobody is there to
answer was still running, and the caller believed the restart was under way. #967 refuses up front
while the session has scheduled jobs; this reads the screen after /exit is typed, for the dialog a
refusal could not foresee, and names what does confirm an exit.
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
    with patch.object(supervisor, "capture_pane", return_value=DIALOG):
        assert supervisor.send_slash_to_self("exit") == 1
    err = capsys.readouterr().err
    assert "Background work is running" in err and "has not exited" in err


def test_a_clean_screen_is_not_taken_for_an_exit(typed, capsys):
    with patch.object(supervisor, "capture_pane", return_value="> \n"):
        assert supervisor.send_slash_to_self("exit") == 0
    err = capsys.readouterr().err
    assert "not confirmed" in err and "pd_carried" in err and "pd status" in err


def test_a_dialog_that_appears_after_a_moment_is_still_seen(typed, capsys):
    screens = iter(["> \n", "> \n", DIALOG])
    with patch.object(supervisor, "capture_pane", side_effect=lambda t: next(screens)):
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
    with patch.object(supervisor, "capture_pane", return_value=DIALOG):
        assert supervisor.send_slash_to_self("quit") == 1
