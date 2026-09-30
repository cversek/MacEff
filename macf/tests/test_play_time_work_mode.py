"""A running play time reports the work mode the agent declared.

The work-mode reader gives SPRINT its lock by deriving the mode from scope: a
SPRINT task in active scope means the mode is SPRINT, whatever was declared.
PLAY_TIME shared that branch and returned the chain phase, so a declared mode
never showed while a play time ran: a Markov override away from the chain, and
every mode after the chain was exhausted, read as the chain's current or last
step. `mode set-work` takes the previous mode from the same reader, so the
play time's own transition log recorded the wrong "from" as well.

A play time has no lock. Its declared mode is recorded on the task
(`current_work_mode`, written by every `mode set-work`), and that is what the
reader now returns; the chain phase remains the answer when nothing was
declared.
"""
import pytest

CHAIN = ["DISCOVER", "EXPERIMENT", "CURATE", "CONSOLIDATE"]


class _Mtmd:
    def __init__(self, task_type, custom):
        self.task_type = task_type
        self.custom = custom


class _T:
    def __init__(self, tid, task_type, custom=None, status="in_progress"):
        self.id = str(tid)
        self.status = status
        self.mtmd = _Mtmd(task_type, custom or {})


def _mode_with(monkeypatch, task):
    from macf.modes import detection

    class _Reader:
        def read_task(self, tid):
            return task if str(tid) == task.id else None

    monkeypatch.setattr("macf.task.scope.get_scope_check",
                        lambda: {"active": [{"id": task.id}]})
    monkeypatch.setattr("macf.task.reader.TaskReader", _Reader)
    return detection._get_current_work_mode()


def test_a_declared_override_is_reported(monkeypatch):
    task = _T(7, "PLAY_TIME", {"predetermined_chain": CHAIN, "chain_position": 2,
                               "current_work_mode": "EXPERIMENT"})
    assert _mode_with(monkeypatch, task) == "EXPERIMENT"


def test_after_the_chain_the_declared_mode_is_reported(monkeypatch):
    task = _T(7, "PLAY_TIME", {"predetermined_chain": CHAIN, "chain_position": 3,
                               "chain_exhausted": True, "current_work_mode": "DISCOVER"})
    assert _mode_with(monkeypatch, task) == "DISCOVER"


def test_without_a_declared_mode_the_chain_phase_is_reported(monkeypatch):
    task = _T(7, "PLAY_TIME", {"predetermined_chain": CHAIN, "chain_position": 2})
    assert _mode_with(monkeypatch, task) == "CURATE"


def test_an_unknown_declared_mode_falls_back_to_the_chain_phase(monkeypatch):
    task = _T(7, "PLAY_TIME", {"predetermined_chain": CHAIN, "chain_position": 1,
                               "current_work_mode": "NOT_A_MODE"})
    assert _mode_with(monkeypatch, task) == "EXPERIMENT"


def test_a_running_sprint_still_locks_the_mode(monkeypatch):
    task = _T(9, "SPRINT", {"current_work_mode": "DISCOVER"})
    assert _mode_with(monkeypatch, task) == "SPRINT"
