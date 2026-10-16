"""In AUTO_MODE an agent resumes after every compaction, whatever asked for it.

A compaction opens no turn, and nothing a SessionStart hook returns can open one. Only
``inject compact`` started a follower, so a compaction the operator typed, or one the
client ran itself, left an AUTO_MODE agent at an empty box until something woke it: a
seat sat idle after its compaction until the operator noticed (Oct 16). The hook now
starts the follower itself in AUTO_MODE, and a lock keeps one follower per compaction
when ``inject compact`` started one too.
"""
import json
from unittest.mock import patch

from macf import compact_followup as cf
from test_session_start_identity import HOOK, quiet_hook  # noqa: F401  (fixture)


def _compact():
    from macf.hooks.handle_session_start import run
    return run(json.dumps({"source": "compact", "session_id": "sess-identity"}))


def test_a_compaction_in_auto_mode_starts_the_resume_follower(quiet_hook):
    with patch(f"{HOOK}.detect_auto_mode", return_value=(True, "event")), \
         patch("macf.supervisor.start_compaction_resume", return_value=True) as start, \
         patch("time.time", return_value=5000.0):
        out = _compact()
    start.assert_called_once_with(5000.0)
    assert out["continue"] is True


def test_no_follower_outside_auto_mode(quiet_hook):
    """In MANUAL_MODE the agent waits for the operator after a compaction, by design."""
    with patch("macf.supervisor.start_compaction_resume") as start:
        _compact()
    assert not start.called


def test_a_follower_that_cannot_start_does_not_stop_recovery(quiet_hook):
    with patch(f"{HOOK}.detect_auto_mode", return_value=(True, "event")), \
         patch("macf.supervisor.start_compaction_resume", side_effect=OSError("no fork")):
        out = _compact()
    assert "RECOVERY BODY" in out["hookSpecificOutput"]["additionalContext"]


def test_the_resume_follower_types_into_our_own_pane_quietly():
    """A hook's stdout is its reply: the starter must print nothing there."""
    from macf import supervisor
    with patch.object(supervisor, "own_pane_target", return_value="pane:%0"), \
         patch.object(supervisor, "_start_compact_followup", return_value=True) as start:
        assert supervisor.start_compaction_resume(5000.0) is True
    start.assert_called_once_with("pane:%0", cf.RESUME_TEXT, since=5000.0, quiet=True)


def test_no_follower_without_a_pane_of_our_own():
    from macf import supervisor
    with patch.object(supervisor, "own_pane_target", return_value=None), \
         patch.object(supervisor, "_start_compact_followup") as start:
        assert supervisor.start_compaction_resume(5000.0) is False
    assert not start.called


def test_the_starter_prints_nothing_to_stdout_when_quiet(capsys, tmp_path):
    from macf import supervisor
    with patch("subprocess.Popen"), \
         patch("macf.transcript_monitor.daemon.get_log_file_path", return_value=tmp_path / "log"):
        assert supervisor._start_compact_followup("pane:%0", "text", since=1.0, quiet=True)
    assert capsys.readouterr().out == ""


def test_a_second_follower_steps_aside_while_one_waits(tmp_path):
    """Tonight two followers each typed the prompt into one box (Oct 16)."""
    lock = tmp_path / cf.LOCK_NAME
    first = cf._take_lock(lock)
    assert first is not None
    assert cf._take_lock(lock) is None
    first.close()
    again = cf._take_lock(lock)
    assert again is not None
    again.close()


def test_main_skips_without_following_when_the_lock_is_held(capsys):
    with patch.object(cf, "_take_lock", return_value=None), \
         patch.object(cf, "follow") as follow, \
         patch("macf.agent_events_log.append_event", return_value=True) as append:
        assert cf.main(["pane:%0", "1.0"]) == 0
    assert not follow.called
    append.assert_called_once_with("compact_followup", {
        "target": "pane:%0", "outcome": "skipped: another follower is already waiting"})
