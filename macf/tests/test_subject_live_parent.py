"""The hierarchy marker must never outlive the relationship it describes.

`[^#N]` in a stored subject is a copy of `parent_id` frozen at compose time.
A reparent moves the authority; without re-derivation at read the display keeps
asserting the old parent, and a reader has no reason to doubt it.
"""
import re

import pytest

from macf.task.create import compose_subject, subject_with_live_parent


def _clean(s):
    return re.sub(r'\033\[[0-9;]*m', '', s or '')


class _Mtmd:
    def __init__(self, parent_id=None, task_type="TASK"):
        self.parent_id = parent_id
        self.task_type = task_type
        self.title = None
        self.plan_ca_ref = None
        self.custom = None


class _Task:
    def __init__(self, task_id, subject, mtmd):
        self.id = task_id
        self.subject = subject
        self.mtmd = mtmd


def _task(task_id, composed_parent, live_parent, title="Do the thing"):
    subject = compose_subject(task_id=task_id, task_type="TASK", title=title,
                              parent_id=composed_parent)
    return _Task(task_id, subject, _Mtmd(parent_id=live_parent))


class TestSubjectWithLiveParent:

    def test_stale_marker_is_corrected_to_live_parent(self):
        """The regression: subject says #10, parent_id says #20."""
        t = _task("42", composed_parent="10", live_parent="20")
        assert "[^#10]" in _clean(t.subject), "fixture did not bake a stale marker"

        assert "[^#20]" in _clean(subject_with_live_parent(t))
        assert "[^#10]" not in _clean(subject_with_live_parent(t))

    def test_agreeing_marker_is_untouched(self):
        t = _task("42", composed_parent="10", live_parent="10")
        assert subject_with_live_parent(t) == t.subject

    def test_marker_is_dropped_when_parent_is_cleared(self):
        t = _task("42", composed_parent="10", live_parent=None)
        assert "[^#" not in _clean(subject_with_live_parent(t))

    def test_marker_is_dropped_when_reparented_to_sentinel(self):
        """compose_subject omits the marker for the sentinel; re-derivation agrees."""
        t = _task("42", composed_parent="10", live_parent="000")
        assert "[^#" not in _clean(subject_with_live_parent(t))

    def test_absent_marker_stays_absent(self):
        """Absence is honest — a reader goes and looks. A wrong marker is the lie.

        Historical subjects predate the marker convention; re-derivation must not
        rewrite 400+ of them under the banner of fixing drift.
        """
        t = _task("42", composed_parent=None, live_parent="20")
        assert subject_with_live_parent(t) == t.subject

    def test_padded_historical_marker_is_recognized(self):
        """Old subjects padded the id inside the brackets: `[^  #5]`."""
        t = _Task("6", "  #6 [^  #5] 🐛 BUG: something", _Mtmd(parent_id="20"))
        out = _clean(subject_with_live_parent(t))
        assert "[^#20]" in out
        assert "#5]" not in out

    def test_padded_historical_marker_that_agrees_is_left_alone(self):
        t = _Task("6", "  #6 [^  #5] 🐛 BUG: something", _Mtmd(parent_id="5"))
        assert subject_with_live_parent(t) == t.subject

    def test_title_and_type_are_passed_through_untouched(self):
        """Only the marker is re-derived.

        A full recomposition was measured against a 1,170-task corpus and
        rejected: title recovery is reliable only for subjects composed by
        current code, and on historical ones it duplicated the title. Fixing one
        derived value must not be able to damage the values beside it.
        """
        t = _Task("6", "  #6 [^#5] 🐛 BUG: [legacy] title with ] brackets",
                  _Mtmd(parent_id="20"))
        out = _clean(subject_with_live_parent(t))
        assert out.endswith("🐛 BUG: [legacy] title with ] brackets")

    def test_missing_mtmd_falls_back_to_stored(self):
        t = _Task("42", "  #42 [^#10] 📋 phase", None)
        assert subject_with_live_parent(t) == t.subject
