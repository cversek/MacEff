"""`scope set` doesn't scope a task that is already completed (#610).

The scope is a fold over events, and the fold can't see a task's status. So a completed
task listed again in a `scope set` used to read active, and the stop gate counted it as
remaining work until it was removed by hand. Seen in a sprint on Oct 16: a task completed
in the sprint stayed active after the next `scope set`.

Run in-process through the real parser, so the test exercises this checkout's code.
"""
import pytest


@pytest.fixture
def cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MACF_TASK_STORE_DIR", str(tmp_path / "tasks"))
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    (tmp_path / "tasks").mkdir()
    from macf.cli import _build_parser
    parser = _build_parser()

    def run(*argv):
        capsys.readouterr()
        args = parser.parse_args(["task", *argv])
        code = args.func(args)
        return code, capsys.readouterr().out
    return run


def test_a_completed_task_is_not_scoped_and_is_named(cli):
    from macf.task.scope import get_scope_state
    for title in ("A", "B"):
        assert cli("create", "task", title, "--plan", "p", "--parent", "000")[0] == 0
    cli("start", "1")
    assert cli("complete", "1", "--report", "done")[0] == 0
    code, out = cli("scope", "set", "1", "2")
    assert code == 0
    assert "#1 is done (completed or archived), so it was not scoped" in out and "Scoped 1 task(s)" in out
    assert get_scope_state() == {"2": "active"}


def test_only_completed_tasks_scope_nothing(cli):
    from macf.task.scope import get_scope_state
    cli("create", "task", "A", "--plan", "p", "--parent", "000")
    cli("start", "1")
    cli("complete", "1", "--report", "done")
    code, out = cli("scope", "set", "1")
    assert code == 1 and "No open tasks to scope" in out
    assert get_scope_state() == {}


def test_scope_add_skips_a_completed_task_too(cli):
    from macf.task.scope import get_scope_state
    for title in ("A", "B"):
        cli("create", "task", title, "--plan", "p", "--parent", "000")
    cli("start", "1")
    cli("complete", "1", "--report", "done")
    code, out = cli("scope", "add", "1", "2")
    assert code == 0 and "#1: completed" in out
    assert get_scope_state() == {"2": "active"}


def test_an_archived_task_is_not_scoped_either(cli, tmp_path):
    """A task file with status "archived" (written by the archiver before `task archive` was
    deprecated) is as finished as a completed one; listing it again must not revive it."""
    import json
    from macf.task.reader import TaskReader
    from macf.task.scope import get_scope_state
    for title in ("A", "B"):
        cli("create", "task", title, "--plan", "p", "--parent", "000")
    path = tmp_path / "tasks" / "1.json"
    record = json.loads(path.read_text())
    record["status"] = "archived"
    path.write_text(json.dumps(record))
    assert TaskReader().read_task("1").status == "archived"
    code, out = cli("scope", "set", "1", "2")
    assert code == 0 and "#1 is done" in out
    assert get_scope_state() == {"2": "active"}
    _, out = cli("scope", "add", "1")
    assert "#1: archived" in out
