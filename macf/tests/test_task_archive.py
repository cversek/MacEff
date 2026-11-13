"""`task archive` is a real state change: written, read back, recorded, and reversible.

The command was retired once because it printed a success line while writing
nothing. These tests hold it to the opposite: every task it reports as archived
was read back from disk with status `archived`; a write that does not stick
exits nonzero and names the task; `task unarchive` puts every task back at the
status it had; and `restore` / `archived list` stay retired, pointing at the
commands that replaced them.
"""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from macf import cli

# The subprocess imports macf exactly as this test process does, so it runs the
# code under test rather than whatever `macf_tools` is first on PATH.
SRC = os.pathsep.join(p for p in sys.path if p)


# --- an isolated store --------------------------------------------------------

@pytest.fixture
def store(tmp_path, monkeypatch):
    """A home task store, event log and agent home that are all the test's own."""
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    env = dict(os.environ)
    env.update({
        "MACF_TASK_STORE_DIR": str(tasks),
        "MACF_EVENTS_LOG_PATH": str(tmp_path / "events.jsonl"),
        "MACEFF_AGENT_HOME_DIR": str(tmp_path),
        "PYTHONPATH": SRC,
    })
    for k in ("MACF_TASK_STORE_DIR", "MACF_EVENTS_LOG_PATH", "MACEFF_AGENT_HOME_DIR"):
        monkeypatch.setenv(k, env[k])
    return SimpleNamespace(tasks=tasks, env=env, events=tmp_path / "events.jsonl")


def run(store, *args):
    return subprocess.run([sys.executable, "-m", "macf.cli", *args],
                          capture_output=True, text=True, env=store.env)


def make(store, title, parent=None, status="pending"):
    """Create a task through the CLI, then set its status on disk."""
    args = ["task", "create", "task", "--plan", "p"]
    if parent:
        args += ["--parent", parent]
    r = run(store, *args, title)
    assert r.returncode == 0, r.stdout + r.stderr
    tid = r.stdout.split("Created task #")[1].split()[0]
    set_status(store, tid, status)
    return tid


def task_file(store, tid):
    return store.tasks / f"{tid}.json"


def set_status(store, tid, status):
    p = task_file(store, tid)
    d = json.loads(p.read_text())
    d["status"] = status
    p.write_text(json.dumps(d))


def status(store, tid):
    return json.loads(task_file(store, tid).read_text())["status"]


def events(store, name):
    if not store.events.exists():
        return []
    out = []
    for line in store.events.read_text().splitlines():
        e = json.loads(line)
        if e.get("event") == name:
            out.append(e["data"])
    return out


@pytest.fixture
def tree(store):
    """#a (in progress) > #b (completed) > #c (pending), and #d beside them."""
    a = make(store, "Root", status="in_progress")
    b = make(store, "Child", parent=a, status="completed")
    c = make(store, "Grandchild", parent=b, status="pending")
    d = make(store, "Bystander", status="pending")
    return SimpleNamespace(a=a, b=b, c=c, d=d)


# --- archive ------------------------------------------------------------------

def test_archive_cascades_reads_back_and_records(store, tree):
    r = run(store, "task", "archive", tree.a, "--reason", "moved to a sibling agent")
    assert r.returncode == 0, r.stdout + r.stderr
    assert [status(store, t) for t in (tree.a, tree.b, tree.c)] == ["archived"] * 3
    assert status(store, tree.d) == "pending"
    assert "3 archived" in r.stdout

    desc = json.loads(task_file(store, tree.b).read_text())["description"]
    assert "type: archive" in desc and "prior_status: completed" in desc
    assert "moved to a sibling agent" in desc

    ev = events(store, "task_archived")
    assert len(ev) == 1
    assert sorted(ev[0]["task_ids"]) == sorted([tree.a, tree.b, tree.c])
    assert ev[0]["reason"] == "moved to a sibling agent"


def test_unarchive_restores_each_prior_status(store, tree):
    assert run(store, "task", "archive", tree.a, "--reason", "r").returncode == 0
    r = run(store, "task", "unarchive", tree.a)
    assert r.returncode == 0, r.stdout + r.stderr
    assert [status(store, t) for t in (tree.a, tree.b, tree.c)] == ["in_progress", "completed", "pending"]
    desc = json.loads(task_file(store, tree.a).read_text())["description"]
    assert "archived: true" not in desc
    assert len(events(store, "task_unarchived")) == 1


