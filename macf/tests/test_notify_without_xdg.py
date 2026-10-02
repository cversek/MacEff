"""The notifier without XDG_RUNTIME_DIR: where its records go, and how it finds a session.

Every other notify test sets XDG_RUNTIME_DIR, so none of them could see what
happens on macOS or in a container without one. These run with it unset.

Two defects were fixed together:
- the notifier's own records fell back to /run/user/<uid>, which exists only
  where a login manager made it, so every write failed;
- the socket lookups derived the socket's location instead of reading the path
  the client publishes, and without XDG_RUNTIME_DIR the client puts it under
  /tmp/cc-socks/ or /tmp/cc-socks-<uid>/, depending on its version, where the
  derivation never looks.
"""

import json
import os

import pytest

from macf.notify import adapter, liveness, masking, session
from macf.utils import paths


@pytest.fixture
def no_xdg(monkeypatch, tmp_path):
    """No XDG_RUNTIME_DIR, and the per-user fallback rooted in a temporary dir."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(paths, "_TMP_ROOT", str(tmp_path))
    return tmp_path / f"macf-{os.getuid()}"


# ------------------------------------------------------------ the state directory

def test_xdg_runtime_dir_is_used_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))
    assert paths.user_runtime_dir() == tmp_path / "xdg"


def test_without_it_the_fallback_is_a_private_per_user_directory(no_xdg):
    got = paths.user_runtime_dir()
    assert got == no_xdg
    assert got.is_dir()
    assert got.stat().st_mode & 0o777 == 0o700


def test_a_fallback_directory_others_can_write_is_refused(no_xdg):
    no_xdg.mkdir()
    no_xdg.chmod(0o777)
    with pytest.raises(PermissionError, match="not this user's private directory"):
        paths.user_runtime_dir()


def test_every_notify_record_lives_in_the_fallback_not_in_run_user(no_xdg):
    for path in (adapter.dedup_path(), liveness.record_path(), liveness.gaps_path(),
                 masking._runtime_dir() / masking.DECLARATION_NAME):
        assert path.parent == no_xdg, path
        assert not str(path).startswith("/run/user")


# ------------------------------------------------------------ finding the socket

def _sidecar(home, pid, **fields):
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{pid}.json").write_text(json.dumps({"sessionId": "s-1", **fields}))
    return sessions


@pytest.fixture
def home(monkeypatch, tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    # A runtime dir with no cc-socks in it, so a derived path never exists.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))
    return h


def test_find_socket_uses_the_path_the_client_published(home, tmp_path):
    published = tmp_path / "cc-socks-1000" / "4242.sock"
    published.parent.mkdir()
    published.touch()
    _sidecar(home, 4242, messagingSocketPath=str(published))
    assert session.find_socket(4242) == published


def test_find_socket_falls_back_to_the_derived_path_when_none_is_published(home, tmp_path):
    _sidecar(home, 4242)
    derived = tmp_path / "xdg" / "cc-socks" / "4242.sock"
    derived.parent.mkdir(parents=True)
    derived.touch()
    assert session.find_socket(4242) == derived


def test_a_session_is_addressable_at_its_published_path(home, tmp_path):
    pid = os.getpid()  # a live process, so its start time is readable
    published = tmp_path / "cc-socks-1000" / f"{pid}.sock"
    published.parent.mkdir()
    published.touch()
    sessions = _sidecar(home, pid, messagingSocketPath=str(published))
    (sessions / f"{pid}.key").write_text("{}")
    assert pid in session.addressable_sessions()
