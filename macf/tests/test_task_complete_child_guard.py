"""Completing a parent with incomplete children is guarded (idea #095).

A done parent over unfinished children misrepresents the tree. Outside AUTO_MODE the
completion is refused (re-run with --force to override); a leaf task completes
without any warning. Driven through the real CLI against an isolated task store.
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


def test_complete_parent_with_open_child_is_refused(store):
    _cli(store, "task", "create", "task", "Parent", "--plan", "p")
    _cli(store, "task", "create", "task", "Child", "--parent", "1", "--plan", "c")
    r = _cli(store, "task", "complete", "1", "--report", "done")
    assert r.returncode != 0, r.stdout
    assert "incomplete child" in r.stdout.lower(), r.stdout
    # Ground truth: the parent was NOT completed.
    assert "completed" not in _cli(store, "task", "get", "1").stdout.lower()


def test_force_completes_parent_over_open_child_but_still_warns(store):
    _cli(store, "task", "create", "task", "Parent", "--plan", "p")
    _cli(store, "task", "create", "task", "Child", "--parent", "1", "--plan", "c")
    r = _cli(store, "task", "complete", "1", "--report", "done", "--force")
    assert r.returncode == 0, r.stdout
    assert "incomplete child" in r.stdout.lower(), r.stdout  # warned, but proceeded


def test_leaf_task_completes_with_no_child_warning(store):
    _cli(store, "task", "create", "task", "Solo", "--plan", "p")
    r = _cli(store, "task", "complete", "1", "--report", "done")
    assert r.returncode == 0, r.stdout
    assert "incomplete child" not in r.stdout.lower()
