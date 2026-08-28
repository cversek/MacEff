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
