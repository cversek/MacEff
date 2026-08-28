"""A running sprint belongs in its own scope, because that is what holds the mode.

SPRINT work mode is *derived*: the work-mode reader returns SPRINT while a
SPRINT task sits in active scope and is in_progress. That invariant exists so
the mode survives compaction and event-window truncation rather than depending
on an imperative event.

`task create sprint` scopes the sprint task for exactly that reason. But
`scope set` REPLACES the scope, and a caller listing the workload naturally
omits the umbrella — so restarting or re-scoping a sprint dropped it, the
invariant stopped matching, and the mode-lock quietly ended while the sprint
ran on. Observed: 1h40m of live sprint with no 🏃 and the recommender
un-suppressed.

Status is the wrong anchor and scope is the right one. A sprint that is
in_progress with no scope is stopped; one that is scoped is running.
"""
import pytest


class _Mtmd:
    def __init__(self, task_type):
        self.task_type = task_type
        self.parent_id = "000"


class _T:
    def __init__(self, tid, task_type, status):
        self.id = str(tid)
        self.status = status
        self.mtmd = _Mtmd(task_type) if task_type is not None else None


class _Reader:
    def __init__(self, tasks):
        self._t = tasks

    def read_all_tasks(self):
        return list(self._t)


def _ids(tasks):
    from macf.task.scope import active_sprint_task_ids
    return active_sprint_task_ids(_Reader(tasks))


class TestFindingTheRunningSprint:
    def test_finds_an_in_progress_sprint(self):
        assert _ids([_T(1234, "SPRINT", "in_progress"), _T(5, "GH_ISSUE", "pending")]) == ["1234"]

    def test_ignores_a_completed_sprint(self):
        """A finished sprint must not resurrect its own mode-lock."""
        assert _ids([_T(1234, "SPRINT", "completed")]) == []

    def test_ignores_a_pending_sprint(self):
        """Created but never started is not running."""
        assert _ids([_T(1234, "SPRINT", "pending")]) == []

    def test_play_time_counts_too(self):
        """PLAY_TIME carries the same lifetime invariant in the work-mode reader."""
        assert _ids([_T(77, "PLAY_TIME", "in_progress")]) == ["77"]

    def test_ordinary_tasks_are_not_sprints(self):
        """Over-matching here would pin a mode-lock to unrelated work."""
        assert _ids([_T(5, "GH_ISSUE", "in_progress"), _T(6, None, "in_progress")]) == []

    def test_several_running_sprints_are_all_reported(self):
        """The caller decides what to do; this only reports candidates."""
        got = _ids([_T(1, "SPRINT", "in_progress"), _T(2, "PLAY_TIME", "in_progress")])
        assert sorted(got) == ["1", "2"]


class TestTheReleaseIsGuarded:
    def test_release_is_a_noop_when_the_mode_is_not_sprint(self, monkeypatch, capsys):
        """Unscoping ordinary work must not touch an unrelated work mode."""
        import macf.cli as cli
        monkeypatch.setattr("macf.modes.detection._get_current_work_mode", lambda: "DISCOVER")
        emitted = []
        monkeypatch.setattr(cli, "append_event", lambda n, d: emitted.append((n, d)))
        cli._clear_sprint_mode_if_unscoped()
        assert emitted == []

    def test_release_is_a_noop_while_a_sprint_is_still_scoped(self, monkeypatch):
        """Removing one task from a sprint's scope is not the end of the sprint."""
        import macf.cli as cli
        monkeypatch.setattr("macf.modes.detection._get_current_work_mode", lambda: "SPRINT")
        monkeypatch.setattr("macf.task.scope.active_sprint_task_ids", lambda reader=None: ["1234"])
        monkeypatch.setattr("macf.task.scope.get_scope_check",
                            lambda: {"active": [{"id": "1234"}, {"id": "5"}]})
        emitted = []
        monkeypatch.setattr(cli, "append_event", lambda n, d: emitted.append((n, d)))
        cli._clear_sprint_mode_if_unscoped()
        assert emitted == []

    def test_release_fires_once_the_last_sprint_leaves_scope(self, monkeypatch, capsys):
        """The stale-event case: the invariant stops matching, the event must follow."""
        import macf.cli as cli
        monkeypatch.setattr("macf.modes.detection._get_current_work_mode", lambda: "SPRINT")
        monkeypatch.setattr("macf.task.scope.active_sprint_task_ids", lambda reader=None: ["1234"])
        monkeypatch.setattr("macf.task.scope.get_scope_check", lambda: {"active": [{"id": "5"}]})
        emitted = []
        monkeypatch.setattr(cli, "append_event", lambda n, d: emitted.append((n, d)))
        cli._clear_sprint_mode_if_unscoped()
        assert emitted == [("work_mode_change", {"mode": None})]
        assert "mode-lock released" in capsys.readouterr().out
