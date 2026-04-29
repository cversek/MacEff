"""
Tests for Phase 5: smart task complete for SPRINT and PLAY_TIME task types.

Tests:
  TC01 SPRINT all children completed → completes cleanly
  TC02 SPRINT open children, no --force → blocked with error message listing child IDs
  TC03 SPRINT open children + --force → completes with warning
  TC04 SPRINT auto-aggregate appears in completion_report
  TC05 SPRINT idea notes counter prompted on stdout
  TC06 PLAY_TIME timer not expired → warns but completes
  TC07 PLAY_TIME timer expired → completes silently (no warning)
  TC08 PLAY_TIME auto-aggregate appears in completion_report

Test count: 8 tests.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Patch target constants
# Local imports in cmd_task_complete resolve at call-time against the
# submodule where the name lives, so we patch those submodule attributes.
# append_event is module-level in macf.cli, so it is patched there.
# ---------------------------------------------------------------------------

_TASK_MOD = "macf.task"                    # TaskReader, update_task_file
_BC_MOD = "macf.utils.breadcrumbs"        # get_breadcrumb
_SCOPE_MOD = "macf.task.scope"             # is_task_timer_blocked, complete_scoped_task
_READER_MOD = "macf.task.reader"           # hide_task_file
_EVENTS_MOD = "macf.cli"                   # append_event (module-level import)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_fake_update(description=""):
    u = MagicMock()
    u.description = description
    return u


def _make_fake_mtmd(task_type, custom=None, updates=None, plan_ca_ref=None, parent_id=None):
    m = MagicMock()
    m.task_type = task_type
    m.custom = custom or {}
    m.updates = updates or []
    m.plan_ca_ref = plan_ca_ref
    m.parent_id = parent_id
    m.completion_breadcrumb = None
    m.completion_report = None
    return m


def _make_fake_task(task_id, status="in_progress", task_type="SPRINT",
                    custom=None, updates=None, plan_ca_ref=None, parent_id=None,
                    description=""):
    t = MagicMock()
    t.id = str(task_id)
    t.status = status
    t.description = description
    mtmd = _make_fake_mtmd(task_type, custom=custom, updates=updates,
                            plan_ca_ref=plan_ca_ref, parent_id=parent_id)
    t.mtmd = mtmd
    t.description_with_updated_mtmd = lambda m: description
    return t


def _make_fake_child(child_id, parent_id, status="in_progress"):
    t = MagicMock()
    t.id = str(child_id)
    t.status = status
    t.parent_id = str(parent_id)
    t.mtmd = None
    return t


def _make_args(task_id, report=None, force=False, commit=None, verified=None, justification=None):
    return argparse.Namespace(
        task_id=str(task_id),
        report=report,
        force=force,
        commit=commit or [],
        verified=verified,
        justification=justification,
    )


def _make_reader(task, all_tasks, session_path):
    """Return a constructor mock whose instance yields task and all_tasks."""
    instance = MagicMock()
    instance.read_task = MagicMock(return_value=task)
    instance.read_all_tasks = MagicMock(return_value=all_tasks)
    instance.session_path = str(session_path)
    FakeReader = MagicMock(return_value=instance)
    return FakeReader


def _std_patches(fake_reader):
    """Context manager stack for the standard infrastructure patches."""
    return [
        patch(f"{_TASK_MOD}.TaskReader", fake_reader),
        patch(f"{_TASK_MOD}.update_task_file", return_value=True),
        patch(f"{_BC_MOD}.get_breadcrumb", return_value="s_t/c_1/g_a/p_b/t_1000"),
        patch(f"{_EVENTS_MOD}.append_event"),
        patch(f"{_SCOPE_MOD}.is_task_timer_blocked", return_value={"blocked": False}),
        patch(f"{_SCOPE_MOD}.complete_scoped_task", return_value={"success": True, "remaining_active": 0}),
        patch(f"{_READER_MOD}.hide_task_file", return_value=True),
    ]


from contextlib import ExitStack


def run_complete(args, fake_reader, extra_patches=None):
    """Run cmd_task_complete with standard infrastructure patched."""
    from macf.cli import cmd_task_complete
    patches = _std_patches(fake_reader)
    if extra_patches:
        patches.extend(extra_patches)
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return cmd_task_complete(args)


# ---------------------------------------------------------------------------
# TC01: SPRINT all children completed → completes cleanly
# ---------------------------------------------------------------------------

class TestSprintAllChildrenComplete:

    def test_completes_without_error(self, tmp_path, capsys):
        sprint = _make_fake_task(42, task_type="SPRINT", custom={
            "goal": "Ship feature X",
            "scoped_progress": {"completed": 2, "total": 2},
            "ideas_captured": 1,
            "learnings_curated": 0,
        })
        children = [
            _make_fake_child(10, parent_id=42, status="completed"),
            _make_fake_child(11, parent_id=42, status="completed"),
        ]
        reader = _make_reader(sprint, children, tmp_path)
        args = _make_args(42, report="manual report")

        rc = run_complete(args, reader)

        assert rc == 0
        out = capsys.readouterr().out
        assert "✅ Task #42 marked complete" in out


# ---------------------------------------------------------------------------
# TC02: SPRINT open children, no --force → blocked with error message
# ---------------------------------------------------------------------------

class TestSprintOpenChildrenBlocked:

    def test_blocked_with_child_ids_listed(self, tmp_path, capsys):
        sprint = _make_fake_task(50, task_type="SPRINT", custom={
            "goal": "G",
            "scoped_progress": {"completed": 1, "total": 3},
            "ideas_captured": 0,
            "learnings_curated": 0,
        })
        children = [
            _make_fake_child(20, parent_id=50, status="in_progress"),
            _make_fake_child(21, parent_id=50, status="completed"),
        ]
        reader = _make_reader(sprint, children, tmp_path)
        args = _make_args(50, report="done", force=False)

        rc = run_complete(args, reader)

        assert rc == 1
        out = capsys.readouterr().out
        # New scope-gate message format (post bug #1051):
        # "❌ SPRINT has N open child task(s) not in scope: #N"
        assert "open child task" in out
        assert "#20" in out
        assert "--force" in out
        # And points the user at carry-through-compaction
        assert "Carry-through-compaction" in out or "carry-through-compaction" in out.lower()


# ---------------------------------------------------------------------------
# TC03a: SPRINT open children + --force WITHOUT --justification → blocked (new gate)
# ---------------------------------------------------------------------------

class TestSprintForceRequiresJustification:

    def test_force_without_justification_blocked(self, tmp_path, capsys):
        """Bug #1051: --force on SPRINT with incomplete scope must require --justification."""
        sprint = _make_fake_task(60, task_type="SPRINT", custom={
            "goal": "G2",
            "scoped_progress": {"completed": 0, "total": 1},
            "ideas_captured": 0,
            "learnings_curated": 0,
        })
        children = [_make_fake_child(30, parent_id=60, status="pending")]
        reader = _make_reader(sprint, children, tmp_path)
        args = _make_args(60, report="forced", force=True, justification=None)

        rc = run_complete(args, reader)

        assert rc == 1, "Force-complete without --justification must hard-fail (parallel scope-gate)"
        out = capsys.readouterr().out
        assert "Force-complete bypass requires --justification" in out
        assert "§3.3.2" in out
        assert "Acceptable" in out
        assert "NOT acceptable" in out


