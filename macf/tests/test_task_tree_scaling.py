"""The task tree render does work proportional to the store, not its square.

The render found a node's children by scanning every task, once per node, so
its cost grew with the square of the store: about 1.5 s of a 2.2 s tree at
1,350 tasks. These tests count parent reads on a synthetic store, which
measures the shape of the work without timing anything.
"""
import argparse

import pytest


def _task(task_id, parent):
    from macf.task.models import MacfTask, MacfTaskMetaData
    return MacfTask(id=task_id, subject=f"TASK-{task_id}", description="",
                    status="in_progress",
                    mtmd=MacfTaskMetaData(parent_id=parent, custom={}))


def _render(monkeypatch, capsys, tasks, succinct=False):
    import macf.cli as cli
    import macf.task as task_mod

    class _Reader:
        session_path = None
        session_uuid = None

        def read_all_tasks(self):
            return list(tasks)

        def read_task(self, tid):
            return next((t for t in tasks if t.id == str(tid)), None)

    monkeypatch.setattr(task_mod, "TaskReader", _Reader)
    monkeypatch.setattr(cli, "get_display_mtime", lambda _d: 1.0)
    cli.cmd_task_tree(argparse.Namespace(
        task_id="000", loop=False, succinct=succinct, verbose=False,
        title_width=0, archived=False, show_all=False))
    return capsys.readouterr().out


def _store(n):
    """A root, ten branches, and the rest spread under them."""
    tasks = [_task("000", None)]
    tasks += [_task(str(i), "000") for i in range(1, 11)]
    tasks += [_task(str(i), str(1 + i % 10)) for i in range(11, n)]
    return tasks


@pytest.mark.parametrize("succinct", [False, True])
def test_parent_reads_per_task_stay_flat_as_the_store_grows(monkeypatch, capsys, succinct):
    from macf.task.models import MacfTask
    reads = {"n": 0}
    real = MacfTask.parent_id.fget

    def counted(self):
        reads["n"] += 1
        return real(self)

    monkeypatch.setattr(MacfTask, "parent_id", property(counted))
    per_task = []
    for n in (100, 400):
        reads["n"] = 0
        out = _render(monkeypatch, capsys, _store(n), succinct=succinct)
        assert f"TASK-{n - 1}" in out, "precondition: the whole store rendered"
        per_task.append(reads["n"] / n)
    # A per-node scan reads every parent once per node, so reads per task grow
    # with the store; an index built in one pass keeps them flat.
    assert per_task[1] < 1.5 * per_task[0], per_task


def test_children_keep_numeric_order(monkeypatch, capsys):
    out = _render(monkeypatch, capsys, [
        _task("000", None), _task("5", "000"),
        _task("10", "5"), _task("2", "5"), _task("7", "5"),
    ])
    assert out.index("TASK-2") < out.index("TASK-7") < out.index("TASK-10")
