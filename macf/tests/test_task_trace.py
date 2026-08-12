"""The trace answers "what was I in the middle of", which a tree cannot.

A tree with six open tasks reports six unfinished things. It does not report
which one attention left and owes a return to — and that distinction is the
whole difference between a stack and a pile.
"""
import pytest

from macf.task.trace import (
    Frame,
    contradictory_frames,
    last_touch,
    open_frames,
    visitation_trace,
)


class _Update:
    def __init__(self, ts, desc="", cycle=7):
        self.breadcrumb = f"s_abc/c_{cycle}/g_deadbee/p_none/t_{ts}"
        self.description = desc


class _Mtmd:
    def __init__(self, updates=None, parent_id=None):
        self.updates = updates or []
        self.parent_id = parent_id


class _Task:
    def __init__(self, task_id, status="pending", updates=None,
                 parent_id=None, blocked_by=None, subject=None):
        self.id = task_id
        self.status = status
        self.subject = subject or f"  #{task_id} a task"
        self.mtmd = _Mtmd(updates, parent_id)
        self.blocked_by = blocked_by or []


class TestLastTouch:
    def test_returns_the_most_recent_stamp(self):
        t = _Task("1", updates=[_Update(100), _Update(300), _Update(200)])
        assert last_touch(t) == 300

    def test_none_when_never_touched(self):
        assert last_touch(_Task("1")) is None


class TestVisitationTrace:
    def test_orders_touches_across_tasks_by_time(self):
        tasks = [
            _Task("1", updates=[_Update(300, "third")]),
            _Task("2", updates=[_Update(100, "first"), _Update(200, "second")]),
        ]
        assert [t.description for t in visitation_trace(tasks)] == [
            "first", "second", "third"]

    def test_preserves_consecutive_touches_on_one_task(self):
        """Dwell is part of the shape — collapsing runs would hide how long
        attention actually stayed somewhere."""
        tasks = [_Task("1", updates=[_Update(10), _Update(20), _Update(30)])]
        assert [t.task_id for t in visitation_trace(tasks)] == ["1", "1", "1"]

    def test_carries_the_cycle_from_the_breadcrumb(self):
        tasks = [_Task("1", updates=[_Update(10, cycle=42)])]
        assert visitation_trace(tasks)[0].cycle == 42


class TestOpenFrames:
    def test_the_newest_touched_in_progress_task_is_active_not_a_debt(self):
        tasks = [
            _Task("1", "in_progress", [_Update(100)]),
            _Task("2", "in_progress", [_Update(900)]),
        ]
        states = {f.task_id: f.state for f in open_frames(tasks)}
        assert states == {"2": "active", "1": "abandoned"}

    def test_a_frame_with_an_open_blocker_is_parked_not_abandoned(self):
        """The distinction that keeps the detector usable.

        A blocked frame was set down for a reason. Flagging it would cry wolf
        on correct behaviour, and a detector that cries wolf gets muted.
        """
        tasks = [
            _Task("1", "in_progress", [_Update(100)], blocked_by=["9"]),
            _Task("9", "pending", [_Update(50)]),
            _Task("2", "in_progress", [_Update(900)]),
        ]
        states = {f.task_id: f.state for f in open_frames(tasks)}
        assert states["1"] == "parked"

    def test_a_completed_blocker_no_longer_parks_a_frame(self):
        tasks = [
            _Task("1", "in_progress", [_Update(100)], blocked_by=["9"]),
            _Task("9", "completed", [_Update(50)]),
            _Task("2", "in_progress", [_Update(900)]),
        ]
        states = {f.task_id: f.state for f in open_frames(tasks)}
        assert states["1"] == "abandoned", "a resolved blocker leaves a real debt"

    def test_oldest_frame_reported_first(self):
        """The most-forgotten frame is the one most worth surfacing."""
        tasks = [
            _Task("1", "in_progress", [_Update(100)]),
            _Task("2", "in_progress", [_Update(200)]),
            _Task("3", "in_progress", [_Update(900)]),
        ]
        assert [f.task_id for f in open_frames(tasks)][0] == "1"

    def test_sentinel_is_never_a_frame(self):
        tasks = [_Task("000", "in_progress", [_Update(100)])]
        assert open_frames(tasks) == []

    def test_pending_and_completed_tasks_are_not_frames(self):
        tasks = [
            _Task("1", "pending", [_Update(100)]),
            _Task("2", "completed", [_Update(200)]),
        ]
        assert open_frames(tasks) == []

    def test_no_open_work_is_an_empty_stack(self):
        assert open_frames([]) == []


