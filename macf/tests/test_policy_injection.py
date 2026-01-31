"""
Tests for policy injection event infrastructure.

Tests the event-based state tracking for policy injection:
- policy_injection_activated events
- policy_injection_cleared events
- policy_injections_cleared_all events
- get_active_policy_injections_from_events() query function
"""

import pytest
from macf.agent_events_log import append_event, set_log_path
from macf.event_queries import get_active_policy_injections_from_events


@pytest.fixture
def isolated_event_log(tmp_path):
    """Provide isolated event log for each test."""
    log_path = tmp_path / "test_events.jsonl"
    set_log_path(log_path)
    yield log_path
    set_log_path(None)  # Reset to default


class TestPolicyInjectionEvents:
    """Test policy injection event emission and query."""

    def test_no_injections_returns_empty(self, isolated_event_log):
        """Empty event log returns empty injection list."""
        result = get_active_policy_injections_from_events()
        assert result == []

    def test_single_activation(self, isolated_event_log):
        """Single activation returns that policy."""
        append_event("policy_injection_activated", {
            "policy_name": "task_management",
            "policy_path": "/path/to/task_management.md"
        })

        result = get_active_policy_injections_from_events()

        assert len(result) == 1
        assert result[0]["policy_name"] == "task_management"
        assert result[0]["policy_path"] == "/path/to/task_management.md"

    def test_multiple_activations(self, isolated_event_log):
        """Multiple different policies can be active simultaneously."""
        append_event("policy_injection_activated", {
            "policy_name": "task_management",
            "policy_path": "/path/to/task_management.md"
        })
        append_event("policy_injection_activated", {
            "policy_name": "roadmaps",
            "policy_path": "/path/to/roadmaps.md"
        })

        result = get_active_policy_injections_from_events()

        assert len(result) == 2
        names = {r["policy_name"] for r in result}
        assert names == {"task_management", "roadmaps"}

    def test_idempotent_activation(self, isolated_event_log):
        """Activating same policy twice doesn't duplicate."""
        append_event("policy_injection_activated", {
            "policy_name": "task_management",
            "policy_path": "/path/v1.md"
        })
        append_event("policy_injection_activated", {
            "policy_name": "task_management",
            "policy_path": "/path/v2.md"
        })

        result = get_active_policy_injections_from_events()

        assert len(result) == 1
        assert result[0]["policy_name"] == "task_management"
        # Most recent path wins (reverse scan finds v2 first)
        assert result[0]["policy_path"] == "/path/v2.md"

    def test_clear_specific_injection(self, isolated_event_log):
        """Clearing specific policy removes only that one."""
        append_event("policy_injection_activated", {
            "policy_name": "task_management",
            "policy_path": "/path/to/task_management.md"
        })
        append_event("policy_injection_activated", {
            "policy_name": "roadmaps",
            "policy_path": "/path/to/roadmaps.md"
        })
        append_event("policy_injection_cleared", {
            "policy_name": "task_management"
        })

        result = get_active_policy_injections_from_events()

        assert len(result) == 1
        assert result[0]["policy_name"] == "roadmaps"

    def test_clear_all_injections(self, isolated_event_log):
        """Clear all removes all active injections."""
        append_event("policy_injection_activated", {
            "policy_name": "task_management",
            "policy_path": "/path/to/task_management.md"
        })
        append_event("policy_injection_activated", {
            "policy_name": "roadmaps",
            "policy_path": "/path/to/roadmaps.md"
        })
        append_event("policy_injections_cleared_all", {})

        result = get_active_policy_injections_from_events()

        assert result == []

    def test_reactivate_after_clear(self, isolated_event_log):
        """Can reactivate policy after clearing."""
        append_event("policy_injection_activated", {
            "policy_name": "task_management",
            "policy_path": "/path/v1.md"
        })
        append_event("policy_injection_cleared", {
            "policy_name": "task_management"
        })
        append_event("policy_injection_activated", {
            "policy_name": "task_management",
            "policy_path": "/path/v2.md"
        })

        result = get_active_policy_injections_from_events()

        assert len(result) == 1
        assert result[0]["policy_path"] == "/path/v2.md"

    def test_compaction_boundary_resets_injections(self, isolated_event_log):
        """Compaction event acts as injection reset boundary."""
        append_event("policy_injection_activated", {
            "policy_name": "task_management",
            "policy_path": "/path/to/task_management.md"
        })
        append_event("compaction_detected", {
            "cycle": 100,
            "session_id": "test123"
        })

        result = get_active_policy_injections_from_events()

        # Injection before compaction is not visible
        assert result == []

    def test_injection_after_compaction_visible(self, isolated_event_log):
        """Injections after compaction are visible."""
        append_event("policy_injection_activated", {
            "policy_name": "old_policy",
            "policy_path": "/path/to/old.md"
        })
        append_event("compaction_detected", {
            "cycle": 100,
            "session_id": "test123"
        })
        append_event("policy_injection_activated", {
            "policy_name": "new_policy",
            "policy_path": "/path/to/new.md"
        })

        result = get_active_policy_injections_from_events()

        # Only new injection visible (after compaction)
        assert len(result) == 1
        assert result[0]["policy_name"] == "new_policy"
