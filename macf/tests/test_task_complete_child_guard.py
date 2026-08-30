"""Completing a parent with incomplete children is guarded (idea #095).

A done parent over unfinished children misrepresents the tree. Outside AUTO_MODE the
completion is refused (re-run with --force to override); a leaf task completes
without any warning. Driven through the real CLI against an isolated task store.
"""

import os
import subprocess

import pytest


def _cli(store, *args, auto=False):
    env = dict(os.environ, MACF_TASK_STORE_DIR=str(store))
    # detect_auto_mode consults MACF_AUTO_MODE before the event log, so this
    # drives the real resolution path rather than patching around it.
    env["MACF_AUTO_MODE"] = "true" if auto else "false"
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


def test_auto_mode_completes_parent_over_open_child_without_force(store):
    """The AUTO_MODE branch of the guard must be REACHABLE.

    Every other test in this file is satisfied by a refusal, and the refusal is
    what a broken mode subsystem also produces: `detect_auto_mode` raising sends
    the handler down `_auto = False`, the completion is refused, and the tests
    above stay green while the exemption they document has stopped existing.
    That is not hypothetical — it shipped. `cli.py` imported `detect_auto_mode`
    from `macf.modes`, which did not export it, so for the life of that import
    the gate was UNSATISFIABLE in AUTO_MODE and `--force` was the only way past
    a guard that was never meant to need one. A gate that cannot be satisfied
    legitimately teaches its users to reach for the override.

    So this asserts the positive case explicitly: AUTO_MODE, no `--force`, the
    completion proceeds and still warns. It fails the moment the mode subsystem
    stops resolving, which is the property the other three cannot observe.
    """
    _cli(store, "task", "create", "task", "Parent", "--plan", "p")
    _cli(store, "task", "create", "task", "Child", "--parent", "1", "--plan", "c")
    r = _cli(store, "task", "complete", "1", "--report", "done", auto=True)

    assert r.returncode == 0, (
        "AUTO_MODE completion was refused — the guard's exemption is unreachable.\n"
        f"stdout: {r.stdout}\nstderr: {r.stderr}"
    )
    assert "incomplete child" in r.stdout.lower(), r.stdout   # warned
    assert "auto_mode" in r.stdout.lower(), r.stdout          # and said why it proceeded
    assert "could not resolve mode" not in r.stderr, (
        f"the mode subsystem failed to resolve: {r.stderr}"
    )
