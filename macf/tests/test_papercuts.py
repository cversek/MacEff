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
        return subprocess.run(
            ["macf_tools", "task", "create", "task", title, "--plan", "smoke"],
            capture_output=True, text=True,
            env={**os.environ, "MACEFF_AGENT_HOME_DIR": str(home),
                 "MACF_EVENTS_LOG_PATH": str(log)},
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