class TestEnclosingFrames:
    """A parent holding the frame attention is working inside is not a debt.

    Before this state existed, ``abandoned`` was the else-branch, and the
    classifier only ever looked *upward* (blockers, parent) — never down. So a
    MISSION with a running phase fell through to "dropped frame" by
    construction, and the false-alarm rate scaled with how faithfully work was
    decomposed. Following the decomposition policy degraded the very detector
    the work-stack policy depends on.
    """

    def test_a_parent_of_the_active_frame_encloses_it(self):
        tasks = [
            _Task("10", "in_progress", [_Update(100)]),
            _Task("30", "in_progress", [_Update(900)], parent_id="10"),
        ]
        states = {f.task_id: f.state for f in open_frames(tasks)}
        assert states == {"30": "active", "10": "enclosing"}

    def test_a_genuinely_dropped_frame_is_still_abandoned(self):
        """The control, and the reason the test above proves anything.

        A fix that simply stopped emitting ``abandoned`` would satisfy every
        assertion about enclosing frames. This is the known-answer case: an
        unblocked, unrelated, in-progress frame that attention left really is a
        dropped frame, and the classifier must still say so.
        """
        tasks = [
            _Task("10", "in_progress", [_Update(100)]),
            _Task("30", "in_progress", [_Update(900)], parent_id="10"),
            _Task("40", "in_progress", [_Update(50)]),
        ]
        states = {f.task_id: f.state for f in open_frames(tasks)}
        assert states["40"] == "abandoned", "the fix must not silence the state"
        assert states["10"] == "enclosing"

    def test_enclosure_reaches_through_grandparents(self):
        tasks = [
            _Task("10", "in_progress", [_Update(100)]),
            _Task("20", "in_progress", [_Update(200)], parent_id="10"),
            _Task("30", "in_progress", [_Update(900)], parent_id="20"),
        ]
        states = {f.task_id: f.state for f in open_frames(tasks)}
        assert states == {"30": "active", "20": "enclosing", "10": "enclosing"}

    def test_a_parent_dropped_alongside_its_child_is_not_absolved(self):
        """The discriminator between the correct rule and the tempting one.

        "Does any descendant happen to be in progress" would call the parent
        enclosing here — but attention is on an unrelated frame, and parent and
        child were dropped together. Enclosure is about where attention *is*,
        not about what is merely open underneath.
        """
        tasks = [
            _Task("10", "in_progress", [_Update(100)]),
            _Task("30", "in_progress", [_Update(200)], parent_id="10"),
            _Task("40", "in_progress", [_Update(900)]),
        ]
        states = {f.task_id: f.state for f in open_frames(tasks)}
        assert states["10"] == "abandoned"
        assert states["30"] == "abandoned"

    def test_enclosing_outranks_parked(self):
        """Work running inside a frame means it is not waiting, whatever its
        blocker list still says — and a stale blocker should not disguise
        where attention actually is."""
        tasks = [
            _Task("10", "in_progress", [_Update(100)], blocked_by=["9"]),
            _Task("9", "pending", [_Update(10)]),
            _Task("30", "in_progress", [_Update(900)], parent_id="10"),
        ]
        states = {f.task_id: f.state for f in open_frames(tasks)}
        assert states["10"] == "enclosing"

    def test_a_parent_link_cycle_does_not_hang(self):
        """Corrupt hierarchy is a data bug, not a reason to spin forever."""
        tasks = [
            _Task("1", "in_progress", [_Update(100)], parent_id="2"),
            _Task("2", "in_progress", [_Update(900)], parent_id="1"),
        ]
        states = {f.task_id: f.state for f in open_frames(tasks)}
        assert states["2"] == "active"


