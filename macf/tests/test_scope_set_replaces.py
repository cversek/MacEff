"""`scope set` replaces the scope's open tasks, as task_management and autonomous_sprint say.

It used to add: a task left out of a later `scope set` stayed active, and the stop gate kept
waiting on it. Completed members stay as the scope's history, and a `scope set` that scopes
nothing changes nothing.

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


def make(cli, *titles):
    for title in titles:
        assert cli("create", "task", title, "--plan", "p", "--parent", "000")[0] == 0


def test_a_task_left_out_of_a_later_scope_set_leaves_the_scope_and_is_named(cli):
    from macf.task.scope import get_scope_state
    make(cli, "A", "B", "C")
    cli("scope", "set", "1", "2")
    code, out = cli("scope", "set", "2", "3")
    assert code == 0
    assert get_scope_state() == {"2": "active", "3": "active"}
    assert "#1 left the scope" in out


def test_a_paused_task_left_out_leaves_too_and_a_relisted_one_stays_paused(cli):
    from macf.task.scope import get_scope_state
    make(cli, "A", "B", "C")
    cli("scope", "set", "1", "2")
    assert cli("scope", "pause", "1", "2", "--justification", "waits on the operator's word")[0] == 0
    code, out = cli("scope", "set", "2", "3")
    assert code == 0
    assert get_scope_state() == {"2": "paused", "3": "active"}
    assert "#1 left the scope" in out


def test_completed_members_stay_as_history(cli):
    from macf.task.scope import get_scope_state
    make(cli, "A", "B")
    cli("scope", "set", "1", "2")
    cli("start", "1")
    assert cli("complete", "1", "--report", "done")[0] == 0
    cli("scope", "set", "2")
    assert get_scope_state() == {"1": "inactive", "2": "active"}


def test_a_scope_set_that_scopes_nothing_keeps_the_scope(cli):
    from macf.task.scope import get_scope_state
    make(cli, "A", "B")
    cli("scope", "set", "1")
    cli("start", "2")
    cli("complete", "2", "--report", "done")
    code, _ = cli("scope", "set", "2")
    assert code == 1
    assert get_scope_state() == {"1": "active"}
