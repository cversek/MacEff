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


class TestSprintPlayTimeNoSelfCollision:
    """create_sprint/create_play_time reserve a provisional stub then finalize
    at the same id; the PR #134 collision guard must not block that finalize
    (BUG #157). Regression: both must create without raising and the finalized
    file must carry the real subject, not the '(provisional)' stub.
    """

    def test_create_sprint_scoped_finalizes(self, home_agent):
        from macf.task.create import create_task, create_sprint
        a = create_task(title="target A", plan="x")
        b = create_task(title="target B", plan="x")
        res = create_sprint(
            "renewal-style sprint",
            scoped_task_ids=[a.task_id, b.task_id],
            no_auto_start=True,
            agent_root=home_agent,
        )
        sid = res["task_id"]
        f = home_agent / "agent" / "public" / "tasks" / f"{sid}.json"
        assert f.exists()
        data = json.loads(f.read_text())
        assert "provisional" not in data["subject"]
        assert "🏃 SPRINT:" in data["subject"]

    def test_create_play_time_children_finalizes(self, home_agent):
        from macf.task.create import create_play_time
        res = create_play_time(
            "play block",
            timer_minutes=30,
            children_titles=["c1", "c2"],
            no_auto_start=True,
            agent_root=home_agent,
        )
        pid = res["task_id"]
        f = home_agent / "agent" / "public" / "tasks" / f"{pid}.json"
        assert f.exists()
        data = json.loads(f.read_text())
        assert "provisional" not in data["subject"]


class TestStoreInit:
    """Provisioning builds the store; it is not opted into after the fact.

    Nothing in agent init, config init, or any downstream provisioning script
    created the directory or wrote the config key, so every provisioned agent
    silently ran on the session-scoped legacy store -- the one CC deletes from
    and a fork duplicates.
    """

    def _run(self, home):
        import argparse
        from macf.cli import cmd_task_store_init
        return cmd_task_store_init(argparse.Namespace(home=str(home)))

    def test_creates_store_and_sets_mode_on_a_bare_home(self, tmp_path):
        assert self._run(tmp_path) == 0
        assert (tmp_path / "agent" / "public" / "tasks").is_dir()
        cfg = json.loads((tmp_path / ".maceff" / "config.json").read_text())
        assert cfg["task_store"]["mode"] == "home"

    def test_preserves_existing_config_keys(self, tmp_path):
        """A provisioned home already holds identity and hook settings. Pointing
        it at a new store must not be a rewrite."""
        maceff = tmp_path / ".maceff"
        maceff.mkdir()
        (maceff / "config.json").write_text(json.dumps(
            {"agent_identity": {"moniker": "Keep Me"}, "hooks": {"capture_output": True}}))
        assert self._run(tmp_path) == 0
        cfg = json.loads((maceff / "config.json").read_text())
        assert cfg["agent_identity"]["moniker"] == "Keep Me"
        assert cfg["hooks"]["capture_output"] is True
        assert cfg["task_store"]["mode"] == "home"

    def test_idempotent(self, tmp_path):
        assert self._run(tmp_path) == 0
        assert self._run(tmp_path) == 0
        cfg = json.loads((tmp_path / ".maceff" / "config.json").read_text())
        assert cfg["task_store"]["mode"] == "home"

    def test_refuses_to_clobber_an_unreadable_config(self, tmp_path):
        """CONTROL on the read-modify-write: corrupt config must abort, not be
        silently replaced with a fresh one that drops the agent's identity."""
        maceff = tmp_path / ".maceff"
        maceff.mkdir()
        (maceff / "config.json").write_text("{not json")
        assert self._run(tmp_path) == 1
        assert (maceff / "config.json").read_text() == "{not json"


