"""Tests for _unprotect_for_creation permission symmetry.

A create must leave the store dir's mode exactly as it found it -- including
when the create body raises. The old behavior force-protected to 555 on every
exit, which hijacked deliberately-writable home stores and stranded them
read-only after failed creates (observed twice on a live store, 2026-07-20).
"""
import os
import stat

import pytest

from macf.task.create import _unprotect_for_creation


def _mode(p):
    return stat.S_IMODE(p.stat().st_mode)


@pytest.fixture
def store(tmp_path):
    d = tmp_path / "tasks"
    d.mkdir()
    return d


def test_protected_dir_restored_after_success(store):
    os.chmod(store, 0o555)
    with _unprotect_for_creation(store):
        assert _mode(store) == 0o755  # writable inside the context
    assert _mode(store) == 0o555


def test_protected_dir_restored_after_failure(store):
    os.chmod(store, 0o555)
    with pytest.raises(RuntimeError):
        with _unprotect_for_creation(store):
            raise RuntimeError("mid-create failure")
    assert _mode(store) == 0o555


def test_writable_dir_stays_writable_after_success(store):
    os.chmod(store, 0o755)
    with _unprotect_for_creation(store):
        pass
    assert _mode(store) == 0o755


def test_writable_dir_stays_writable_after_failure(store):
    """The observed bug: a failed create stranded a 755 store at 555."""
    os.chmod(store, 0o755)
    with pytest.raises(RuntimeError):
        with _unprotect_for_creation(store):
            raise RuntimeError("mid-create failure")
    assert _mode(store) == 0o755


def test_new_dir_is_born_protected(tmp_path):
    d = tmp_path / "fresh_tasks"
    with _unprotect_for_creation(d):
        d.mkdir()
    assert _mode(d) == 0o555
