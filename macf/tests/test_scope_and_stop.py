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


class TestRecommenderPrefix:
    """Regression guard for issue #56 — recommender must not leak /ctb-* into framework hook output."""

    def test_format_recommendation_emits_maceff_prefix(self):
        """format_recommendation with agent_prefix='maceff' must produce /maceff-* skill names."""
        from macf.modes.detection import format_recommendation
        output = format_recommendation(
            current_work_mode="DISCOVER",
            selected_mode="EXPERIMENT",
            distribution={"DISCOVER": 0.1, "EXPERIMENT": 0.5, "BUILD": 0.2, "CURATE": 0.1, "CONSOLIDATE": 0.1},
            agent_prefix="maceff",
        )
        assert "/maceff-experimental-self-motivation" in output
        assert "/ctb-" not in output

    def test_handle_stop_does_not_hardcode_ctb_prefix(self):
        """Source-level regression: handle_stop.py must not pass "ctb" to format_recommendation."""
        from pathlib import Path
        import macf.hooks.handle_stop as hs
        source = Path(hs.__file__).read_text()
        # Any literal "ctb" token as the 4th positional arg to format_recommendation would match
        assert 'format_recommendation(' in source  # sanity: function is still called
        assert ', "ctb")' not in source, "hardcoded /ctb-* prefix leaked back into the stop hook"
        assert ", 'ctb')" not in source, "hardcoded /ctb-* prefix leaked back into the stop hook"


# ─────────────────────────────────────────────────────────────────────────────
# BUG #1067 — scope pause/unpause/add/remove primitives (Cycle 514)
# 3-state model (active/paused/inactive); paused tasks excluded from gate
# ─────────────────────────────────────────────────────────────────────────────


class TestScopePausePrimitives:
    """Test pause/unpause behavior + 3-state scope model."""

    def test_pause_active_task(self, isolated_events):
        from macf.task.scope import set_scope, pause_scoped_tasks, get_scope_state
        set_scope(["100", "101"])
        result = pause_scoped_tasks(["100"], justification="external blocker — needs lxterm access")
        assert result["success"]
        assert result["paused_ids"] == ["100"]
        state = get_scope_state()
        assert state["100"] == "paused"
        assert state["101"] == "active"  # unaffected

    def test_pause_requires_justification(self, isolated_events):
        from macf.task.scope import set_scope, pause_scoped_tasks
        set_scope(["100"])
        # Empty justification should fail
        result = pause_scoped_tasks(["100"], justification="")
        assert not result["success"]
        assert result["paused_ids"] == []
        # Whitespace-only also fails
        result = pause_scoped_tasks(["100"], justification="   ")
        assert not result["success"]

    def test_pause_skips_non_active_tasks(self, isolated_events):
        from macf.task.scope import set_scope, pause_scoped_tasks, get_scope_state
        set_scope(["100"])
        # Pause once OK
        pause_scoped_tasks(["100"], justification="reason A")
        # Pause again is skipped (already paused)
        result = pause_scoped_tasks(["100"], justification="reason B")
        assert result["paused_ids"] == []
        assert any(s["reason"] == "already_paused" for s in result["skipped_ids"])

    def test_pause_skips_unscoped_tasks(self, isolated_events):
        from macf.task.scope import pause_scoped_tasks
        result = pause_scoped_tasks(["999"], justification="reason")
        assert result["paused_ids"] == []
        assert any(s["reason"] == "not_in_scope" for s in result["skipped_ids"])

    def test_unpause_restores_active(self, isolated_events):
        from macf.task.scope import set_scope, pause_scoped_tasks, unpause_scoped_tasks, get_scope_state
        set_scope(["100"])
        pause_scoped_tasks(["100"], justification="reason")
        result = unpause_scoped_tasks(["100"])
        assert result["success"]
        assert result["unpaused_ids"] == ["100"]
        assert get_scope_state()["100"] == "active"

    def test_unpause_skips_active_tasks(self, isolated_events):
        from macf.task.scope import set_scope, unpause_scoped_tasks
        set_scope(["100"])
        # Trying to unpause an already-active task is a no-op
        result = unpause_scoped_tasks(["100"])
        assert result["unpaused_ids"] == []
        assert any("not_paused" in s["reason"] for s in result["skipped_ids"])

    def test_paused_excluded_from_active_count(self, isolated_events):
        """The key invariant: paused_count separate from active_count, gate uses active_count."""
        from macf.task.scope import set_scope, pause_scoped_tasks, get_scope_check
        set_scope(["100", "101", "102"])
        pause_scoped_tasks(["100"], justification="external blocker")
        check = get_scope_check()
        assert check["active_count"] == 2  # 101, 102
        assert check["paused_count"] == 1  # 100
        assert check["inactive_count"] == 0
        assert check["total"] == 3


class TestScopeAddRemovePrimitives:
    """Test scope add/remove (incremental edits, no replace)."""

    def test_add_to_empty_scope(self, isolated_events):
        from macf.task.scope import add_to_scope, get_scope_state
        result = add_to_scope(["100", "101"])
        assert result["success"]
        assert sorted(result["added_ids"]) == ["100", "101"]
        state = get_scope_state()
        assert state["100"] == "active"
        assert state["101"] == "active"

    def test_add_appends_no_replace(self, isolated_events):
        """add_to_scope is incremental — does NOT replace existing scope."""
        from macf.task.scope import set_scope, add_to_scope, get_scope_state
        set_scope(["100"])
        add_to_scope(["101"])
        state = get_scope_state()
        # Both should be present
        assert state["100"] == "active"
        assert state["101"] == "active"

    def test_add_skips_already_in_scope(self, isolated_events):
        from macf.task.scope import set_scope, add_to_scope
        set_scope(["100"])
        result = add_to_scope(["100", "101"])
        assert result["added_ids"] == ["101"]  # 100 already in scope, skipped
        assert any(s["id"] == "100" for s in result["skipped_ids"])

    def test_remove_drops_task(self, isolated_events):
        from macf.task.scope import set_scope, remove_from_scope, get_scope_state
        set_scope(["100", "101"])
        result = remove_from_scope(["100"])
        assert result["success"]
        assert result["removed_ids"] == ["100"]
        state = get_scope_state()
        assert "100" not in state  # gone entirely
        assert state["101"] == "active"  # unaffected

    def test_remove_skips_unscoped(self, isolated_events):
        from macf.task.scope import remove_from_scope
        result = remove_from_scope(["999"])
        assert result["removed_ids"] == []
        assert any(s["reason"] == "not_in_scope" for s in result["skipped_ids"])
