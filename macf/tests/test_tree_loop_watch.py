"""`task tree --loop` keeps what completed while you were watching.

A one-shot succinct render hides finished top-tier subtrees, and should: a tree
carrying hundreds of them is unreadable. In a loop that same rule deletes the
information the loop is being watched for — an operator running `--loop` is
watching completions ACCUMULATE, and suppression removes each one on the next
refresh, so the display is least informative exactly when it has the most to
report. A task that was visible a moment ago and is now gone reads as loss
rather than progress; "completed" and "vanished" look identical at a glance.

The retention window needs no new flag or state: a loop has a start, and that
start is the boundary. Exit and re-enter to clear the board, which makes hiding
an explicit act rather than an automatic one.
"""
import time

from macf.cli import touched_within_watch


class _Update:
    def __init__(self, stamp):
        self.breadcrumb = f"s_x/c_1/g_a/p_b/t_{stamp}"
        self.description = "note"


class _Mtmd:
    def __init__(self, stamps):
        self.updates = [_Update(t) for t in stamps]


class _Task:
    """Stand-in matching what `_breadcrumbs` actually reads.

    Shape verified against `task/trace.py` rather than assumed: breadcrumbs hang
    off `task.mtmd.updates` as ATTRIBUTES. An earlier version of this stub put
    dicts on `task.updates`, produced no breadcrumbs at all, and four of these
    five tests passed anyway — every assertion expecting False is satisfied by a
    stub that yields nothing. Only the one asserting True could tell.
    """

    def __init__(self, task_id, stamps):
        self.id = task_id
        self.mtmd = _Mtmd(stamps)


class TestTouchedWithinWatch:
    def test_a_one_shot_render_retains_nothing(self):
        """`since=None` must behave exactly as before — no watch, no window."""
        assert touched_within_watch(_Task("1", [int(time.time())]), None) is False

    def test_completed_during_the_watch_is_retained(self):
        started = time.time() - 60
        assert touched_within_watch(_Task("1", [int(time.time())]), started) is True

    def test_completed_before_the_watch_stays_hidden(self):
        """The accumulated history the suppression exists for."""
        started = time.time()
        assert touched_within_watch(_Task("1", [int(started) - 3600]), started) is False

    def test_a_task_with_no_recorded_touch_is_not_retained(self):
        """Absence of evidence is not evidence of a completion just now.

        Guards the direction of the fallback: unknown must read as 'before the
        watch', or every untimestamped task would pin itself to the display.
        """
        assert touched_within_watch(_Task("1", []), time.time() - 60) is False

    def test_an_unreadable_task_does_not_crash_the_render(self):
        """A malformed record must not take the whole tree down.

        Hiding is the safe direction here: it matches the one-shot behaviour, so
        the failure degrades to the previous default rather than to a traceback
        in a display the operator is watching.
        """
        class Broken:
            id = "1"
            @property
            def updates(self):
                raise ValueError("malformed update stream")

        assert touched_within_watch(Broken(), time.time() - 60) is False


