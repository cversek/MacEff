"""Unit tests for sprint_gate helpers (Phase 4 of MISSION 1010).

Covers the pure-function helpers that the Stop hook routes to when a SPRINT
or PLAY_TIME task is in active scope.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from macf.task.sprint_gate import (
    emit_scope_nag,
    emit_chain_advance_suggestion,
    should_fire_markov_for_play_time,
    parse_play_time_custom,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id, custom):
    """Construct a minimal task-like object with .mtmd.custom for tests."""
    mtmd = SimpleNamespace(custom=custom)
    return SimpleNamespace(id=task_id, mtmd=mtmd)


# ---------------------------------------------------------------------------
# emit_scope_nag
# ---------------------------------------------------------------------------

class TestEmitScopeNag:

    def test_includes_goal_and_open_count(self):
        sprint = _make_task(100, {"goal": "Build pipeline"})
        children = [
            {"id": 101, "subject": "Phase A"},
            {"id": 102, "subject": "Phase B"},
        ]
        msg = emit_scope_nag(sprint, children)
        assert "🏃‍♂️ SPRINT in progress" in msg
        assert "Build pipeline" in msg
        assert "2 scoped task(s) remaining" in msg
        assert "#101: Phase A" in msg
        assert "#102: Phase B" in msg
        assert "macf_tools task complete" in msg

    def test_no_goal_omits_quoted_section(self):
        sprint = _make_task(100, {})
        msg = emit_scope_nag(sprint, [{"id": 101, "subject": "X"}])
        # No goal → no quoted section after the header
        assert "🏃‍♂️ SPRINT in progress" in msg
        assert ': "' not in msg.splitlines()[0]

    def test_emergency_escape_present(self):
        msg = emit_scope_nag(_make_task(1, {}), [{"id": 2, "subject": "x"}])
        assert "MANUAL_MODE" in msg


# ---------------------------------------------------------------------------
# emit_chain_advance_suggestion
# ---------------------------------------------------------------------------

class TestEmitChainAdvance:

    def test_basic_advance_message(self):
        pt = _make_task(200, {"goal": "Explore"})
        msg = emit_chain_advance_suggestion(pt, 0, ["DISCOVER", "EXPERIMENT", "BUILD"])
        assert "PLAY_TIME chain advance" in msg
        assert "DISCOVER" in msg
        assert "EXPERIMENT" in msg
        assert "Chain position: 0 → 1" in msg
        assert "of 3 steps" in msg
        assert "/maceff-experimental-self-motivation" in msg

    def test_includes_goal_when_present(self):
        pt = _make_task(200, {"goal": "Find new things"})
        msg = emit_chain_advance_suggestion(pt, 0, ["DISCOVER", "BUILD"])
        assert "Find new things" in msg

    def test_skill_map_per_mode(self):
        pt = _make_task(200, {})
        chain = ["DISCOVER", "CURATE"]
        msg = emit_chain_advance_suggestion(pt, 0, chain)
        assert "/maceff-curative-self-motivation" in msg


# ---------------------------------------------------------------------------
# should_fire_markov_for_play_time
# ---------------------------------------------------------------------------

class TestShouldFireMarkov:

    def test_chain_not_exhausted_returns_false(self):
        pt = _make_task(200, {"chain_exhausted": False})
        assert should_fire_markov_for_play_time(pt) is False

    def test_no_task_returns_false(self):
        assert should_fire_markov_for_play_time(None) is False

    def test_no_mtmd_returns_false(self):
        bad = SimpleNamespace(id=1, mtmd=None)
        assert should_fire_markov_for_play_time(bad) is False

    def test_chain_exhausted_with_active_timer_returns_true(self):
        pt = _make_task(200, {"chain_exhausted": True})
        with patch("macf.task.sprint_gate.get_active_timer",
                   return_value={"active": True, "remaining_min": 5}, create=True):
            # The function imports get_active_timer locally — use a different patch target
            with patch("macf.task.scope.get_active_timer",
                       return_value={"active": True, "remaining_min": 5}):
                assert should_fire_markov_for_play_time(pt) is True

    def test_chain_exhausted_no_timer_returns_false(self):
        pt = _make_task(200, {"chain_exhausted": True})
        with patch("macf.task.scope.get_active_timer", return_value={"active": False}):
            assert should_fire_markov_for_play_time(pt) is False


# ---------------------------------------------------------------------------
# parse_play_time_custom
# ---------------------------------------------------------------------------

class TestParsePlayTimeCustom:

    def test_round_trip_valid_dict(self):
        custom = {
            "goal": "test",
            "timer_minutes": 30,
            "timer_started_at": 1000,
            "timer_expires_at": 1000 + 30 * 60,
            "predetermined_chain": ["DISCOVER"],
            "chain_position": 0,
            "chain_exhausted": False,
            "initial_work_mode": "DISCOVER",
            "current_work_mode": "DISCOVER",
        }
        pt = _make_task(200, custom)
        result = parse_play_time_custom(pt)
        assert result is not None
        assert result.goal == "test"
        assert result.timer_minutes == 30

    def test_none_task_returns_none(self):
        assert parse_play_time_custom(None) is None

    def test_invalid_dict_returns_none(self):
        # Missing required fields → ValidationError → None
        pt = _make_task(200, {"goal": "x"})  # incomplete
        assert parse_play_time_custom(pt) is None
