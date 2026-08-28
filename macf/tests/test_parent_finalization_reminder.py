"""Completing the last child should say something about the parent.

`task complete` guards one direction: a parent closing over open children
refuses and explains why. The mirror case was silent — completing the LAST open
child left the parent `in_progress` with nothing to prompt the wrap-up. The CLI
protected against premature closure and said nothing about stalled closure.

The asymmetry costs most on an EXPERIMENT parent, which carries the terminal
artifact: the analysis and the crystallization decision. Every phase can be
individually satisfying while the thing the experiment was FOR never gets
written.
"""

class _Mtmd:
    def __init__(self, parent, task_type=None):
        self.parent_id = parent
        self.task_type = task_type


class _T:
    def __init__(self, tid, status="completed", parent=None, task_type=None):
        self.id = str(tid)
        self.status = status
        self.mtmd = _Mtmd(parent, task_type)


class _Reader:
    def __init__(self, tasks):
        self._t = {t.id: t for t in tasks}

    def read_task(self, tid):
        return self._t.get(str(tid).lstrip("#"))

    def read_all_tasks(self):
        return list(self._t.values())


def _reminder(tasks, completed):
    # Imported here rather than at module scope: a symbol that does not exist
    # yet makes the whole file uncollectable, which turns a red proof into an
    # ImportError that cannot tell you WHICH behaviour is missing.
    from macf.cli import parent_finalization_reminder
    return parent_finalization_reminder(completed, _Reader(tasks))


class TestFiresOnlyOnTheLastChild:
    def test_silent_while_a_sibling_is_still_open(self):
        """The common path stays quiet; a reminder on every completion is noise."""
        tasks = [_T("10", "in_progress", None, "EXPERIMENT"),
                 _T("11", "completed", "10"), _T("12", "pending", "10")]
        assert _reminder(tasks, "11") is None

    def test_fires_when_the_last_one_closes(self):
        tasks = [_T("10", "in_progress", None, "EXPERIMENT"),
                 _T("11", "completed", "10"), _T("12", "completed", "10")]
        out = _reminder(tasks, "12")
        assert out is not None
        assert "#10" in out and "EXPERIMENT" in out

    def test_fires_again_when_a_later_child_is_added_and_closed(self):
        """State-based, not once-per-parent — the condition can recur."""
        tasks = [_T("10", "in_progress", None, "EXPERIMENT"),
                 _T("11", "completed", "10"), _T("12", "completed", "10"),
                 _T("13", "completed", "10")]
        assert _reminder(tasks, "13") is not None


class TestStaysQuietWhenThereIsNothingToSay:
    def test_parent_already_complete(self):
        tasks = [_T("10", "completed", None, "EXPERIMENT"), _T("11", "completed", "10")]
        assert _reminder(tasks, "11") is None

    def test_paused_sibling_counts_as_open(self):
        """Paused reads as pending: deferred is not resolved, so do not prompt."""
        tasks = [_T("10", "in_progress", None, "EXPERIMENT"),
                 _T("11", "completed", "10"), _T("12", "pending", "10")]
        assert _reminder(tasks, "11") is None

    def test_root_level_task_has_no_parent_to_finalize(self):
        assert _reminder([_T("11", "completed", "000")], "11") is None


class TestTextVariesByParentType:
    def test_experiment_names_the_addenda_clause(self):
        """Load-bearing: a hypothesis added by amendment lives only in the doc.

        A prompt that says 'write the analysis' and stops invites finalizing
        over exactly that gap.
        """
        tasks = [_T("10", "in_progress", None, "EXPERIMENT"), _T("11", "completed", "10")]
        assert "addenda" in _reminder(tasks, "11")

    def test_mission_asks_for_evidence_against_success_criteria(self):
        tasks = [_T("10", "in_progress", None, "MISSION"), _T("11", "completed", "10")]
        assert "success criteria" in _reminder(tasks, "11")

    def test_unknown_type_falls_back_rather_than_printing_nothing(self):
        """The state is worth surfacing even when the guidance is generic."""
        tasks = [_T("10", "in_progress", None, None), _T("11", "completed", "10")]
        out = _reminder(tasks, "11")
        assert out is not None and "#10" in out
