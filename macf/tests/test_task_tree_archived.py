"""An archived subtree is one 📦 line in the tree, nothing in --succinct, all of it in --all.

Before this, the tree hid tasks carrying the legacy MTMD flag and drew tasks with
status `archived` fully expanded, so archiving either vanished work without a
trace or cluttered the tree with everything it was meant to put down.
"""

import json
import os
import re
import subprocess
import sys

import pytest

SRC = os.pathsep.join(p for p in sys.path if p)


@pytest.fixture
def env(tmp_path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    e = dict(os.environ)
    e.update({"MACF_TASK_STORE_DIR": str(tasks), "MACF_EVENTS_LOG_PATH": str(tmp_path / "ev.jsonl"),
              "MACEFF_AGENT_HOME_DIR": str(tmp_path), "PYTHONPATH": SRC})
    e["_TASKS"] = str(tasks)
    return e


def run(env, *args):
    r = subprocess.run([sys.executable, "-m", "macf.cli", *args], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def make(env, title, parent=None):
    args = ["task", "create", "task", "--plan", "p"] + (["--parent", parent] if parent else [])
    return run(env, *args, title).split("Created task #")[1].split()[0]


def shown(out, tid):
    return re.search(rf"#{tid}(?!\d)", out) is not None


def line_of(out, tid):
    return next(l for l in out.splitlines() if re.search(rf"#{tid}(?!\d)", l))


@pytest.fixture
def store(env):
    """a > (b > c, e) and d; g carries only the legacy flag; h archived alone over open i."""
    t = {}
    t["a"] = make(env, "Open root")
    t["b"] = make(env, "Put down", t["a"])
    t["c"] = make(env, "Put down child", t["b"])
    t["e"] = make(env, "Put down child two", t["b"])
    t["d"] = make(env, "Still open", t["a"])
    t["g"] = make(env, "Legacy flagged")
    t["h"] = make(env, "Archived alone")
    t["i"] = make(env, "Open under archived", t["h"])
    run(env, "task", "archive", t["b"], "--reason", "moved")
    run(env, "task", "archive", t["h"], "--reason", "moved", "--no-cascade")
    p = os.path.join(env["_TASKS"], f"{t['g']}.json")
    d = json.load(open(p))
    d["description"] = d["description"].replace("task_type: TASK", "task_type: TASK\narchived: true")
    json.dump(d, open(p, "w"))
    return t


def tree(env, *flags):
    return run(env, "task", "tree", "--roles", "none", *flags)


def test_default_draws_each_archived_subtree_as_one_line(env, store):
    out = tree(env)
    b = line_of(out, store["b"])
    assert "📦" in b and "2 archived" in b
    assert not shown(out, store["c"]) and not shown(out, store["e"])
    assert shown(out, store["d"])
    assert "📦" in line_of(out, store["g"])
    # an open task under an archived parent keeps its path to the surface
    assert "📦" in line_of(out, store["h"]) and shown(out, store["i"])


def test_succinct_draws_no_archived_work(env, store):
    out = tree(env, "--succinct")
    for k in ("b", "c", "e", "g"):
        assert not shown(out, store[k]), k
    assert shown(out, store["i"])


def test_all_expands_and_archived_only_filters(env, store):
    out = tree(env, "--all")
    assert all(shown(out, store[k]) for k in "abcdeghi")
    out = tree(env, "--archived")
    assert shown(out, store["b"]) and shown(out, store["c"]) and shown(out, store["g"])
    assert not shown(out, store["d"]) and not shown(out, store["i"])
