"""An injected /exit refuses while the session has scheduled jobs (cversek/MacEff#854).

A scheduled job makes the client answer /exit with "Background work is running", and an
unattended restart sat on that dialog until a person answered it, while inject reported the
keystrokes as sent. The jobs are read from the session's transcript: the client keeps them in
memory only.
"""
import json
from unittest.mock import patch

from macf import supervisor
from macf.utils.scheduled_jobs import RECURRING_LIFETIME_S, Job, live_jobs

NOW = 2_000_000_000.0


def _iso(t):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def _created(job_id, at, recurring=True, due=None):
    return {"type": "user", "timestamp": _iso(at), "toolUseResult": {
        "id": job_id, "humanSchedule": "Every hour at :13", "recurring": recurring, "durable": False,
        "nextFireAt": (due if due is not None else at + 3600) * 1000}}


def _cancelled(job_id, at):
    return {"type": "user", "timestamp": _iso(at), "toolUseResult": {"id": job_id}}


def _transcript(tmp_path, entries):
    path = tmp_path / "session.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return path


def test_a_job_scheduled_and_not_cancelled_is_live(tmp_path):
    path = _transcript(tmp_path, [_created("a1", NOW - 600), _created("b2", NOW - 500), _cancelled("b2", NOW - 100)])
    assert [j.id for j in live_jobs(path, now=NOW)] == ["a1"]


def test_jobs_from_before_the_client_started_or_expired_are_gone(tmp_path):
    path = _transcript(tmp_path, [_created("old", NOW - RECURRING_LIFETIME_S - 60),
                                  _created("before", NOW - 3000), _created("after", NOW - 60)])
    assert [j.id for j in live_jobs(path, since=NOW - 1000, now=NOW)] == ["after"]
    assert [j.id for j in live_jobs(path, now=NOW)] == ["before", "after"]


def test_a_one_shot_job_that_has_fired_is_gone_and_one_still_due_is_live(tmp_path):
    path = _transcript(tmp_path, [_created("fired", NOW - 600, recurring=False, due=NOW - 300),
                                  _created("pending", NOW - 600, recurring=False, due=NOW + 300)])
    assert [j.id for j in live_jobs(path, now=NOW)] == ["pending"]


def test_exit_refuses_and_names_the_jobs(monkeypatch, capsys):
    monkeypatch.setattr(supervisor, "_scheduled_jobs",
                        lambda: [Job("6c5de042", "Every hour at :13", True, NOW)])
    with patch.object(supervisor, "own_pane_target", return_value="seat"), \
         patch.object(supervisor, "_draft_in_box", return_value=""), \
         patch.object(supervisor, "_unsent_feedback_drafts", return_value=[]), \
         patch.object(supervisor, "send_keys", return_value=0) as send:
        assert supervisor.send_slash_to_self("exit") == 1
    send.assert_not_called()
    err = capsys.readouterr().err
    assert "6c5de042 (Every hour at :13)" in err and "Background work is running" in err


def test_exit_goes_on_without_jobs(monkeypatch):
    with patch.object(supervisor, "own_pane_target", return_value="seat"), \
         patch.object(supervisor, "_draft_in_box", return_value=""), \
         patch.object(supervisor, "_unsent_feedback_drafts", return_value=[]), \
         patch.object(supervisor, "send_keys", return_value=0) as send, \
         patch("macf.stop_bypass.arm"):
        assert supervisor.send_slash_to_self("exit") == 0
    send.assert_called_once()
