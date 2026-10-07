"""Only the monitor a pid file names may remove it.

A transcript monitor removed the pid file whenever it exited, whether or not the
file named it. Where a second monitor was running (two agents sharing one
account share the file), a duplicate's exit erased the record of the monitor
meant to stay, the next session start saw no monitor and forked another, and
monitors accumulated, each recording every compaction boundary again.
"""

import os

import pytest

from macf.transcript_monitor import daemon
from macf.utils import paths


@pytest.fixture
def no_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(paths, "_TMP_ROOT", str(tmp_path))
    return tmp_path / f"macf-{os.getuid()}"


def test_an_exiting_monitor_leaves_another_monitors_pid_file(no_xdg, capsys):
    daemon.write_pid_file(5555)  # the monitor that is meant to stay

    daemon.remove_pid_file(4242)  # a duplicate exits

    assert daemon.read_pid_file() == 5555
    assert "5555" in capsys.readouterr().err


def test_a_monitor_removes_its_own_pid_file(no_xdg):
    daemon.write_pid_file(4242)

    daemon.remove_pid_file(4242)

    assert not daemon.get_pid_file_path().exists()


def test_a_stale_check_leaves_a_file_rewritten_since_it_read_it(no_xdg, monkeypatch):
    """The liveness check reads a dead pid; before it removes the file, another
    session start records a new monitor. The new record must survive."""
    daemon.write_pid_file(4242)

    def dead_then_replaced(pid, sig):
        if pid == 4242:
            daemon.write_pid_file(5555)
            raise ProcessLookupError(pid)

    monkeypatch.setattr(daemon.os, "kill", dead_then_replaced)

    assert daemon.is_running() is False
    assert daemon.read_pid_file() == 5555
