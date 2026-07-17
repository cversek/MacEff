"""Tests for the stale-resume behavior on `task start`.

When a task last worked in an earlier cycle is resumed (whether it is still
`pending` or was left `in_progress` across cycles), `task start` bumps the
stamp with a resume update and prints a banner prompting the read-notes-and-
narrate ritual. A same-cycle re-start of an already-active task stays a no-op.

Covers:
  _stale_resume_info   — the pure detector (cycle-delta + not-complete)
  cmd_task_start       — banner emission on stale resume vs fresh start

Patch targets (mirrors test_task_mutation_verbs.py conventions):
  TaskReader          — macf.task.TaskReader          (local import in cmd)
  update_task_file    — macf.task.update_task_file     (local import in cmd)
  unhide_task_file    — macf.task.reader.unhide_task_file
  get_breadcrumb      — macf.utils.breadcrumbs.get_breadcrumb (local import)
  append_event        — macf.cli.append_event          (top-level import in cli.py)

Fixtures use generic placeholders only (no project-specific names).
"""
import argparse
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from macf.cli import _stale_resume_info, cmd_task_start


_PATCH_TASK_READER = "macf.task.TaskReader"
_PATCH_UPDATE = "macf.task.update_task_file"
_PATCH_UNHIDE = "macf.task.reader.unhide_task_file"
_PATCH_BREADCRUMB = "macf.utils.breadcrumbs.get_breadcrumb"
_PATCH_APPEND_EVENT = "macf.cli.append_event"


def _bc(cycle, ts):
    # minimal enhanced breadcrumb with the cycle + timestamp fields the detector reads
    return f"s_abc12345/c_{cycle}/p_def67890/t_{ts}"


def _fake_task(status="in_progress", last_cycle=23, last_ts=1000,
               created_cycle=20, created_ts=500, with_updates=True):
    """A task whose most recent activity sits in `last_cycle`."""
    updates = []
    if with_updates:
        updates = [SimpleNamespace(breadcrumb=_bc(last_cycle, last_ts))]
    mtmd = SimpleNamespace(
        updates=updates,
        started_breadcrumb=None,
        creation_breadcrumb=_bc(created_cycle, created_ts),
        task_type=None,
        plan_ca_ref=None,
    )
    task = MagicMock()
    task.status = status
    task.mtmd = mtmd
    task.description_with_updated_mtmd.return_value = "<!-- updated description -->"
    return task


class TestStaleResumeInfo:
    def test_prior_cycle_is_stale(self):
        task = _fake_task(status="in_progress", last_cycle=23, last_ts=1000)
        with patch(_PATCH_BREADCRUMB, return_value=_bc(25, 2000)):
            assert _stale_resume_info(task) == (23, 1000, 25)

    def test_same_cycle_is_not_stale(self):
        task = _fake_task(status="in_progress", last_cycle=25, last_ts=1900)
        with patch(_PATCH_BREADCRUMB, return_value=_bc(25, 2000)):
            assert _stale_resume_info(task) is None

    def test_completed_is_never_stale(self):
        task = _fake_task(status="completed", last_cycle=23)
        with patch(_PATCH_BREADCRUMB, return_value=_bc(25, 2000)):
            assert _stale_resume_info(task) is None

    def test_no_mtmd_is_not_stale(self):
        task = MagicMock()
        task.status = "pending"
        task.mtmd = None
        with patch(_PATCH_BREADCRUMB, return_value=_bc(25, 2000)):
            assert _stale_resume_info(task) is None

    def test_falls_back_to_creation_when_no_updates(self):
        task = _fake_task(status="pending", created_cycle=20, created_ts=500,
                          with_updates=False)
        with patch(_PATCH_BREADCRUMB, return_value=_bc(25, 2000)):
            assert _stale_resume_info(task) == (20, 500, 25)


class TestStartBanner:
    def _run(self, task, cur_bc):
        reader = MagicMock()
        reader.session_path = "/tmp/session"
        reader.read_task.return_value = task
        args = argparse.Namespace(task_id="10")
        with patch(_PATCH_TASK_READER, return_value=reader), \
             patch(_PATCH_UPDATE) as upd, \
             patch(_PATCH_UNHIDE), \
             patch(_PATCH_APPEND_EVENT), \
             patch(_PATCH_BREADCRUMB, return_value=cur_bc):
            rc = cmd_task_start(args)
        return rc, upd

    def test_stale_in_progress_prints_banner_and_bumps(self, capsys):
        task = _fake_task(status="in_progress", last_cycle=23, last_ts=1000)
        # capture the resume update appended to the deep-copied mtmd before persist
        appended = []
        with patch("macf.task.models.MacfTaskUpdate",
                   side_effect=lambda **kw: appended.append(kw) or MagicMock(**kw)):
            rc, upd = self._run(task, _bc(25, 2000))
        out = capsys.readouterr().out
        assert rc == 0
        assert "🔁 Resuming #10" in out
        assert "Cycle 23" in out
        assert "narrate" in out.lower()
        # bumped: a resume update was appended and the task file was re-persisted
        assert upd.called
        assert any("resumed" in kw["description"].lower() for kw in appended)

    def test_same_cycle_in_progress_is_plain_noop(self, capsys):
        task = _fake_task(status="in_progress", last_cycle=25, last_ts=1900)
        rc, _ = self._run(task, _bc(25, 2000))
        out = capsys.readouterr().out
        assert rc == 0
        assert "already in_progress" in out
        assert "🔁 Resuming" not in out

    def test_fresh_pending_starts_without_banner(self, capsys):
        task = _fake_task(status="pending", last_cycle=25, last_ts=1900)
        rc, _ = self._run(task, _bc(25, 2000))
        out = capsys.readouterr().out
        assert rc == 0
        assert "started" in out
        assert "🔁 Resuming" not in out