class TestLoopWatchIsActuallyWired:
    """The predicate above was correct and the feature still did nothing.

    Every test in this file called `touched_within_watch` directly with an
    explicit `since`, so all five passed while the render path never supplied
    one: `display_tree` initialised its own local `loop_since = None`, and the
    loop assigned a same-named local in the enclosing command. Two bindings,
    one name. The watch predicate always saw None, and `--loop` hid completed
    top-tier tasks exactly as a one-shot render does.

    A unit test of a predicate cannot see that. These render the tree and read
    what an operator would actually have on screen.
    """

    @staticmethod
    def _task(task_id, status, parent, stamp, subject=None):
        from macf.task.models import MacfTask, MacfTaskMetaData, MacfTaskUpdate
        mtmd = MacfTaskMetaData(
            parent_id=parent,
            updates=[MacfTaskUpdate(breadcrumb=f"s_x/c_1/g_a/p_b/t_{int(stamp)}",
                                    description="note")],
            custom={},
        )
        return MacfTask(
            id=task_id,
            subject=subject or f"TASK-{task_id}",
            description="",
            status=status,
            mtmd=mtmd,
        )

    def _render(self, monkeypatch, capsys, loop: bool, tasks_factory=None):
        """Render one succinct tree and return stdout.

        In loop mode the body renders once and then hits `time.sleep`, which we
        turn into KeyboardInterrupt — the loop's own clean-exit path. That gives
        exactly one real pass through the wiring under test.
        """
        import argparse
        import macf.cli as cli
        import macf.task as task_mod

        # Freeze the clock. The watch opens at T0, so "completed during the
        # watch" must carry a stamp at or after T0 -- with a live clock the
        # fixture is built microseconds BEFORE the loop starts and every task
        # is retroactively outside its own window, which fails for a reason
        # that has nothing to do with the wiring under test.
        T0 = 1_787_000_000.0
        monkeypatch.setattr(cli.time, "time", lambda: T0)
        # ACTIVE carries the newest stamp on purpose. The renderer always shows
        # the recency-marked task so its marker cannot vanish, so a fixture whose
        # newest touch IS the completed task under test would show it in every
        # mode -- and both assertions below would pass without the watch doing
        # any work at all. Parking the marker on a separate live task is what
        # makes the completed one a real measurement.
        tasks = tasks_factory(T0) if tasks_factory else [
            self._task("000", "in_progress", None, T0, subject="ROOT"),
            self._task("1", "completed", "000", T0 + 10, subject="FRESH-DONE"),
            self._task("2", "completed", "000", T0 - 7200, subject="OLD-DONE"),
            self._task("3", "in_progress", "000", T0 + 20, subject="ACTIVE"),
        ]

        class _Reader:
            session_path = None

            def read_all_tasks(self):
                return list(tasks)

            def read_task(self, tid):
                return next((t for t in tasks if t.id == str(tid)), None)

        monkeypatch.setattr(task_mod, "TaskReader", _Reader)
        monkeypatch.setattr(cli, "get_display_mtime", lambda _d: 1.0)
        if loop:
            def _boom(_secs):
                raise KeyboardInterrupt
            monkeypatch.setattr(cli.time, "sleep", _boom)

        args = argparse.Namespace(task_id="000", loop=loop, succinct=True,
                                  verbose=False, title_width=0, archived=False,
                                  show_all=False)
        cli.cmd_task_tree(args)
        return capsys.readouterr().out

    def test_one_shot_hides_completed_top_tier(self, monkeypatch, capsys):
        """Unchanged behaviour: without a watch, finished subtrees collapse."""
        out = self._render(monkeypatch, capsys, loop=False)
        assert "FRESH-DONE" not in out
        assert "OLD-DONE" not in out

    def test_loop_keeps_what_completed_during_the_watch(self, monkeypatch, capsys):
        """The regression. Completed-since-the-watch-began must stay visible."""
        out = self._render(monkeypatch, capsys, loop=True)
        assert "FRESH-DONE" in out

    def test_loop_still_hides_what_finished_before_it_started(self, monkeypatch, capsys):
        """The watch is a window, not an amnesty — old completions stay hidden."""
        out = self._render(monkeypatch, capsys, loop=True)
        assert "OLD-DONE" not in out


class TestArchivedDescendantDoesNotPinTheChain(TestLoopWatchIsActuallyWired):
    """`archived` is finished work, and a reader that only knows "completed" says otherwise.

    A completed DETOUR sat pinned to the succinct tree for many cycles because
    three of its grandchildren were `archived` rather than `completed`. The
    collapse predicate read them as outstanding, so the whole 68-task chain
    stayed on screen every render.

    It presented as a stale row an operator should be able to clear by exiting
    and re-entering the tree. Nothing would have cleared it: the render was
    recomputing the same wrong answer each time. Inherits the render harness
    above because the two bugs share a surface and nothing else.
    """

    @staticmethod
    def _archived_case(T0):
        mk = TestArchivedDescendantDoesNotPinTheChain._task
        return [
            mk("000", "in_progress", None, T0, subject="ROOT"),
            # Resolved all the way down -- the deepest node is merely archived.
            mk("10", "completed", "000", T0 - 1000, subject="ARCHIVED-CHAIN"),
            mk("11", "archived", "10", T0 - 900, subject="ARCHIVED-CHILD"),
            # Genuinely unfinished; must survive the fix.
            mk("20", "completed", "000", T0 - 1000, subject="OPEN-CHAIN"),
            mk("21", "pending", "20", T0 - 900, subject="PENDING-CHILD"),
            # Holds the recency marker so neither parent gets shown for free.
            mk("30", "in_progress", "000", T0 + 20, subject="ACTIVE"),
        ]

    def test_archived_descendant_lets_the_chain_collapse(self, monkeypatch, capsys):
        out = self._render(monkeypatch, capsys, loop=False,
                           tasks_factory=self._archived_case)
        assert "ARCHIVED-CHAIN" not in out

    def test_pending_descendant_still_pins_the_chain(self, monkeypatch, capsys):
        """The over-correction guard: only terminal statuses may collapse a subtree."""
        out = self._render(monkeypatch, capsys, loop=False,
                           tasks_factory=self._archived_case)
        assert "OPEN-CHAIN" in out
