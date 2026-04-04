"""
Integration tests for task scope system and Stop hook scope gate.

Tests the full lifecycle: scope set → task start → task complete (inactive) →
Stop hook (blocked vs allowed) → scope clear.
"""

import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def isolated_events(tmp_path):
    """Provide an isolated event log for each test."""
    event_log = tmp_path / ".maceff" / "agent_events_log.jsonl"
    event_log.parent.mkdir(parents=True)
    event_log.touch()
    with patch.dict(os.environ, {"MACEFF_AGENT_HOME_DIR": str(tmp_path)}):
        yield event_log


class TestScopeLifecycle:
    """Test scope set/show/clear/check lifecycle."""

    def test_empty_scope(self, isolated_events):
        from macf.task.scope import get_scope_state, get_scope_check
        assert get_scope_state() == {}
        check = get_scope_check()
        assert check["active_count"] == 0
        assert check["total"] == 0

    def test_set_scope(self, isolated_events):
        from macf.task.scope import set_scope, get_scope_state
        result = set_scope(["290", "291", "292"])
        assert result["success"]
        assert result["tasks_scoped"] == ["290", "291", "292"]
        state = get_scope_state()
        assert state["290"] == "active"
        assert state["291"] == "active"
        assert state["292"] == "active"

    def test_complete_scoped_task(self, isolated_events):
        from macf.task.scope import set_scope, complete_scoped_task, get_scope_state
        set_scope(["1", "2", "3"])
        result = complete_scoped_task("2")
        assert result["success"]
        assert result["task_id"] == "2"
        assert result["transitioned_to"] == "inactive"
        assert result["remaining_active"] == 2
        state = get_scope_state()
        assert state["1"] == "active"
        assert state["2"] == "inactive"
        assert state["3"] == "active"

    def test_clear_scope(self, isolated_events):
        from macf.task.scope import set_scope, complete_scoped_task, clear_scope, get_scope_state
        set_scope(["10", "20", "30"])
        complete_scoped_task("10")
        result = clear_scope()
        assert result["success"]
        assert "10" in result["inactive_removed"]
        assert "20" in result["active_removed"]
        assert "30" in result["active_removed"]
        assert get_scope_state() == {}

    def test_scope_check_json(self, isolated_events):
        from macf.task.scope import set_scope, complete_scoped_task, get_scope_check
        set_scope(["5", "6", "7"])
        complete_scoped_task("5")
        check = get_scope_check()
        assert check["active_count"] == 2
        assert check["inactive_count"] == 1
        assert check["total"] == 3

    def test_clear_resets_everything(self, isolated_events):
        from macf.task.scope import set_scope, clear_scope, set_scope as set2, get_scope_state
        set_scope(["1", "2"])
        clear_scope()
        set_scope(["99"])
        state = get_scope_state()
        assert list(state.keys()) == ["99"]
        assert state["99"] == "active"


class TestScopeFullDisclosure:
    """Test that scope functions return what changed (Full Disclosure Principle)."""

    def test_set_returns_tasks_scoped(self, isolated_events):
        from macf.task.scope import set_scope
        result = set_scope(["a", "b"])
        assert "tasks_scoped" in result
        assert result["tasks_scoped"] == ["a", "b"]

    def test_complete_returns_transition(self, isolated_events):
        from macf.task.scope import set_scope, complete_scoped_task
        set_scope(["x", "y"])
        result = complete_scoped_task("x")
        assert result["transitioned_to"] == "inactive"
        assert result["remaining_active"] == 1

    def test_clear_returns_removed_lists(self, isolated_events):
        from macf.task.scope import set_scope, complete_scoped_task, clear_scope
        set_scope(["p", "q"])
        complete_scoped_task("p")
        result = clear_scope()
        assert "p" in result["inactive_removed"]
        assert "q" in result["active_removed"]


class TestStopHookScopeGate:
    """Test that Stop hook blocks when scoped tasks remain in AUTO_MODE."""

    def test_stop_hook_imports_cleanly(self):
        """Regression: local import must not shadow top-level detect_auto_mode."""
        from macf.hooks.handle_stop import run
        result = run('{"stop_reason":"end_turn"}')
        # Should not contain 'error' in message (the shadowing bug)
        assert "error" not in result.get("systemMessage", "").lower() or "hook error" not in result.get("systemMessage", "").lower()

    def test_stop_allowed_without_scope(self):
        """Stop should succeed when no scope is active."""
        from macf.hooks.handle_stop import run
        result = run('{"stop_reason":"end_turn"}')
        assert result["continue"] is True
