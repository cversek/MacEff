"""Sessions that Claude Code's own background daemon hosts, as the readout sees them.

MIS-0002-R66 (pd_MUST_adopt_harness_supervisor) starts with seeing those sessions.
Measured on 2.1.296: a daemon-hosted worker runs in a pre-started spare process whose
argv is generic, its sidecar says ``kind: "bg"``, and its launch flags (``--channels``
among them) exist only in ``~/.claude/jobs/<short>/state.json`` as ``respawnFlags``.
"""
import json
import os

import pytest

from macf.notify import session


@pytest.fixture
def claude_home(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "sessions_dir", lambda: tmp_path / "sessions")
    monkeypatch.setattr(session, "jobs_dir", lambda: tmp_path / "jobs")
    (tmp_path / "sessions").mkdir()
    (tmp_path / "jobs").mkdir()
    return tmp_path


def _sidecar(home, pid, kind, session_id):
    (home / "sessions" / f"{pid}.json").write_text(json.dumps(
        {"pid": pid, "sessionId": session_id, "kind": kind, "status": "idle", "cwd": "/tmp/x"}))


def _job(home, short, flags):
    (home / "jobs" / short).mkdir()
    (home / "jobs" / short / "state.json").write_text(json.dumps({"respawnFlags": flags}))


def test_background_session_is_listed_with_its_channels(claude_home):
    _sidecar(claude_home, os.getpid(), "bg", "8d48008b-2c36-4ca6-9b41-2e173fc25a92")
    _job(claude_home, "8d48008b", ["--channels", "plugin:fakechat@claude-plugins-official", "--setting-sources", "project,local"])
    hosted = session.harness_hosted_sessions()
    assert len(hosted) == 1
    assert hosted[0].channels == ["plugin:fakechat@claude-plugins-official"]


def test_channels_written_with_equals_or_several_values_are_read(claude_home):
    """MEASURED 2.1.296: ``--channels=X`` is kept as one token, and ``--channels`` takes several values."""
    _sidecar(claude_home, os.getpid(), "bg", "32149023-da95-480f-bb4a-866d6bc083a0")
    _job(claude_home, "32149023", ["--settings", "/tmp/s.json", "--channels=plugin:fakechat@claude-plugins-official"])
    assert session.harness_hosted_sessions()[0].channels == ["plugin:fakechat@claude-plugins-official"]
    _job_flags = ["--channels", "plugin:a@x", "plugin:b@x", "--settings", "/tmp/s.json"]
    (claude_home / "jobs" / "32149023" / "state.json").write_text(json.dumps({"respawnFlags": _job_flags}))
    assert session.harness_hosted_sessions()[0].channels == ["plugin:a@x", "plugin:b@x"]


def test_interactive_sessions_are_not_hosted_by_the_daemon(claude_home):
    _sidecar(claude_home, os.getpid(), "interactive", "89f47c46-71a2-4d9b-873a-72f4c44f3788")
    assert session.harness_hosted_sessions() == []


def test_missing_job_record_is_unknown_not_empty(claude_home):
    """No state.json means the channels are unknown, which must not read as 'none'."""
    _sidecar(claude_home, os.getpid(), "bg", "aaaaaaaa-0000-0000-0000-000000000000")
    hosted = session.harness_hosted_sessions()
    assert hosted[0].channels is None


def test_dead_worker_is_not_listed(claude_home):
    _sidecar(claude_home, 999999, "bg", "bbbbbbbb-0000-0000-0000-000000000000")
    assert session.harness_hosted_sessions() == []


def test_readout_names_the_client_daemon_for_this_process(claude_home, monkeypatch):
    """A session the client's daemon hosts is supervised, by the harness's own supervisor."""
    from macf.utils import supervision
    monkeypatch.setenv("CLAUDE_CODE_SESSION_KIND", "bg")
    d = supervision.diagnose()
    assert d["client_daemon"]["hosts_this_session"] is True
    assert "Claude Code's daemon" in supervision.format_diagnosis(d)
