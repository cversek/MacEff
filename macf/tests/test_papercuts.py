"""Small independent fixes, each with a documented trigger."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


class TestVersionShowsSourceCheckout:
    """`--version` must say which checkout is running.

    Dogfooding a feature branch, the bare dev version string was identical
    whether the code under it was main, a branch, or a dirty tree — so
    "is my fix actually loaded?" could not be answered from the tool.
    """

    def test_reports_branch_and_commit_for_a_git_checkout(self):
        from macf.cli import _editable_source_suffix
        suffix = _editable_source_suffix()
        # The test suite itself runs from a checkout, so a suffix is expected.
        assert suffix.startswith(" ("), f"no source info reported: {suffix!r}"
        assert " @ " in suffix

    def test_absent_outside_a_repo(self, tmp_path, monkeypatch):
        """A wheel install has no checkout and must print the plain version."""
        from macf import cli
        monkeypatch.setattr(cli, "__file__", str(tmp_path / "cli.py"))
        assert cli._editable_source_suffix() == ""

    def test_resolution_is_lazy(self, monkeypatch):
        """Resolving the checkout must not be charged to every invocation.

        Hooks shell out to macf_tools on every tool use; three git calls per
        invocation, for a string only --version prints, is not free.
        """
        from macf import cli
        calls = []
        monkeypatch.setattr(cli, "_editable_source_suffix",
                            lambda: calls.append(1) or "")
        cli._build_parser()
        assert calls == [], "source checkout resolved while merely building the parser"


class TestHomeStoreIsGitignored:
    """Creating the home store inside a repo must not silently stage it.

    The store accumulates one JSON file per task; left tracked, a routine
    `git add -A` stages thousands of files nobody meant to commit.
    """

    def _agent_home(self, tmp_path, track=False):
        home = tmp_path / "home"
        (home / ".maceff").mkdir(parents=True)
        store = {"mode": "home", "path": "agent/public/tasks"}
        if track:
            store["track"] = True
        (home / ".maceff" / "config.json").write_text(
            json.dumps({"task_store": store}))
        subprocess.run(["git", "init", "-q", str(home)], check=True)
        return home

    def _create_task(self, home, title, log):
        # The backend under test is selected by the config.json written above,
        # so the subprocess must not inherit a variable that selects a different
        # one. `MACF_TASKS_DIR` is set for every test by conftest's
        # `isolated_task_store`, and it forces the legacy per-session store --
        # which would leave this class asserting about a home store that was
        # never used. The isolation those variables provide is not needed here:
        # `home` is already a tmp_path.
        env = {k: v for k, v in os.environ.items()
               if k not in ("MACF_TASKS_DIR", "MACF_TASK_STORE_DIR")}
        env["MACEFF_AGENT_HOME_DIR"] = str(home)
        env["MACF_EVENTS_LOG_PATH"] = str(log)
        return subprocess.run(
            ["macf_tools", "task", "create", "task", title, "--plan", "smoke"],
            capture_output=True, text=True, env=env,
        )

    def test_store_is_ignored_after_first_task(self, tmp_path):
        home = self._agent_home(tmp_path)
        result = self._create_task(home, "first", tmp_path / "ev.jsonl")
        assert result.returncode == 0, result.stdout + result.stderr

        ignored = subprocess.run(
            ["git", "-C", str(home), "check-ignore", "-q", "agent/public/tasks"])
        assert ignored.returncode == 0, (
            f"task store is tracked:\n{(home / '.gitignore').read_text() if (home / '.gitignore').exists() else '(no .gitignore)'}"
        )

    def test_rule_is_written_once(self, tmp_path):
        home = self._agent_home(tmp_path)
        self._create_task(home, "first", tmp_path / "ev.jsonl")
        after_first = (home / ".gitignore").read_text()
        self._create_task(home, "second", tmp_path / "ev.jsonl")
        assert (home / ".gitignore").read_text() == after_first

    def test_track_opt_in_leaves_gitignore_alone(self, tmp_path):
        """Some projects genuinely want the task history versioned."""
        home = self._agent_home(tmp_path, track=True)
        result = self._create_task(home, "first", tmp_path / "ev.jsonl")
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (home / ".gitignore").exists(), "opt-out was ignored"


class TestMigrateStore:
    """Moving the legacy per-session store into the home store.

    Done by hand this is: copy every file including the dot-prefixed completed
    ones, edit the config, then hope. The ordering is the whole point — copy,
    verify, then flip — because a config flipped before verification points the
    agent at a possibly-incomplete store, and that failure reads like amnesia
    rather than like a bad migration.
    """

    def _legacy_setup(self, tmp_path, mode="legacy"):
        home = tmp_path / "home"
        (home / ".maceff").mkdir(parents=True)
        (home / ".maceff" / "config.json").write_text(json.dumps(
            {"task_store": {"mode": mode, "path": "agent/public/tasks"}}))
        subprocess.run(["git", "init", "-q", str(home)], check=True)

        session = tmp_path / "tasks" / "sess-abc"
        session.mkdir(parents=True)
        for tid in ("000", "1", "2"):
            (session / f"{tid}.json").write_text(json.dumps(
                {"id": tid, "subject": f"  #{tid} t", "status": "pending",
                 "description": "<macf_task_metadata version=\"1.0\">\n"
                                "task_type: TASK\nparent_id: null\n"
                                "</macf_task_metadata>\n"}))
        # Completed tasks are dot-prefixed; a shell glob misses them and a
        # hand migration loses the entire completed history.
        (session / ".3.json").write_text(json.dumps(
            {"id": "3", "subject": "  #3 done", "status": "completed",
             "description": "x"}))
        return home, session

    def _run(self, home, tmp_path, *extra):
        return subprocess.run(
            ["macf_tools", "task", "migrate-store", *extra],
            capture_output=True, text=True,
            env={**os.environ,
                 "MACEFF_AGENT_HOME_DIR": str(home),
                 "MACF_TASKS_DIR": str(tmp_path / "tasks"),
                 "MACF_SESSION_ID": "sess-abc",
                 "MACF_EVENTS_LOG_PATH": str(tmp_path / "ev.jsonl")},
        )

    def test_migrates_including_hidden_completed_tasks(self, tmp_path):
        home, _ = self._legacy_setup(tmp_path)
        result = self._run(home, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr

        target = home / "agent" / "public" / "tasks"
        names = {p.name for p in target.iterdir()}
        assert names == {"000.json", "1.json", "2.json", ".3.json"}, names
        assert ".3.json" in names, "hidden completed task was dropped"

    def test_config_is_flipped_to_home(self, tmp_path):
        home, _ = self._legacy_setup(tmp_path)
        self._run(home, tmp_path)
        config = json.loads((home / ".maceff" / "config.json").read_text())
        assert config["task_store"]["mode"] == "home"

    def test_legacy_store_is_retained(self, tmp_path):
        """Nothing is deleted — reverting is a one-line config edit."""
        home, session = self._legacy_setup(tmp_path)
        self._run(home, tmp_path)
        assert len(list(session.iterdir())) == 4

    def test_dry_run_touches_nothing(self, tmp_path):
        home, _ = self._legacy_setup(tmp_path)
        result = self._run(home, tmp_path, "--dry-run")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Dry run" in result.stdout
        assert not (home / "agent" / "public" / "tasks").exists()
        config = json.loads((home / ".maceff" / "config.json").read_text())
        assert config["task_store"]["mode"] == "legacy", "dry run flipped the config"

    def test_refuses_when_already_on_home_store(self, tmp_path):
        home, _ = self._legacy_setup(tmp_path, mode="home")
        result = self._run(home, tmp_path)
        assert result.returncode == 0
        assert "Already on the home store" in result.stdout

    def test_refuses_to_overwrite_without_force(self, tmp_path):
        home, _ = self._legacy_setup(tmp_path)
        target = home / "agent" / "public" / "tasks"
        target.mkdir(parents=True)
        (target / "1.json").write_text('{"id": "1", "subject": "pre-existing"}')

        result = self._run(home, tmp_path)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "Refusing to overwrite" in result.stdout
        assert json.loads((target / "1.json").read_text())["subject"] == "pre-existing"
        config = json.loads((home / ".maceff" / "config.json").read_text())
        assert config["task_store"]["mode"] == "legacy", "config flipped despite refusing"

    def test_store_is_gitignored_after_migration(self, tmp_path):
        home, _ = self._legacy_setup(tmp_path)
        self._run(home, tmp_path)
        ignored = subprocess.run(
            ["git", "-C", str(home), "check-ignore", "-q", "agent/public/tasks"])
        assert ignored.returncode == 0, "migrated store is tracked"
