"""`task hide-completed` is idempotent, and declines where it would do nothing.

The dot prefix exists to hide completed task files from CC's scanner. Two
defects shared one cause — the command decided what to operate on by globbing
filenames it had itself renamed.
"""
import json
import os
import subprocess

import pytest


def _cli(env, *args):
    return subprocess.run(["macf_tools", *args], capture_output=True, text=True, env=env)


def _legacy_env(tmp_path):
    """A store CC actually scans — the only place hiding means anything.

    `_is_cc_session_dir` resolves `Path.home()/".claude"/"tasks"`, so the store
    has to live under a HOME for the command to treat it as scanned. Pointing
    MACF_TASKS_DIR at an arbitrary temp directory is not enough: the command
    correctly declines there, and a test built that way would exercise the
    decline path while believing it was testing the rename.
    """
    home = tmp_path / "home"
    session = home / ".claude" / "tasks" / "sess-abc"
    session.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k != "MACF_TASK_STORE_DIR"}
    env.update({"HOME": str(home),
                "MACF_TASKS_DIR": str(home / ".claude" / "tasks"),
                "MACF_SESSION_ID": "sess-abc",
                "MACF_EVENTS_LOG_PATH": str(tmp_path / "ev.jsonl")})
    return env, session


def _completed(session, task_id):
    (session / f"{task_id}.json").write_text(json.dumps(
        {"id": task_id, "subject": f"  #{task_id} done", "status": "completed",
         "description": "x"}))


class TestIdempotence:
    def test_a_second_run_does_not_add_another_dot(self, tmp_path):
        """`Path.glob('*.json')` matches dotfiles, unlike a shell glob.

        Unfiltered, run two picks up `.7.json`, reads `.stem` as `.7` — dot
        included — and hides a task it believes is called `.7`, producing
        `..7.json`. Run three makes `...7.json`.

        `hide_task_file` is not at fault and its idempotence docstring is
        accurate: it is idempotent for a given task_id. The caller derived a
        DIFFERENT id each run, from a filename the previous run had changed. The
        component was idempotent; the operation was not.
        """
        env, session = _legacy_env(tmp_path)
        _completed(session, "7")

        _cli(env, "task", "hide-completed")
        after_first = sorted(p.name for p in session.iterdir())
        _cli(env, "task", "hide-completed")
        after_second = sorted(p.name for p in session.iterdir())

        assert after_first == after_second, (
            f"a second run changed the store: {after_first} -> {after_second}"
        )
        assert not any(n.startswith("..") for n in after_second), after_second

    def test_the_summary_does_not_count_hidden_files_as_visible(self, tmp_path):
        """The same dotfile trap in the closing report.

        An unfiltered re-count reported the files it had just hidden as still
        visible, so the summary contradicted the operation directly above it.
        """
        env, session = _legacy_env(tmp_path)
        _completed(session, "7")

        result = _cli(env, "task", "hide-completed")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "CC-visible: 0" in result.stdout, result.stdout


class TestUnscannedStoreDeclines:
    def test_it_declines_rather_than_renaming_for_no_reader(self, tmp_path):
        """Nothing scans this store, so hiding in it benefits nobody.

        Renaming anyway and reporting "hidden N files from CC scanner" claims a
        protection that was not obtained — the phantom work in the report.
        """
        store = tmp_path / "home_tasks"
        store.mkdir()
        _completed(store, "7")
        env = dict(os.environ, MACF_TASK_STORE_DIR=str(store),
                   MACF_EVENTS_LOG_PATH=str(tmp_path / "ev.jsonl"))

        result = _cli(env, "task", "hide-completed")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "nothing to hide" in result.stdout.lower(), result.stdout
        assert (store / "7.json").exists(), "the file was renamed for no reader"
        assert not (store / ".7.json").exists()