# ---------------------------------------------------------------------------
# TC03b: SPRINT open children + --force + --justification → completes, marker prepended
# ---------------------------------------------------------------------------

class TestSprintForceWithJustificationCompletes:

    def test_completes_with_justification_and_records_marker(self, tmp_path, capsys):
        """Bug #1051: --force + --justification succeeds and prepends marker to report."""
        sprint = _make_fake_task(60, task_type="SPRINT", custom={
            "goal": "G2",
            "scoped_progress": {"completed": 0, "total": 1},
            "ideas_captured": 0,
            "learnings_curated": 0,
        })
        children = [_make_fake_child(30, parent_id=60, status="pending")]
        reader = _make_reader(sprint, children, tmp_path)
        args = _make_args(
            60, report="forced", force=True,
            justification="pinned MISSIONs intentionally cycle-spanning"
        )

        rc = run_complete(args, reader)

        assert rc == 0, "Force-complete WITH --justification must succeed"
        out = capsys.readouterr().out
        assert "✅ Task #60 marked complete" in out
        # Justification marker prepended to report (visible in completion message)
        assert "FORCE-COMPLETE JUSTIFICATION" in args.report
        assert "pinned MISSIONs" in args.report


# ---------------------------------------------------------------------------
# TC04: SPRINT auto-aggregate appears in completion_report
# ---------------------------------------------------------------------------