class TestContradictoryFrames:
    def test_completed_parent_with_running_child_is_flagged(self):
        """A structural check needing no timestamps: a parent cannot honestly
        be complete while a child of it is still in progress."""
        tasks = [
            _Task("197", "completed", [_Update(50)]),
            _Task("200", "in_progress", [_Update(100)], parent_id="197"),
            _Task("2", "in_progress", [_Update(900)]),
        ]
        assert [f.task_id for f in contradictory_frames(tasks)] == ["200"]

    def test_open_parent_with_running_child_is_ordinary(self):
        tasks = [
            _Task("197", "in_progress", [_Update(50)]),
            _Task("200", "in_progress", [_Update(100)], parent_id="197"),
            _Task("2", "in_progress", [_Update(900)]),
        ]
        assert contradictory_frames(tasks) == []

    def test_the_active_frame_is_not_reported_as_contradictory(self):
        """Where attention is right now is not a dropped frame, even if the
        parent bookkeeping is wrong — report it as work, not as debt."""
        tasks = [
            _Task("197", "completed", [_Update(50)]),
            _Task("200", "in_progress", [_Update(900)], parent_id="197"),
        ]
        assert contradictory_frames(tasks) == []


class TestMoveMarkerIsAPropertyOfTheTouch:
    """The move marker must not be recomputed from display adjacency.

    It says "attention arrived here from somewhere else", which is a fact about
    the chronological sequence. Deriving it from whichever line sits above at
    render time makes it a statement about the layout instead — and reversing
    the output then inverts its meaning while it goes on looking authoritative.
    """

    def test_marks_only_the_touches_that_changed_task(self):
        tasks = [
            _Task("1", updates=[_Update(10), _Update(20)]),
            _Task("2", updates=[_Update(30)]),
        ]
        trace = visitation_trace(tasks)
        assert [(t.task_id, t.begins_dwell) for t in trace] == [
            ("1", True), ("1", False), ("2", True)]

    def test_the_marker_survives_reversal(self):
        """The regression this class exists for.

        Rendering newest-first must not change which touches are moves.
        """
        tasks = [
            _Task("1", updates=[_Update(10)]),
            _Task("2", updates=[_Update(20)]),
            _Task("1", updates=[_Update(30)]),
        ]
        forward = [(t.task_id, t.begins_dwell) for t in visitation_trace(tasks)]
        reversed_view = list(reversed(visitation_trace(tasks)))
        assert [(t.task_id, t.begins_dwell) for t in reversed_view] == list(reversed(forward))

    def test_the_first_touch_is_always_a_move(self):
        tasks = [_Task("1", updates=[_Update(10)])]
        assert visitation_trace(tasks)[0].begins_dwell is True


class TestLoopChangeSignal:
    """`task tree --loop` must notice event-sourced changes, not only file ones.

    Scope is written to the event log and touches no task file. A detector
    watching only the store therefore cannot see `scope set`, and the loop held
    a stale frame until its 60-second timed redraw -- so scope markers appeared
    up to a minute late while ordinary task edits appeared in about a second.

    The asymmetry is the hazard rather than the delay: the display *is* moving,
    so nothing suggests part of it is stale.
    """

    def test_event_log_write_moves_the_display_signal(self, tmp_path, monkeypatch):
        from macf import cli

        store = tmp_path / "tasks"
        store.mkdir()
        (store / "1.json").write_text("{}")
        log = tmp_path / "events.jsonl"
        log.write_text("")
        monkeypatch.setattr(cli, "get_log_path", lambda: log, raising=False)
        import macf.agent_events_log as ael
        monkeypatch.setattr(ael, "get_log_path", lambda: log)

        before_display = cli.get_display_mtime(store)
        before_store = cli.get_tasks_mtime(store)

        import os, time
        time.sleep(0.01)
        with open(log, "a") as fh:
            fh.write('{"event": "scope_set"}\n')
        os.utime(log, (time.time() + 5, time.time() + 5))

        # CONTROL: the store must NOT have moved. Without this, a passing test
        # could mean the event write happened to touch a task file, which would
        # make the store-only detector sufficient and the fix unnecessary.
        assert cli.get_tasks_mtime(store) == before_store, \
            "control failed: the event write touched the store"
        assert cli.get_display_mtime(store) != before_display, \
            "an event-log-only change must trigger a redraw"

    def test_store_change_still_moves_the_signal(self, tmp_path, monkeypatch):
        """The fix must not replace one blind spot with another."""
        from macf import cli
        import macf.agent_events_log as ael

        store = tmp_path / "tasks"
        store.mkdir()
        log = tmp_path / "events.jsonl"
        log.write_text("")
        monkeypatch.setattr(ael, "get_log_path", lambda: log)

        before = cli.get_display_mtime(store)
        import os, time
        f = store / "1.json"
        f.write_text("{}")
        os.utime(f, (time.time() + 5, time.time() + 5))
        assert cli.get_display_mtime(store) != before
