"""Regression tests: `task reparent` must keep the subject's [^#parent] marker
in sync with parent_id even when MTMD.title was never stored.

Background: reparent used to recompose the subject only `if mtmd.title is not
None` (the "Bug 3 invariant"). Most tasks store their title only inside the
composed subject string, so title was None and the recompose was skipped —
leaving a stale [^#old_parent] marker that the task tree then rendered,
contradicting both parent_id and the task's actual position. The fix recovers
the title from the subject (title_from_subject) so reparent always recomposes.

Follows the mocking conventions in test_task_mutation_verbs.py: MagicMock task
fixtures, patch the source namespaces that cmd_task_reparent imports from.
"""
import argparse
from unittest.mock import patch, MagicMock

from macf.cli import cmd_task_reparent
from macf.task.create import compose_subject, title_from_subject


def _ns(**kw):
    ns = argparse.Namespace()
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


# ---------------------------------------------------------------------------
# title_from_subject — the inverse of compose_subject, robust to marker drift
# ---------------------------------------------------------------------------

def test_title_roundtrips_across_types():
    cases = [("BUG", None, None), ("TASK", None, None),
             ("MISSION", None, None), ("PHASE", "roadmap.md", None)]
    for ttype, plan, custom in cases:
        subj = compose_subject("7", ttype, "Some Title", parent_id="3",
                               plan_ca_ref=plan, custom=custom)
        assert title_from_subject(subj, ttype, plan, custom) == "Some Title"


def test_title_recovery_ignores_stale_marker():
    # Subject carries parent [^#99]; the title recovers regardless of the value.
    subj = compose_subject("7", "BUG", "Real Title", parent_id="99")
    assert title_from_subject(subj, "BUG") == "Real Title"


def test_title_roundtrips_for_gh_issue():
    custom = {"gh_owner": "o", "gh_repo": "r",
              "gh_issue_number": "42", "gh_labels": ["bug"]}
    subj = compose_subject("7", "GH_ISSUE", "Fix the thing",
                           parent_id="3", custom=custom)
    assert title_from_subject(subj, "GH_ISSUE", None, custom) == "Fix the thing"


# ---------------------------------------------------------------------------
# cmd_task_reparent — recomposes the subject when title is None
# ---------------------------------------------------------------------------

def _titleless_task(task_id, parent_id, task_type, subject_title):
    """A task whose MTMD.title is None but whose subject was composed normally."""
    task = MagicMock()
    task.id = task_id
    task.parent_id = parent_id
    task.subject = compose_subject(task_id, task_type, subject_title,
                                   parent_id=parent_id)

    mtmd = MagicMock()
    mtmd.parent_id = parent_id
    mtmd.title = None            # the Bug-3 condition
    mtmd.task_type = task_type
    mtmd.plan_ca_ref = None
    mtmd.custom = {}
    mtmd.updates = []

    def _upd(field, value, breadcrumb, description=""):
        new = MagicMock()
        new.parent_id, new.title, new.task_type = mtmd.parent_id, None, task_type
        new.plan_ca_ref, new.custom = None, {}
        setattr(new, field, value)
        return new

    mtmd.with_updated_field.side_effect = _upd
    task.mtmd = mtmd
    task.description_with_updated_mtmd.return_value = "<!-- updated -->"
    return task


def _run_reparent(task, new_parent):
    grant = {"event": "task_grant_update",
             "data": {"task_ids": [task.id], "field": "parent_id",
                      "value": new_parent},
             "timestamp": 200}
    captured = {}
    with patch("macf.task.TaskReader") as MockReader, \
         patch("macf.task.update_task_file",
               side_effect=lambda tid, updates: captured.setdefault("updates", updates) or True), \
         patch("macf.utils.breadcrumbs.get_breadcrumb", return_value="s_t/c_0/g_a/p_x/t_0"), \
         patch("macf.task.protection.clear_grant"), \
         patch("macf.event_queries.get_latest_event",
               side_effect=lambda et, **_: grant if et == "task_grant_update" else None):
        MockReader.return_value.read_task.return_value = task
        rc = cmd_task_reparent(_ns(task_id=task.id, parent=new_parent))
    return rc, captured.get("updates", {})


def test_reparent_to_sentinel_strips_marker_when_title_none():
    task = _titleless_task("10", "5", "BUG", "Real Title")
    rc, updates = _run_reparent(task, "000")
    assert rc == 0
    subj = updates["subject"]
    assert "[^#" not in subj, f"parent marker leaked after reparent to 000: {subj!r}"
    assert title_from_subject(subj, "BUG") == "Real Title"


def test_reparent_to_digit_updates_marker_when_title_none():
    task = _titleless_task("10", "5", "BUG", "Real Title")
    rc, updates = _run_reparent(task, "7")
    assert rc == 0
    subj = updates["subject"]
    assert "[^#7]" in subj and "[^#5]" not in subj
    assert title_from_subject(subj, "BUG") == "Real Title"
