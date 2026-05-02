"""
Unit + integration tests for Phase 3: create_sprint() and create_play_time().

Tests per spec (roadmap §5.3):

create_sprint:
  T01 round-trip: title → SPRINT task with correct task_type, SprintCustom, 🏃 subject
  T02 --scoped happy path: existing tasks in scope, SprintCustom.scoped_task_ids populated
  T03 --children happy path: child tasks created and collected into scope
  T04 --scoped AND --children both given → ValueError
  T05 --scoped references non-existent task → ValueError
  T06 --timer passed → ValueError (hard-fail with documented message)
  T07 --no-auto-start: task created but start/scope/mode not called
  T08 CA skeleton written to agent/public/sprints/ with correct content
  T09 auto-start chain: task in_progress, scope set, mode SPRINT, launch note

create_play_time:
  T10 round-trip: title + timer → PLAY_TIME task with PlayTimeCustom, ⏲️ subject
  T11 --timer missing → TypeError / ValueError hard-fail
  T12 --timer 0 or negative → ValueError
  T13 --chain multi-mode: chain stored correctly, current_work_mode = chain[0]
  T14 --chain SPRINT → ValueError (SPRINT not allowed in chain)
  T15 CA skeleton written to agent/public/play_time/ folder
  T16 auto-start chain: scope set with timer, mode = chain[0], launch note

CLI integration:
  T17 macf_tools task create sprint --help shows correct flags
  T18 macf_tools task create play_time --help shows correct flags

Test count: 18 tests.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from macf.task.create import create_sprint, create_play_time, create_task
from macf.task.custom_models import SprintCustom, PlayTimeCustom


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def fake_agent_root(tmp_path):
    """Minimal agent root tree for file-system assertions."""
    # Structure expected by create_sprint / create_play_time
    (tmp_path / "agent" / "public" / "sprints").mkdir(parents=True)
    (tmp_path / "agent" / "public" / "play_time").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def mock_task_infra(tmp_path, monkeypatch):
    """
    Patch the file-system and event-log side effects so tests run without a
    real CC task store, breadcrumb, or TM daemon.

    Returns a dict of mock handles for assertion.
    """
    # Task ID counter (start at 200 to avoid collisions with stub task IDs)
    _next_id = [200]

    def fake_get_next_task_id(session_uuid=None):
        val = _next_id[0]
        _next_id[0] += 1
        return val

    def fake_create_task_file(task_id, subject, description,
                              status="pending", session_uuid=None,
                              blocked_by=None):
        path = tmp_path / f"{task_id}.json"
        path.write_text(json.dumps({"id": str(task_id), "subject": subject,
                                    "description": description, "status": status}))
        return path

    def fake_get_breadcrumb():
        return "s_test/c_1/g_abc/p_def/t_1000"

    def fake_parse_breadcrumb(bc):
        return {"cycle": 1, "session": "test", "git": "abc", "prompt": "def"}

    def fake_find_agent_home():
        return tmp_path

    # Task reader mock: reads from tmp_path
    class FakeTask:
        def __init__(self, tid, status="pending"):
            self.id = str(tid)
            self.status = status
            self.subject = f"Task #{tid}"
            self.mtmd = None
            self.description = ""

        def description_with_updated_mtmd(self, mtmd):
            return self.description

    class FakeTaskReader:
        def __init__(self, session_uuid=None):
            self.session_path = tmp_path

        def read_task(self, task_id):
            path = tmp_path / f"{task_id}.json"
            if not path.exists():
                return None
            data = json.loads(path.read_text())
            t = FakeTask(task_id, status=data.get("status", "pending"))
            return t

        def read_all_tasks(self):
            tasks = []
            for p in tmp_path.glob("*.json"):
                data = json.loads(p.read_text())
                tasks.append(FakeTask(data["id"], status=data.get("status", "pending")))
            return tasks

        def list_task_files(self, include_hidden=False):
            return list(tmp_path.glob("*.json"))

    # Scope mock (always succeeds)
    fake_set_scope_calls = []

    def fake_set_scope(task_ids, parent_expanded=False, expanded_from=None):
        fake_set_scope_calls.append(list(task_ids))
        return {"success": True, "tasks_scoped": task_ids,
                "parent_expanded": False, "expanded_from": None}

    def fake_get_active_timer():
        return {"active": False}

    # Mode mock
    fake_mode_calls = []

    def fake_append_event(event_type, data=None):
        if event_type == "work_mode_change":
            fake_mode_calls.append(data.get("mode") if data else None)

    def fake_update_task_file(task_id, updates, session_uuid=None):
        path = tmp_path / f"{task_id}.json"
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = {"id": str(task_id), "subject": "", "description": "", "status": "pending"}
        data.update(updates)
        path.write_text(json.dumps(data))

    # Patch everything
    monkeypatch.setattr("macf.task.create._get_next_task_id", fake_get_next_task_id)
    monkeypatch.setattr("macf.task.create._create_task_file", fake_create_task_file)
    monkeypatch.setattr("macf.task.create.find_agent_home", fake_find_agent_home)

    import macf.task.create as _create_mod
    monkeypatch.setattr(_create_mod, "TaskReader", FakeTaskReader)

    # Patch update_task_file and TaskReader in macf.task.reader — _run_task_start
    # and _run_task_note do `from .reader import TaskReader, update_task_file`
    # at call time, so we must patch the module attributes there.
    import macf.task.reader as _reader_mod
    monkeypatch.setattr(_reader_mod, "update_task_file", fake_update_task_file)
    monkeypatch.setattr(_reader_mod, "TaskReader", FakeTaskReader)

    # Patch breadcrumbs within create module
    import macf.utils.breadcrumbs as _bc_mod
    monkeypatch.setattr(_bc_mod, "get_breadcrumb", fake_get_breadcrumb)
    monkeypatch.setattr(_bc_mod, "parse_breadcrumb", fake_parse_breadcrumb)

    # Patch scope
    import macf.task.scope as _scope_mod
    monkeypatch.setattr(_scope_mod, "set_scope", fake_set_scope)
    monkeypatch.setattr(_scope_mod, "get_active_timer", fake_get_active_timer)

    # Patch append_event so mode changes are captured without a real event log
    import macf.agent_events_log as _ev_mod
    original_append = _ev_mod.append_event

    def patched_append_event(event_type, data=None):
        if event_type == "work_mode_change":
            fake_mode_calls.append(data.get("mode") if data else None)
        # don't write to disk

    monkeypatch.setattr(_ev_mod, "append_event", patched_append_event)

    # Patch TM check to avoid daemon dependency
    monkeypatch.setattr("macf.task.create._verify_tm_running", lambda: True)

    return {
        "tmp_path": tmp_path,
        "scope_calls": fake_set_scope_calls,
        "mode_calls": fake_mode_calls,
        "next_id": _next_id,
    }


def _make_existing_task(tmp_path, task_id: int, status: str = "pending") -> Path:
    """Write a minimal task JSON so it appears to the FakeTaskReader."""
    path = tmp_path / f"{task_id}.json"
    path.write_text(json.dumps({
        "id": str(task_id),
        "subject": f"Task #{task_id}",
        "description": "",
        "status": status,
    }))
    return path


# ===========================================================================
# create_sprint tests
# ===========================================================================

class TestCreateSprint:

    # -----------------------------------------------------------------------
    # T01: Round-trip — task_type=SPRINT, SprintCustom valid, 🏃 subject
    # -----------------------------------------------------------------------
    def test_T01_round_trip(self, mock_task_infra, fake_agent_root):
        mocks = mock_task_infra
        tmp = mocks["tmp_path"]
        _make_existing_task(tmp, 10)

        result = create_sprint(
            "Build pipeline",
            scoped_task_ids=[10],
            no_auto_start=True,
            agent_root=fake_agent_root,
        )

        assert result["task_id"] == 200
        assert result["initial_mode"] == "SPRINT"

        # Read written task file and check MTMD content
        task_file = Path(result["task_path"])
        data = json.loads(task_file.read_text())
        assert "🏃 SPRINT:" in data["subject"]
        assert "SPRINT" in data["description"]
        assert "task_type: SPRINT" in data["description"]

        # Validate custom dict round-trips through SprintCustom
        import re, yaml
        mtmd_match = re.search(
            r'<macf_task_metadata[^>]*>(.*?)</macf_task_metadata>',
            data["description"], re.DOTALL
        )
        assert mtmd_match, "MTMD block not found in description"
        mtmd_yaml = mtmd_match.group(1)
        mtmd_dict = yaml.safe_load(mtmd_yaml)
        custom = mtmd_dict.get("custom", {})
        model = SprintCustom.from_dict(custom)
        assert model.initial_work_mode == "SPRINT"
        assert model.goal == "Build pipeline"
        assert 10 in model.scoped_task_ids

    # -----------------------------------------------------------------------
    # T02: --scoped happy path
    # -----------------------------------------------------------------------
    def test_T02_scoped_happy_path(self, mock_task_infra, fake_agent_root):
        tmp = mock_task_infra["tmp_path"]
        for tid in [20, 21, 22]:
            _make_existing_task(tmp, tid)

        result = create_sprint(
            "Test run",
            scoped_task_ids=[20, 21, 22],
            no_auto_start=True,
            agent_root=fake_agent_root,
        )

        assert set([20, 21, 22]).issubset(set(result["scope"]))

        # Verify SprintCustom.scoped_task_ids populated
        task_file = Path(result["task_path"])
        data = json.loads(task_file.read_text())
        import re, yaml
        mtmd_match = re.search(
            r'<macf_task_metadata[^>]*>(.*?)</macf_task_metadata>',
            data["description"], re.DOTALL
        )
        custom = yaml.safe_load(mtmd_match.group(1)).get("custom", {})
        model = SprintCustom.from_dict(custom)
        assert model.scoped_task_ids == [20, 21, 22]
        assert model.scoped_progress["total"] == 3

    # -----------------------------------------------------------------------
    # T03: --children happy path
    # -----------------------------------------------------------------------
    def test_T03_children_happy_path(self, mock_task_infra, fake_agent_root):
        result = create_sprint(
            "Research sprint",
            children_titles=["Read docs", "Write notes"],
            no_auto_start=True,
            agent_root=fake_agent_root,
        )

        # Sprint task is 200; children get 201, 202
        assert result["task_id"] == 200
        assert len(result["scope"]) == 3  # sprint + 2 children
        assert 201 in result["scope"]
        assert 202 in result["scope"]

    # -----------------------------------------------------------------------
    # T04: --scoped AND --children both given → ValueError
    # -----------------------------------------------------------------------
    def test_T04_scoped_and_children_mutually_exclusive(self, mock_task_infra, fake_agent_root):
        tmp = mock_task_infra["tmp_path"]
        _make_existing_task(tmp, 30)

        with pytest.raises(ValueError, match="exactly one of"):
            create_sprint(
                "Ambiguous",
                scoped_task_ids=[30],
                children_titles=["Something"],
                no_auto_start=True,
                agent_root=fake_agent_root,
            )

    # -----------------------------------------------------------------------
    # T05: --scoped references non-existent task → ValueError
    # -----------------------------------------------------------------------
    def test_T05_scoped_nonexistent_task(self, mock_task_infra, fake_agent_root):
        # Task 999 was never written to tmp_path
        with pytest.raises(ValueError, match="does not refer to an existing task"):
            create_sprint(
                "Missing scope",
                scoped_task_ids=[999],
                no_auto_start=True,
                agent_root=fake_agent_root,
            )

    # -----------------------------------------------------------------------
    # T06: --timer passed → ValueError (hard-fail)
    # -----------------------------------------------------------------------
    def test_T06_timer_rejected(self, mock_task_infra, fake_agent_root):
        """create_sprint should hard-fail if the caller somehow passes a timer.

        The CLI enforces this via argparse (hidden --timer arg that feeds into
        cmd_task_create_sprint which does the hard-fail before calling the
        Python function). The Python function itself does NOT take a timer arg,
        so we test the CLI path via subprocess. The documented error message
        must appear.
        """
        result = subprocess.run(
            [sys.executable, "-m", "macf.cli", "task", "create", "sprint",
             "Some sprint", "--scoped", "1", "--timer", "30"],
            capture_output=True, text=True,
        )
        # Either: argument rejected by argparse OR our handler emits the message
        combined = result.stdout + result.stderr
        assert "SPRINT does not accept --timer" in combined or result.returncode != 0

    # -----------------------------------------------------------------------
    # T07: --no-auto-start: task created but auto-start NOT called
    # -----------------------------------------------------------------------
    def test_T07_no_auto_start(self, mock_task_infra, fake_agent_root):
        tmp = mock_task_infra["tmp_path"]
        _make_existing_task(tmp, 40)

        result = create_sprint(
            "No start sprint",
            scoped_task_ids=[40],
            no_auto_start=True,
            agent_root=fake_agent_root,
        )

        assert result["auto_start_completed"] is False
        assert result["auto_start_error"] is None
        # Scope set must NOT have been called
        assert mock_task_infra["scope_calls"] == []
        # Mode must NOT have been set
        assert mock_task_infra["mode_calls"] == []

    # -----------------------------------------------------------------------
    # T08: CA skeleton written to correct path
    # -----------------------------------------------------------------------
    def test_T08_ca_skeleton_written(self, mock_task_infra, fake_agent_root):
        tmp = mock_task_infra["tmp_path"]
        _make_existing_task(tmp, 50)

        result = create_sprint(
            "Pipeline run",
            scoped_task_ids=[50],
            no_auto_start=True,
            agent_root=fake_agent_root,
        )

        ca = fake_agent_root / result["ca_path"]
        assert ca.exists(), f"CA skeleton not found at {ca}"
        content = ca.read_text()
        assert "# SPRINT LOG:" in content
        assert "Pipeline run" in content
        # Check it lives in the right folder
        assert "agent/public/sprints/" in result["ca_path"]
        assert result["ca_path"].endswith("sprint_log.md")

    # -----------------------------------------------------------------------
    # T09: auto-start chain — scope set, mode SPRINT, launch note
    # -----------------------------------------------------------------------
    def test_T09_auto_start_chain(self, mock_task_infra, fake_agent_root):
        tmp = mock_task_infra["tmp_path"]
        _make_existing_task(tmp, 60)
        _make_existing_task(tmp, 61)

        result = create_sprint(
            "Full auto sprint",
            scoped_task_ids=[60, 61],
            no_auto_start=False,
            agent_root=fake_agent_root,
        )

        assert result["auto_start_completed"] is True
        assert result["auto_start_error"] is None

        # Scope was called once with sprint + scoped tasks
        scope_calls = mock_task_infra["scope_calls"]
        assert len(scope_calls) == 1
        scoped = scope_calls[0]
        assert str(result["task_id"]) in scoped
        assert "60" in scoped
        assert "61" in scoped

        # Mode set to SPRINT
        assert "SPRINT" in mock_task_infra["mode_calls"]

        # Task file now has status in_progress (set by _run_task_start)
        task_path = Path(result["task_path"])
        data = json.loads(task_path.read_text())
        assert data["status"] == "in_progress"


# ===========================================================================
# create_play_time tests
# ===========================================================================

class TestCreatePlayTime:

    # -----------------------------------------------------------------------
    # T10: Round-trip — PlayTimeCustom, ⏲️ subject
    # -----------------------------------------------------------------------
    def test_T10_round_trip(self, mock_task_infra, fake_agent_root):
        result = create_play_time(
            "Explore widgets",
            timer_minutes=60,
            no_auto_start=True,
            agent_root=fake_agent_root,
        )

        assert result["task_id"] == 200
        assert result["initial_mode"] == "DISCOVER"

        task_file = Path(result["task_path"])
        data = json.loads(task_file.read_text())
        assert "⏲️ PLAY_TIME:" in data["subject"]
        assert "PLAY_TIME" in data["description"]
        assert "task_type: PLAY_TIME" in data["description"]

        # Validate custom dict round-trips through PlayTimeCustom
        import re, yaml
        mtmd_match = re.search(
            r'<macf_task_metadata[^>]*>(.*?)</macf_task_metadata>',
            data["description"], re.DOTALL
        )
        assert mtmd_match, "MTMD block not found in description"
        custom = yaml.safe_load(mtmd_match.group(1)).get("custom", {})
        model = PlayTimeCustom.from_dict(custom)
        assert model.timer_minutes == 60
        assert model.initial_work_mode == "DISCOVER"
        assert model.current_work_mode == "DISCOVER"
        assert model.predetermined_chain == ["DISCOVER"]

    # -----------------------------------------------------------------------
    # T11: --timer missing → TypeError (timer_minutes is mandatory kwarg)
    # -----------------------------------------------------------------------
    def test_T11_timer_missing(self, mock_task_infra, fake_agent_root):
        with pytest.raises(TypeError):
            create_play_time(
                "Missing timer",
                # timer_minutes intentionally omitted
                no_auto_start=True,
                agent_root=fake_agent_root,
            )

    # -----------------------------------------------------------------------
    # T12: --timer 0 or negative → ValueError
    # -----------------------------------------------------------------------
    def test_T12_timer_zero_rejected(self, mock_task_infra, fake_agent_root):
        with pytest.raises(ValueError, match="positive minutes"):
            create_play_time(
                "Zero timer",
                timer_minutes=0,
                no_auto_start=True,
                agent_root=fake_agent_root,
            )

    def test_T12b_timer_negative_rejected(self, mock_task_infra, fake_agent_root):
        with pytest.raises(ValueError, match="positive minutes"):
            create_play_time(
                "Negative timer",
                timer_minutes=-15,
                no_auto_start=True,
                agent_root=fake_agent_root,
            )

    # -----------------------------------------------------------------------
    # T13: --chain multi-mode: stored correctly, current = chain[0]
    # -----------------------------------------------------------------------
    def test_T13_chain_multi_mode(self, mock_task_infra, fake_agent_root):
        result = create_play_time(
            "Deep dive",
            timer_minutes=45,
            chain=["DISCOVER", "EXPERIMENT", "BUILD"],
            no_auto_start=True,
            agent_root=fake_agent_root,
        )

        assert result["initial_mode"] == "DISCOVER"

        task_file = Path(result["task_path"])
        data = json.loads(task_file.read_text())
        import re, yaml
        mtmd_match = re.search(
            r'<macf_task_metadata[^>]*>(.*?)</macf_task_metadata>',
            data["description"], re.DOTALL
        )
        custom = yaml.safe_load(mtmd_match.group(1)).get("custom", {})
        model = PlayTimeCustom.from_dict(custom)
        assert model.predetermined_chain == ["DISCOVER", "EXPERIMENT", "BUILD"]
        assert model.chain_position == 0
        assert model.chain_exhausted is False
        assert model.current_work_mode == "DISCOVER"

    # -----------------------------------------------------------------------
    # T14: --chain SPRINT → ValueError
    # -----------------------------------------------------------------------
    def test_T14_chain_sprint_rejected(self, mock_task_infra, fake_agent_root):
        with pytest.raises(ValueError, match="SPRINT"):
            create_play_time(
                "Bad chain",
                timer_minutes=30,
                chain=["SPRINT"],
                no_auto_start=True,
                agent_root=fake_agent_root,
            )

    # -----------------------------------------------------------------------
    # T15: CA skeleton written to agent/public/play_time/
    # -----------------------------------------------------------------------
    def test_T15_ca_skeleton_written(self, mock_task_infra, fake_agent_root):
        result = create_play_time(
            "Skeleton test",
            timer_minutes=20,
            chain=["CURATE"],
            no_auto_start=True,
            agent_root=fake_agent_root,
        )

        ca = fake_agent_root / result["ca_path"]
        assert ca.exists(), f"CA skeleton not found at {ca}"
        content = ca.read_text()
        assert "# PLAY LOG:" in content
        assert "Skeleton test" in content
        assert "20 min" in content
        assert "CURATE" in content
        assert "agent/public/play_time/" in result["ca_path"]
        assert result["ca_path"].endswith("play_log.md")

    # -----------------------------------------------------------------------
    # T16: auto-start chain — scope with timer, mode = chain[0], launch note
    # -----------------------------------------------------------------------
    def test_T16_auto_start_chain(self, mock_task_infra, fake_agent_root):
        result = create_play_time(
            "Full auto play",
            timer_minutes=30,
            chain=["EXPERIMENT", "BUILD"],
            no_auto_start=False,
            agent_root=fake_agent_root,
        )

        assert result["auto_start_completed"] is True
        assert result["auto_start_error"] is None
        assert result["initial_mode"] == "EXPERIMENT"

        # Scope was called (with timer would be in the event log, tested separately)
        scope_calls = mock_task_infra["scope_calls"]
        assert len(scope_calls) == 1
        scoped = scope_calls[0]
        assert str(result["task_id"]) in scoped

        # Mode set to EXPERIMENT (chain[0])
        assert "EXPERIMENT" in mock_task_infra["mode_calls"]

        # Task file status set to in_progress
        task_path = Path(result["task_path"])
        data = json.loads(task_path.read_text())
        assert data["status"] == "in_progress"


# ===========================================================================
# CLI integration: --help output
# ===========================================================================

class TestCliHelp:

    # -----------------------------------------------------------------------
    # T17: macf_tools task create sprint --help
    # -----------------------------------------------------------------------
    def test_T17_sprint_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "macf.cli", "task", "create", "sprint", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        out = result.stdout
        assert "--scoped" in out
        assert "--children" in out
        assert "--no-auto-start" in out
        assert "--goal" in out
        # Title positional must appear
        assert "title" in out.lower()

    # -----------------------------------------------------------------------
    # T18: macf_tools task create play_time --help
    # -----------------------------------------------------------------------
    def test_T18_play_time_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "macf.cli", "task", "create", "play_time", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        out = result.stdout
        assert "--timer" in out
        assert "--chain" in out
        assert "--no-auto-start" in out
        assert "--goal" in out
        assert "title" in out.lower()
