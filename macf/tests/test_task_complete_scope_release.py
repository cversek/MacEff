"""Completing a scope OWNER (sprint / play_time) must release its scope.

A force-completed sprint used to leave its scoped members 'active' in the gate:
`remaining` never reached 0, the auto-clear never fired, and the Stop-hook scope
gate nagged forever after the sprint was done. Completing the owner must release
the whole scope — the children return to the tree at their real status, they are
NOT fake-completed.

These are CLI integration tests because the fix lives in the `task complete`
command path (the scope primitives themselves were already correct).
"""

import json
import os
import subprocess

import pytest


@pytest.fixture(autouse=True)
def isolated_task_env(tmp_path, monkeypatch):
    """Isolate CLI subprocess calls from production tasks and event logs."""
    test_tasks_dir = tmp_path / "tasks"
    test_session_id = "test-session-uuid"
    test_session_dir = test_tasks_dir / test_session_id
    test_session_dir.mkdir(parents=True)
    test_log = tmp_path / "test_cli_events.jsonl"

    subprocess_env = {
        **os.environ,
        "MACF_TASKS_DIR": str(test_tasks_dir),
        "MACF_SESSION_ID": test_session_id,
        "MACF_EVENTS_LOG_PATH": str(test_log),
    }
    monkeypatch.setenv("MACF_TASKS_DIR", str(test_tasks_dir))
    monkeypatch.setenv("MACF_SESSION_ID", test_session_id)
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))

    yield {"tasks_dir": test_tasks_dir, "session_dir": test_session_dir, "env": subprocess_env}


def _task(args, env):
    return subprocess.run(
        ["macf_tools", "task", *args], capture_output=True, text=True, env=env
    )


def _active_count(env):
    r = _task(["scope", "check"], env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["active_count"]


class TestScopeReleaseOnOwnerCompletion:
    def test_force_completed_sprint_releases_its_scope(self, isolated_task_env):
        env = isolated_task_env["env"]

        created = _task(
            ["create", "sprint", "Repro sprint",
             "--children", "Child A", "Child B", "--json"],
            env,
        )
        assert created.returncode == 0, created.stderr
        sprint_id = json.loads(created.stdout)["task_id"]

        # The sprint scopes itself + its two children.
        assert _active_count(env) > 0

        # Force-complete the sprint with its children deliberately still open —
        # this is the exact scenario that used to strand the scope gate.
        done = _task(
            ["complete", str(sprint_id),
             "--force",
             "--justification", "test: children deliberately left open",
             "--report", "reproduce the scope-release-on-owner-completion bug"],
            env,
        )
        assert done.returncode == 0, done.stderr

        # The gate is released, not stuck reporting 'N remaining'.
        assert _active_count(env) == 0
        assert "released" in done.stdout.lower() or "scope owner" in done.stdout.lower()

    def test_completing_a_plain_scoped_member_does_not_over_clear(self, isolated_task_env):
        """Guard: the owner-release path must NOT fire for a non-owner completion —
        completing one plain scoped task leaves the others active."""
        env = isolated_task_env["env"]

        t1 = json.loads(_task(["create", "task", "Task one", "--plan", "p", "--json"], env).stdout)["task_id"]
        t2 = json.loads(_task(["create", "task", "Task two", "--plan", "p", "--json"], env).stdout)["task_id"]

        set_res = _task(["scope", "set", str(t1), str(t2)], env)
        assert set_res.returncode == 0, set_res.stderr
        assert _active_count(env) == 2

        _task(["start", str(t1)], env)
        done = _task(["complete", str(t1), "--report", "done"], env)
        assert done.returncode == 0, done.stderr

        # t1 goes inactive; t2 stays active — no over-clear.
        assert _active_count(env) == 1
