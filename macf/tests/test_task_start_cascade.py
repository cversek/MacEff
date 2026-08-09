"""`task start` cascades pending ancestors and reports it (#115 / GH#212).

A phase in_progress under a MISSION still 'pending' makes the tree misreport
where work stands. Starting a child must start any pending ancestor and say so.
Driven through the real CLI against an isolated task store.
"""

import os
import subprocess

import pytest


def _cli(store, *args):
    env = dict(os.environ, MACF_TASK_STORE_DIR=str(store))
    return subprocess.run(["macf_tools", *args], capture_output=True, text=True, env=env)


@pytest.fixture
def store(tmp_path):
    return tmp_path


def test_start_cascades_and_reports_pending_ancestor(store):
    _cli(store, "task", "create", "task", "Parent umbrella", "--plan", "parent")
    _cli(store, "task", "create", "phase", "--parent", "1", "Child phase", "--plan", "child")

    started = _cli(store, "task", "start", "2")
    assert "Cascade-started" in started.stdout, started.stdout
    assert "#1" in started.stdout

    # Ground truth: the ancestor is actually in_progress now, not just reported.
    assert "in_progress" in _cli(store, "task", "get", "1").stdout


def test_no_cascade_when_ancestor_already_started(store):
    # Negative control: nothing to cascade means nothing is reported (and the
    # command doesn't spuriously restart an already-active ancestor).
    _cli(store, "task", "create", "task", "Parent umbrella", "--plan", "parent")
    _cli(store, "task", "start", "1")
    _cli(store, "task", "create", "phase", "--parent", "1", "Child phase", "--plan", "child")

    started = _cli(store, "task", "start", "2")
    assert "Cascade-started" not in started.stdout, started.stdout
