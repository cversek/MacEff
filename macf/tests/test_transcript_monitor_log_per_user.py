"""The transcript monitors' log is per user, never in a shared directory.

In a container with several agent accounts and XDG_RUNTIME_DIR unset, the
monitor's files fell back to a bare /tmp, so every account shared them (#490).
The pid file is gone since #529, which reads the process table instead; the
log stays, and stays out of a shared directory.

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


def test_without_xdg_the_log_is_in_this_users_directory(no_xdg):
    assert daemon.get_log_file_path() == no_xdg / daemon.LOG_FILE_NAME


def test_without_xdg_the_log_is_not_in_a_shared_directory(no_xdg):
    path = daemon.get_log_file_path()
    assert path.parent.name == f"macf-{os.getuid()}", path
    assert path.parent.stat().st_mode & 0o077 == 0, path


def test_the_supervisors_0755_directory_holds_the_log(no_xdg):
    # Real hosts already have this directory, made 0755 by the supervisor as
    # the parent of its registry (#494). The monitor must use it, not refuse.
    (no_xdg / "auto-restart").mkdir(parents=True, mode=0o700)
    no_xdg.chmod(0o755)
    daemon.get_log_file_path().write_text("a line\n")
    assert daemon.get_log_file_path().parent == no_xdg
    assert no_xdg.stat().st_mode & 0o777 == 0o700


def test_with_xdg_the_log_follows_it(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))
    assert daemon.get_log_file_path() == tmp_path / "xdg" / daemon.LOG_FILE_NAME