class TestMigrateEveryLegacyDirectory:
    """Migrating only the live session leaves a directory nothing will mention.

    An agent that has been continued, rewound or forked has several session
    dirs. The old implementation resolved exactly one -- the current session --
    and reported success, which is a partial result shaped like a complete one.
    """

    @pytest.fixture
    def legacy_agent(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MACF_TASKS_DIR", raising=False)
        monkeypatch.delenv("MACF_TASK_STORE_DIR", raising=False)
        monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        find_agent_home.cache_clear()
        (tmp_path / ".maceff").mkdir()
        tasks = tmp_path / ".claude" / "tasks"
        (tasks / "aaaa-1111").mkdir(parents=True)
        (tasks / "bbbb-2222").mkdir(parents=True)
        yield tmp_path
        find_agent_home.cache_clear()

    def _run(self, dry_run=False, force=False):
        import argparse
        from macf.cli import cmd_task_migrate_store
        return cmd_task_migrate_store(
            argparse.Namespace(dry_run=dry_run, force=force))

    def test_migrates_tasks_from_every_directory(self, legacy_agent):
        t = legacy_agent / ".claude" / "tasks"
        (t / "aaaa-1111" / "1.json").write_text('{"id": "1"}')
        (t / "bbbb-2222" / "2.json").write_text('{"id": "2"}')
        assert self._run() == 0
        store = legacy_agent / "agent" / "public" / "tasks"
        # The second assertion is the one that matters: migrating only the
        # "current" directory satisfies the first and fails this.
        assert (store / "1.json").exists()
        assert (store / "2.json").exists(), "a whole legacy directory was stranded"

    def test_normalises_the_hidden_dot_prefix(self, legacy_agent):
        """The prefix exists only to hide files from CC's scanner, which never
        looks at the home store. Carrying it in leaves one directory with two
        conventions, and shell globs skip the dotted half."""
        t = legacy_agent / ".claude" / "tasks"
        (t / "aaaa-1111" / ".7.json").write_text('{"id": "7"}')
        assert self._run() == 0
        store = legacy_agent / "agent" / "public" / "tasks"
        assert (store / "7.json").exists()
        assert not (store / ".7.json").exists()

    def test_identical_copies_across_directories_are_not_a_conflict(self, legacy_agent):
        t = legacy_agent / ".claude" / "tasks"
        (t / "aaaa-1111" / "5.json").write_text('{"id": "5"}')
        (t / "bbbb-2222" / "5.json").write_text('{"id": "5"}')
        assert self._run() == 0
        assert (legacy_agent / "agent" / "public" / "tasks" / "5.json").exists()

    def test_divergent_copies_refuse_rather_than_choose(self, legacy_agent):
        """A fork copies the store and both sides move on. Choosing silently
        discards whichever copy lost a coin toss."""
        t = legacy_agent / ".claude" / "tasks"
        (t / "aaaa-1111" / "5.json").write_text('{"id": "5", "v": "old"}')
        (t / "bbbb-2222" / "5.json").write_text('{"id": "5", "v": "new"}')
        assert self._run() == 1
        assert not (legacy_agent / "agent" / "public" / "tasks" / "5.json").exists()
        cfg = json.loads((legacy_agent / ".maceff" / "config.json").read_text() or "{}") \
            if (legacy_agent / ".maceff" / "config.json").exists() else {}
        assert (cfg.get("task_store") or {}).get("mode") != "home", \
            "config must not flip when the migration refused"

    def test_force_takes_the_newest_divergent_copy(self, legacy_agent):
        import os, time
        t = legacy_agent / ".claude" / "tasks"
        old = t / "aaaa-1111" / "5.json"
        new = t / "bbbb-2222" / "5.json"
        old.write_text('{"id": "5", "v": "old"}')
        new.write_text('{"id": "5", "v": "new"}')
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))
        assert self._run(force=True) == 0
        got = (legacy_agent / "agent" / "public" / "tasks" / "5.json").read_text()
        assert '"new"' in got

    def test_dry_run_touches_nothing(self, legacy_agent):
        t = legacy_agent / ".claude" / "tasks"
        (t / "aaaa-1111" / "1.json").write_text('{"id": "1"}')
        assert self._run(dry_run=True) == 0
        assert not (legacy_agent / "agent" / "public" / "tasks" / "1.json").exists()

    def test_empty_legacy_refuses(self, legacy_agent):
        assert self._run() == 1
