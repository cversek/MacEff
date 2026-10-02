"""The transcript monitor's pid file is per user, and another user's pid is named, not read as dead.

In a container with several agent accounts and XDG_RUNTIME_DIR unset, the pid
file fell back to a bare /tmp, so every account shared one file. The first
account to write it owned it. For every other account, the liveness check read
that pid, os.kill raised PermissionError, the broad OSError handler read that
as "not running", and each session start forked another monitor (#490).

The other daemon tests set XDG_RUNTIME_DIR, so none of them ran the fallback.
"""

import os

import pytest

from macf.transcript_monitor import daemon
from macf.utils import paths


@pytest.fixture
def no_xdg(monkeypatch, tmp_path):
    """No XDG_RUNTIME_DIR, and the per-user fallback rooted in a temporary dir."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(paths, "_TMP_ROOT", str(tmp_path))
    return tmp_path / f"macf-{os.getuid()}"


# ------------------------------------------------------------ where the files live

def test_without_xdg_the_pid_and_log_files_are_in_this_users_directory(no_xdg):
    assert daemon.get_pid_file_path() == no_xdg / daemon.PID_FILE_NAME
    assert daemon.get_log_file_path() == no_xdg / daemon.LOG_FILE_NAME


def test_without_xdg_neither_file_is_in_a_shared_directory(no_xdg):
    for path in (daemon.get_pid_file_path(), daemon.get_log_file_path()):
        assert path.parent.name == f"macf-{os.getuid()}", path
        assert path.parent.stat().st_mode & 0o077 == 0, path


def test_with_xdg_the_files_follow_it(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))
    assert daemon.get_pid_file_path() == tmp_path / "xdg" / daemon.PID_FILE_NAME


# ------------------------------------------------------------ another user's pid

def _record_root_pid(no_xdg):
    """Record pid 1, which belongs to root: a real pid this user cannot signal."""
    daemon.write_pid_file(1)
    return daemon.get_pid_file_path()


needs_non_root = pytest.mark.skipif(
    os.geteuid() == 0, reason="root may signal pid 1, so no PermissionError arises"
)


@needs_non_root
def test_another_users_pid_is_reported_by_name_not_as_silence(no_xdg, capsys):
    pid_file = _record_root_pid(no_xdg)
    assert daemon.is_running() is False
    err = capsys.readouterr().err
    assert "belongs to another user" in err
    assert "pid 1 " in err
    assert not pid_file.exists()


@needs_non_root
def test_stop_does_not_claim_to_have_stopped_another_users_process(no_xdg, capsys):
    pid_file = _record_root_pid(no_xdg)
    assert daemon.stop_daemon() == 0
    out = capsys.readouterr()
    assert "belongs to another user" in out.err
    assert "Nothing was signaled" in out.err
    assert "stopped" not in out.out
    assert not pid_file.exists()


def test_a_dead_pid_is_still_not_running_and_quiet(no_xdg, capsys, monkeypatch):
    daemon.write_pid_file(4242)

    def dead(pid, sig):
        raise ProcessLookupError(pid)

    monkeypatch.setattr(daemon.os, "kill", dead)
    assert daemon.is_running() is False
    assert "another user" not in capsys.readouterr().err
    assert not daemon.get_pid_file_path().exists()