def test_dry_run_changes_nothing_and_no_cascade_stops_at_the_target(store, tree):
    before = {t: task_file(store, t).read_bytes() for t in (tree.a, tree.b, tree.c)}
    r = run(store, "task", "archive", tree.a, "--reason", "r", "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert {t: task_file(store, t).read_bytes() for t in before} == before
    assert events(store, "task_archived") == []
    for t in (tree.a, tree.b, tree.c):
        assert f"#{t}" in r.stdout

    r = run(store, "task", "archive", tree.b, "--reason", "r", "--no-cascade")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (status(store, tree.b), status(store, tree.c)) == ("archived", "pending")


def test_reason_is_required(store, tree):
    r = run(store, "task", "archive", tree.a)
    assert r.returncode != 0
    r = run(store, "task", "archive", tree.a, "--reason", "   ")
    assert r.returncode != 0
    assert status(store, tree.a) == "in_progress"


def test_a_write_that_does_not_stick_fails_and_names_the_task(store, tree, monkeypatch, capsys):
    """The old command's defect, planted: the writer reports success and writes nothing."""
    import macf.task.archive as archive_mod
    monkeypatch.setattr(archive_mod, "update_task_file", lambda *a, **k: True)
    rc = cli.cmd_task_archive(SimpleNamespace(task_ids=[tree.a], reason="r", no_cascade=False,
                                              dry_run=False, json_output=False))
    out = capsys.readouterr().out
    assert rc != 0
    assert f"#{tree.a}" in out and "failed" in out.lower()
    assert "3 archived" not in out
    assert status(store, tree.a) == "in_progress"


def test_archiving_a_scoped_task_takes_it_out_of_scope(store, tree):
    assert run(store, "task", "scope", "set", tree.c).returncode == 0
    r = run(store, "task", "archive", tree.a, "--reason", "r")
    assert r.returncode == 0, r.stdout + r.stderr
    assert any(tree.c in e["task_ids"] for e in events(store, "scope_removed"))
    assert "scope" in r.stdout.lower()


# --- the rest of the old trio stays retired, pointing at what replaced it -----

@pytest.mark.parametrize("fn,ns", [
    (cli.cmd_task_restore, SimpleNamespace(archive_path_or_id="1", json_output=False)),
    (cli.cmd_task_archived_list, SimpleNamespace(json_output=False)),
])
def test_restore_and_archived_list_fail_closed(fn, ns, capsys):
    assert fn(ns) == 2
    out = capsys.readouterr().out
    assert "DEPRECATED" in out
    assert "task unarchive" in out or "task tree --archived" in out


# --- review of PR 1006 (CTB): re-archive and earlier archives -----------------

def test_archiving_twice_keeps_the_first_prior_status(store, tree):
    """A second archive must skip the task, or it records prior_status 'archived'."""
    assert run(store, "task", "archive", tree.b, "--reason", "first").returncode == 0
    r = run(store, "task", "archive", tree.b, "--reason", "second")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 archived, 2 already so" in r.stdout
    desc = json.loads(task_file(store, tree.b).read_text())["description"]
    assert "second" not in desc
    assert run(store, "task", "unarchive", tree.b).returncode == 0
    assert (status(store, tree.b), status(store, tree.c)) == ("completed", "pending")


def test_cascading_unarchive_leaves_earlier_archives_alone(store, tree):
    """Unarchiving a root restores what that call archived, not what was put down before it."""
    assert run(store, "task", "archive", tree.c, "--reason", "earlier, on its own").returncode == 0
    assert run(store, "task", "archive", tree.a, "--reason", "later, the whole tree").returncode == 0
    r = run(store, "task", "unarchive", tree.a)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (status(store, tree.a), status(store, tree.b)) == ("in_progress", "completed")
    assert status(store, tree.c) == "archived"
    assert f"#{tree.c}" in r.stdout and "earlier" in r.stdout.lower()


def test_unarchiving_a_legacy_flagged_task_keeps_its_status(store, tree):
    """THM's review: a task with only the old MTMD flag was never set to `archived`."""
    p = task_file(store, tree.b)
    d = json.loads(p.read_text())
    d["description"] = d["description"].replace("task_type: TASK", "task_type: TASK\narchived: true")
    p.write_text(json.dumps(d))
    r = run(store, "task", "unarchive", tree.b, "--no-cascade")
    assert r.returncode == 0, r.stdout + r.stderr
    assert status(store, tree.b) == "completed"
    assert "archived: true" not in json.loads(p.read_text())["description"]
