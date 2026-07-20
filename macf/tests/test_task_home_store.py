"""Tests for the project-scoped home task store backend.

Covers store resolution (config mode, env overrides, MACF_TASKS_DIR isolation
precedence), the hide/unhide no-op outside CC's tree, and the reconcile guard.
"""

import json
import pytest
from pathlib import Path

from macf.task.reader import (
    TaskReader,
    hide_task_file,
    unhide_task_file,
    _is_cc_session_dir,
)
from macf.task.reconcile import reconcile
from macf.utils.paths import find_agent_home


@pytest.fixture
def home_agent(tmp_path, monkeypatch):
    """An isolated agent home with task_store.mode=home configured."""
    monkeypatch.delenv("MACF_TASKS_DIR", raising=False)
    monkeypatch.delenv("MACF_TASK_STORE_DIR", raising=False)
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    find_agent_home.cache_clear()
    maceff = tmp_path / ".maceff"
    maceff.mkdir()
    (maceff / "config.json").write_text(json.dumps(
        {"task_store": {"mode": "home", "path": "agent/public/tasks"}}))
    yield tmp_path
    find_agent_home.cache_clear()


class TestHomeStoreResolution:
    def test_home_mode_resolves_to_agent_home_store(self, home_agent):
        reader = TaskReader()
        assert reader.session_uuid == TaskReader.HOME_STORE_UUID
        assert reader.session_path == home_agent / "agent" / "public" / "tasks"

    def test_macf_tasks_dir_forces_legacy(self, home_agent, tmp_path, monkeypatch):
        # The legacy isolation override must win over the home config, or an
        # isolated env leaks into the real home store (the bug the suite caught).
        iso = tmp_path / "iso_tasks"
        iso.mkdir()
        monkeypatch.setenv("MACF_TASKS_DIR", str(iso))
        assert TaskReader._resolve_home_store() is None

    def test_task_store_dir_env_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MACF_TASKS_DIR", raising=False)
        store = tmp_path / "explicit_store"
        monkeypatch.setenv("MACF_TASK_STORE_DIR", str(store))
        assert TaskReader._resolve_home_store() == store

    def test_unconfigured_agent_stays_legacy(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MACF_TASKS_DIR", raising=False)
        monkeypatch.delenv("MACF_TASK_STORE_DIR", raising=False)
        monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))  # no config.json
        find_agent_home.cache_clear()
        assert TaskReader._resolve_home_store() is None
        find_agent_home.cache_clear()


class TestCcSessionDirDetection:
    def test_accepts_str_and_path(self):
        # Regression: hide/unhide pass a str; _is_cc_session_dir must not crash.
        cc = Path.home() / ".claude" / "tasks" / "some-uuid"
        assert _is_cc_session_dir(str(cc)) is True
        assert _is_cc_session_dir(cc) is True

    def test_home_store_is_not_a_cc_dir(self, tmp_path):
        assert _is_cc_session_dir(tmp_path / "agent" / "public" / "tasks") is False


class TestHideIsNoOpOutsideCc:
    def test_hide_and_unhide_leave_home_store_visible(self, tmp_path):
        store = tmp_path / "tasks"
        store.mkdir()
        task = store / "5.json"
        task.write_text("{}")
        assert hide_task_file(store, "5") is True
        assert task.exists()  # not renamed to .5.json
        assert not (store / ".5.json").exists()
        assert unhide_task_file(store, "5") is True
        assert task.exists()


class TestReconcileGuard:
    def test_raises_without_home_store(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MACF_TASKS_DIR", str(tmp_path))  # forces legacy -> no home
        with pytest.raises(RuntimeError):
            reconcile(apply=False)


class TestReconcileOverwritesReadOnly:
    def test_reapply_over_readonly_dest(self, tmp_path, monkeypatch):
        # Task files copied from CC's protected dirs are read-only; a second
        # reconcile must still overwrite them instead of failing midway.
        import os
        import macf.task.reconcile as rec
        src = tmp_path / "src"
        src.mkdir()
        (src / "5.json").write_text('{"id": "5", "status": "completed"}')
        dest = tmp_path / "dest"
        monkeypatch.setenv("MACF_TASK_STORE_DIR", str(dest))
        monkeypatch.setattr(rec, "_project_session_dirs", lambda: [src])

        reconcile(apply=True)
        target = dest / "5.json"
        assert target.exists()
        os.chmod(target, 0o444)  # simulate a protected/read-only dest file

        # Must not raise despite the read-only target.
        report = reconcile(apply=True)
        assert report["applied"] is True
        assert target.read_text().strip().startswith("{")


class TestLoopWatcherFlatStore:
    """task tree --loop must detect changes in a flat store dir (#144)."""

    def test_mtime_none_and_missing_dir(self, tmp_path):
        from macf.cli import get_tasks_mtime
        assert get_tasks_mtime(None) == 0.0
        assert get_tasks_mtime(tmp_path / "nope") == 0.0

    def test_mtime_sees_flat_store_files(self, tmp_path):
        import os
        from macf.cli import get_tasks_mtime
        store = tmp_path / "tasks"
        store.mkdir()
        task = store / "7.json"
        task.write_text("{}")
        first = get_tasks_mtime(store)
        assert first > 0.0
        # A later write must move the watermark (flat glob, no session subdirs)
        os.utime(task, (first + 10, first + 10))
        assert get_tasks_mtime(store) > first

    def test_mtime_sees_hidden_files_and_dir_changes(self, tmp_path):
        import os
        from macf.cli import get_tasks_mtime
        store = tmp_path / "tasks"
        store.mkdir()
        hidden = store / ".8.json"
        hidden.write_text("{}")
        base = get_tasks_mtime(store)
        assert base > 0.0
        os.utime(hidden, (base + 10, base + 10))
        assert get_tasks_mtime(store) > base
        # Deleting a file bumps the dir mtime -> watermark changes even
        # though no surviving file mtime moved.
        before = get_tasks_mtime(store)
        hidden.unlink()
        os.utime(store, (before + 20, before + 20))
        assert get_tasks_mtime(store) != before

    def test_loop_watches_session_path_not_legacy_root(self, home_agent):
        # The watcher dir must be the resolved store, not ~/.claude/tasks root.
        reader = TaskReader()
        assert reader.session_uuid == TaskReader.HOME_STORE_UUID
        assert reader.session_path == home_agent / "agent" / "public" / "tasks"
