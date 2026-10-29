"""A transcript monitor started by the code before this one is found, reported and stopped.

That code forked the monitor from the session-start hook without exec and wrote
its pid to a file, so its command line is the hook's and ``find_monitors`` cannot
see it. Left alone it serves beside the new monitor and never exits. These tests
start a real process with such a command line and point the old pid file at it.
``find_monitors`` is replaced so that no test can reach a real monitor.
"""
import os
import signal
import subprocess
import sys
import time

import pytest

from macf.transcript_monitor import daemon

HOOK_SCRIPT = "/home/agent/.claude/hooks/session_start.py"


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "user_runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(daemon, "find_monitors", lambda: [])
    return tmp_path


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@pytest.fixture
def spawn():
    """Start a sleeper detached, as the old monitor was: its parent exits, so init reaps it."""
    pids = []

    def run(*extra):
        argv = [sys.executable, "-c", "import time; time.sleep(60)", *extra]
        out = subprocess.run(["sh", "-c", 'exec "$@" >/dev/null 2>&1 & echo $!', "sh", *argv],
                             capture_output=True, text=True, check=True).stdout
        pids.append(int(out.strip()))
        return pids[-1]

    yield run
    for pid in pids:
        if alive(pid):
            os.kill(pid, signal.SIGTERM)


def point_at(runtime, pid):
    (runtime / "macf_transcript_monitor.pid").write_text(f"{pid}\n")


def any_age(monkeypatch):
    # Without the module's age constant this does nothing, and the test then
    # fails on its assertion rather than passing.
    monkeypatch.setattr(daemon, "LEGACY_MIN_AGE_S", 0, raising=False)


def test_stop_stops_an_old_form_monitor_and_removes_its_pid_file(runtime, spawn, monkeypatch):
    any_age(monkeypatch)
    pid = spawn(HOOK_SCRIPT)
    point_at(runtime, pid)
    daemon.stop_daemon()
    for _ in range(12):
        if not alive(pid):
            break
        time.sleep(0.5)
    assert not alive(pid)
    assert not (runtime / "macf_transcript_monitor.pid").exists()


def test_status_reports_an_old_form_monitor_without_stopping_it(runtime, spawn, monkeypatch, capsys):
    any_age(monkeypatch)
    pid = spawn(HOOK_SCRIPT)
    point_at(runtime, pid)
    daemon.daemon_status()
    assert f"PID {pid}" in capsys.readouterr().out
    assert alive(pid)


def test_a_pid_whose_command_is_not_the_hook_is_left_alone(runtime, spawn, monkeypatch):
    any_age(monkeypatch)
    pid = spawn()
    point_at(runtime, pid)
    daemon.stop_daemon()
    assert alive(pid)


def test_a_process_younger_than_any_monitor_is_left_alone(runtime, spawn):
    pid = spawn(HOOK_SCRIPT)
    point_at(runtime, pid)
    daemon.stop_daemon()
    assert alive(pid)


@pytest.mark.parametrize("text, seconds", [
    ("05:07", 307), ("1:02:03", 3723), ("2-01:00:00", 176400), ("", None), ("x:y", None),
])
def test_elapsed_time_is_read_in_every_form_ps_prints(text, seconds):
    assert daemon._parse_etime(text) == seconds
