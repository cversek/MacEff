"""`task start` refuses a task whose declared dependency is not satisfied.

`blocked_by` was an honest record of intent and nothing else: a phase gated on a
pending task started cleanly and cascade-started its parent on the way, warning
nobody. A dependency that is declared and unenforced is worse than one never
expressed, because people design against it — someone reads a tree, sees the
edge, concludes the ordering is guaranteed, and is wrong.

The guard matches the voice of the parent-over-open-children guard on
`task complete`: refuse, name what is in the way, offer `--force`. Deliberate
out-of-order execution stays possible; it just has to be stated.
"""
import argparse
from dataclasses import dataclass, field

import pytest


class _Task:
    def __init__(self, tid, status="pending", blocked_by=None, parent=None):
        self.id = str(tid)
        self.status = status
        self.blocked_by = list(blocked_by or [])
        self.blocks = []
        self.subject = f"TASK-{tid}"
        self.description = ""
        self.mtmd = None


class _Reader:
    session_path = None

    def __init__(self, tasks):
        self._tasks = {t.id: t for t in tasks}

    def read_task(self, tid):
        return self._tasks.get(str(tid).lstrip("#"))

    def read_all_tasks(self):
        return list(self._tasks.values())


@dataclass(frozen=True)
class _Outcome:
    """What one cmd_task_start call did.

    A named record rather than a tuple: the tests read whichever fields they
    care about, so nothing is identified by its position and a discarded slot
    cannot silently rebind when the shape changes.
    """
    rc: int
    writes: list = field(default_factory=list)
    events: list = field(default_factory=list)


@pytest.fixture
def wired(monkeypatch):
    """Run cmd_task_start against an in-memory store, recording every write."""
    import macf.cli as cli
    import macf.task as task_mod

    writes = []
    events = []
    monkeypatch.setattr(task_mod, "update_task_file",
                        lambda tid, data: writes.append((str(tid), data)))
    monkeypatch.setattr(cli, "append_event", lambda name, data: events.append((name, data)))

    def _run(tasks, task_id, force=False):
        monkeypatch.setattr(task_mod, "TaskReader", lambda: _Reader(tasks))
        args = argparse.Namespace(task_id=str(task_id), force=force, justification=None)
        return _Outcome(rc=cli.cmd_task_start(args), writes=writes, events=events)

    return _run


class TestBlockedStartIsRefused:
    def test_pending_blocker_refuses_and_writes_nothing(self, wired, capsys):
        """The refusal has to be a refusal, not a warning followed by the work."""
        tasks = [_Task("2", blocked_by=["1"]), _Task("1", status="pending")]
        got = wired(tasks, "2")
        out = capsys.readouterr().out
        assert got.rc == 1
        assert "#1(pending)" in out
        assert got.writes == [], "a refused start must not mutate the task"

    def test_in_progress_blocker_does_not_satisfy(self, wired, capsys):
        """Started is not delivered — the edge says this work waits on a result."""
        tasks = [_Task("2", blocked_by=["1"]), _Task("1", status="in_progress")]
        got = wired(tasks, "2")
        assert got.rc == 1
        assert "#1(in_progress)" in capsys.readouterr().out
        assert got.writes == []

    def test_missing_blocker_refuses_rather_than_waving_through(self, wired, capsys):
        """A dangling edge is when a human should look, not when the tool decides."""
        tasks = [_Task("2", blocked_by=["99"])]
        got = wired(tasks, "2")
        assert got.rc == 1
        assert "#99(not found)" in capsys.readouterr().out

    def test_force_starts_and_records_the_override(self, wired, capsys):
        """Out-of-order execution stays available; it stops being silent."""
        tasks = [_Task("2", blocked_by=["1"]), _Task("1", status="pending")]
        got = wired(tasks, "2", force=True)
        assert got.rc == 0
        assert got.writes, "--force must actually start the task"
        assert any(name == "task_start_forced_over_blockers" for name, _payload in got.events)

    def test_terminal_blockers_satisfy_and_say_nothing(self, wired, capsys):
        """Both terminal statuses clear the gate, and the common path stays quiet."""
        for status in ("completed", "archived"):
            tasks = [_Task("2", blocked_by=["1"]), _Task("1", status=status)]
            got = wired(tasks, "2")
            assert got.rc == 0, status
            assert "is blocked by" not in capsys.readouterr().out, status

    def test_unblocked_task_is_untouched(self, wired, capsys):
        """No blocked_by means no new output on the path everyone actually uses."""
        got = wired([_Task("2")], "2")
        assert got.rc == 0
        assert "is blocked by" not in capsys.readouterr().out
        assert got.writes


class TestRefusalDoesNotCascade:
    def test_refused_start_leaves_ancestors_alone(self, monkeypatch, capsys):
        """The trap in the original report: the accidental start also started its parent.

        A refusal that unwound afterwards would need that unwind kept correct
        forever. Returning before any mutation means there is nothing to unwind.
        """
        import macf.cli as cli
        import macf.task as task_mod
        import macf.task.create as create_mod

        cascaded = []
        monkeypatch.setattr(create_mod, "_run_task_start",
                            lambda pid, _cascaded=None: cascaded.append(pid))
        monkeypatch.setattr(task_mod, "update_task_file", lambda tid, data: None)
        monkeypatch.setattr(cli, "append_event", lambda name, data: None)

        child = _Task("2", blocked_by=["1"], parent="5")
        tasks = [child, _Task("1", status="pending"), _Task("5", status="pending")]
        monkeypatch.setattr(task_mod, "TaskReader", lambda: _Reader(tasks))

        rc = cli.cmd_task_start(argparse.Namespace(task_id="2", force=False, justification=None))
        assert rc == 1
        assert cascaded == [], "a refused start must not cascade-start ancestors"