class TestSprintAutoAggregate:

    def test_aggregate_injected_into_report(self, tmp_path, capsys):
        sprint = _make_fake_task(70, task_type="SPRINT", custom={
            "goal": "Build dashboard",
            "scoped_progress": {"completed": 3, "total": 3},
            "ideas_captured": 2,
            "learnings_curated": 1,
        })
        reader = _make_reader(sprint, [], tmp_path)
        args = _make_args(70, report="Manual summary")

        rc = run_complete(args, reader)

        assert rc == 0
        # args.report is mutated by cmd_task_complete before MTMD write
        assert "Build dashboard" in args.report
        assert "3/3" in args.report
        assert "2 ideas" in args.report
        assert "1 learnings" in args.report


# ---------------------------------------------------------------------------
# TC05: SPRINT 💡 ideas counter prompted on stdout
# ---------------------------------------------------------------------------

class TestSprintIdeaPrompt:

    def test_idea_count_printed(self, tmp_path, capsys):
        updates = [
            _make_fake_update("💡 Idea about caching"),
            _make_fake_update("Regular note"),
            _make_fake_update("💡 Another idea"),
        ]
        sprint = _make_fake_task(80, task_type="SPRINT", custom={
            "goal": "G",
            "scoped_progress": {"completed": 1, "total": 1},
            "ideas_captured": 2,
            "learnings_curated": 0,
        }, updates=updates)
        reader = _make_reader(sprint, [], tmp_path)
        args = _make_args(80, report="done")

        rc = run_complete(args, reader)

        assert rc == 0
        out = capsys.readouterr().out
        assert "💡 2 ideas in task notes" in out
        assert "macf_tools idea create" in out


# ---------------------------------------------------------------------------
# TC06: PLAY_TIME timer not expired → warns but completes
# ---------------------------------------------------------------------------

class TestPlayTimeTimerNotExpired:

    def test_warns_but_completes(self, tmp_path, capsys):
        future_ts = int(time.time()) + 3600  # 60 min remaining
        pt = _make_fake_task(90, task_type="PLAY_TIME", custom={
            "goal": "Explore topic",
            "timer_expires_at": future_ts,
            "timer_minutes": 60,
            "mode_transitions": [{"mode": "DISCOVER"}],
            "markov_gates": [{}],
            "ideas_captured": 0,
            "learnings_curated": 0,
        })
        reader = _make_reader(pt, [], tmp_path)
        args = _make_args(90, report="done early", force=False)

        rc = run_complete(args, reader)

        assert rc == 0
        out = capsys.readouterr().out
        assert "timer hasn't expired" in out
        assert "✅ Task #90 marked complete" in out


# ---------------------------------------------------------------------------
# TC07: PLAY_TIME timer expired → completes silently
# ---------------------------------------------------------------------------

class TestPlayTimeTimerExpired:

    def test_no_warning_when_expired(self, tmp_path, capsys):
        past_ts = int(time.time()) - 60  # expired 1 min ago
        pt = _make_fake_task(91, task_type="PLAY_TIME", custom={
            "goal": "Explore more",
            "timer_expires_at": past_ts,
            "timer_minutes": 30,
            "mode_transitions": [],
            "markov_gates": [],
            "ideas_captured": 0,
            "learnings_curated": 0,
        })
        reader = _make_reader(pt, [], tmp_path)
        args = _make_args(91, report="finished", force=False)

        rc = run_complete(args, reader)

        assert rc == 0
        out = capsys.readouterr().out
        assert "timer hasn't expired" not in out
        assert "✅ Task #91 marked complete" in out


# ---------------------------------------------------------------------------
# TC08: PLAY_TIME auto-aggregate appears in completion_report
# ---------------------------------------------------------------------------

class TestPlayTimeAutoAggregate:

    def test_aggregate_injected_into_report(self, tmp_path, capsys):
        past_ts = int(time.time()) - 10
        pt = _make_fake_task(92, task_type="PLAY_TIME", custom={
            "goal": "Rapid exploration",
            "timer_expires_at": past_ts,
            "timer_minutes": 45,
            "mode_transitions": [{"mode": "DISCOVER"}, {"mode": "EXPERIMENT"}],
            "markov_gates": [{"gate": 1}, {"gate": 2}],
            "ideas_captured": 3,
            "learnings_curated": 2,
        })
        reader = _make_reader(pt, [], tmp_path)
        args = _make_args(92, report="Human summary")

        rc = run_complete(args, reader)

        assert rc == 0
        assert "Rapid exploration" in args.report
        assert "45min" in args.report
        assert "Modes used: 3" in args.report   # 2 transitions + 1
        assert "Markov gates: 2" in args.report
        assert "3 ideas" in args.report
        assert "2 learnings" in args.report
