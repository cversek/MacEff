"""Per-session directories live under a root a test run can move, and by default under this user's own.

#780: the default was a bare ``/tmp/macf``. ``/tmp`` is shared by every account on a host or in a
container, so the first account to create it owned it, and every other agent's session folders failed.
"""
import os
from pathlib import Path

import pytest

from macf.hooks.hook_logging import log_hook_event
from macf.utils import paths
from macf.utils.paths import get_session_dir, session_root


def test_session_root_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("MACF_SESSION_ROOT", str(tmp_path))
    assert session_root() == tmp_path


def test_the_default_root_is_inside_the_users_runtime_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("MACF_SESSION_ROOT", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert session_root() == tmp_path / "sessions"


def test_without_a_runtime_directory_the_default_is_the_uid_qualified_one(monkeypatch, tmp_path):
    monkeypatch.delenv("MACF_SESSION_ROOT", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(paths, "_TMP_ROOT", str(tmp_path))
    root = session_root()
    assert root == tmp_path / f"macf-{os.getuid()}" / "sessions"
    assert (tmp_path / f"macf-{os.getuid()}").stat().st_mode & 0o077 == 0


def test_a_fallback_directory_another_account_owns_is_refused_not_used(monkeypatch, tmp_path, capsys):
    """The directory the first account made is not this account's. Writing session folders into it
    would put them where another account could read or replace them, so none are made."""
    monkeypatch.delenv("MACF_SESSION_ROOT", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(paths, "_TMP_ROOT", str(tmp_path))
    (tmp_path / "macf-4242").mkdir(mode=0o700)
    monkeypatch.setattr(os, "getuid", lambda: 4242)       # a different account than the one that made it
    assert get_session_dir(session_id="s1", agent_id="a") is None
    assert "no private directory for session folders" in capsys.readouterr().err
    assert not list(tmp_path.glob("macf-4242/**/s1"))


def test_a_session_folder_is_made_under_the_default_root(monkeypatch, tmp_path):
    monkeypatch.delenv("MACF_SESSION_ROOT", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    made = get_session_dir(session_id="s1", agent_id="a", subdir="hooks")
    assert made == tmp_path / "sessions" / "a" / "s1" / "hooks" and made.is_dir()


def test_a_tests_hook_log_stays_out_of_the_live_session(monkeypatch, isolated_session_root):
    """A hook error logged by a test, with a live session's id in the environment, lands
    under the test run's root, not in that session's hook log under the user's own root."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "live-session-probe")
    log_hook_event({"hook_name": "probe", "event_type": "ERROR", "error": "a test's error"})

    assert list(isolated_session_root.glob("*/live-session-probe/hooks/hook_events.log"))
    live_root = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/macf-{os.getuid()}") / "sessions"
    assert not list(live_root.glob("*/live-session-probe"))
