"""
TDD Tests for Event Query Utilities.

These tests define expected behavior for event-sourced state reconstruction.
The implementation (macf.event_queries) does not exist yet - that's the point of TDD.

Tests verify that we can replace mutable state file reads with JSONL event log
queries for: DEV_DRV stats, DELEG_DRV stats, cycle number, compaction count,
and auto_mode detection.
"""
import pytest
import uuid
from pathlib import Path

from macf.agent_events_log import append_event, query_events


# =============================================================================
# Fixtures for Test Isolation
# =============================================================================

@pytest.fixture
def test_session_id():
    """Unique session ID for test isolation."""
    return f"test-session-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def different_session_id():
    """Different session ID for cross-session isolation tests."""
    return f"other-session-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def populated_dev_drv_events(test_session_id):
    """
    Populate test events for DEV_DRV tracking.

    Simulates typical development drive lifecycle:
    - Start at user prompt submission
    - End at stop hook
    """
    # Session started
    append_event("session_started", {
        "session_id": test_session_id,
        "cycle": 202
    })

    # DEV_DRV started (user submitted prompt)
    append_event("dev_drv_started", {
        "session_id": test_session_id,
        "prompt_uuid": "prompt-abc123",
        "timestamp": 1000.0
    })

    # DEV_DRV ended (stop hook)
    append_event("dev_drv_ended", {
        "session_id": test_session_id,
        "prompt_uuid": "prompt-abc123",
        "duration": 300.0
    })

    # Second DEV_DRV cycle
    append_event("dev_drv_started", {
        "session_id": test_session_id,
        "prompt_uuid": "prompt-def456",
        "timestamp": 1500.0
    })

    append_event("dev_drv_ended", {
        "session_id": test_session_id,
        "prompt_uuid": "prompt-def456",
        "duration": 450.0
    })

    return test_session_id


@pytest.fixture
def populated_deleg_drv_events(test_session_id):
    """
    Populate test events for DELEG_DRV tracking.

    Simulates delegation lifecycle:
    - Start at Task tool invocation
    - End at subagent_stop hook
    """
    # Session started
    append_event("session_started", {
        "session_id": test_session_id,
        "cycle": 202
    })

    # DELEG_DRV started (Task tool invoked)
    append_event("deleg_drv_started", {
        "session_id": test_session_id,
        "subagent_type": "devops-eng",
        "timestamp": 2000.0
    })

    # DELEG_DRV ended
    append_event("deleg_drv_ended", {
        "session_id": test_session_id,
        "subagent_type": "devops-eng",
        "duration": 120.0
    })

    # Second delegation to different subagent
    append_event("deleg_drv_started", {
        "session_id": test_session_id,
        "subagent_type": "test-eng",
        "timestamp": 2200.0
    })

    append_event("deleg_drv_ended", {
        "session_id": test_session_id,
        "subagent_type": "test-eng",
        "duration": 180.0
    })

    return test_session_id


@pytest.fixture
def populated_compaction_events(test_session_id):
    """Populate test events for compaction tracking."""
    # Session started
    append_event("session_started", {
        "session_id": test_session_id,
        "cycle": 202
    })

    # First compaction detected
    append_event("compaction_detected", {
        "session_id": test_session_id,
        "source": "compact"
    })

    # Second compaction (rare but possible in long sessions)
    append_event("compaction_detected", {
        "session_id": test_session_id,
        "source": "compact"
    })

    return test_session_id


@pytest.fixture
def populated_auto_mode_events(test_session_id):
    """Populate test events for auto_mode detection."""
    # Session started
    append_event("session_started", {
        "session_id": test_session_id,
        "cycle": 202
    })

    # Mode change (authoritative setting)
    append_event("mode_change", {
        "mode": "AUTO_MODE",
        "enabled": True,
        "session_id": test_session_id,
        "auth_validated": True
    })

    return test_session_id


# =============================================================================
# Tests for get_dev_drv_stats_from_events()
# =============================================================================

def test_dev_drv_stats_basic_calculation(populated_dev_drv_events):
    """Test basic DEV_DRV statistics calculation from events."""
    from macf.event_queries import get_dev_drv_stats_from_events

    stats = get_dev_drv_stats_from_events(populated_dev_drv_events)

    # Should count 2 completed DEV_DRVs
    assert stats["count"] == 2

    # Should sum durations: 300 + 450 = 750
    assert stats["total_duration"] == 750.0

    # Current prompt UUID should be from most recent ended drive
    assert stats["current_prompt_uuid"] == "prompt-def456"


def test_dev_drv_stats_empty_log(test_session_id):
    """Test DEV_DRV stats with no events in log."""
    from macf.event_queries import get_dev_drv_stats_from_events

    stats = get_dev_drv_stats_from_events(test_session_id)

    # Should return zero stats
    assert stats["count"] == 0
    assert stats["total_duration"] == 0.0
    assert stats["current_prompt_uuid"] is None


def test_dev_drv_stats_session_isolation(populated_dev_drv_events, different_session_id):
    """Test DEV_DRV stats only includes events from specified session."""
    from macf.event_queries import get_dev_drv_stats_from_events

    # Add events for different session
    append_event("dev_drv_started", {
        "session_id": different_session_id,
        "prompt_uuid": "other-prompt",
        "timestamp": 3000.0
    })

    append_event("dev_drv_ended", {
        "session_id": different_session_id,
        "prompt_uuid": "other-prompt",
        "duration": 999.0
    })

    # Query original session - should NOT include other session's events
    stats = get_dev_drv_stats_from_events(populated_dev_drv_events)

    assert stats["count"] == 2  # Only original session's 2 drives
    assert stats["total_duration"] == 750.0  # Should NOT include 999.0


def test_dev_drv_stats_incomplete_drive(test_session_id):
    """Test DEV_DRV stats with started but not ended drive."""
    from macf.event_queries import get_dev_drv_stats_from_events

    # Start a drive but don't end it (still in progress)
    append_event("dev_drv_started", {
        "session_id": test_session_id,
        "prompt_uuid": "prompt-incomplete",
        "timestamp": 5000.0
    })

    stats = get_dev_drv_stats_from_events(test_session_id)

    # Should NOT count incomplete drive
    assert stats["count"] == 0
    assert stats["total_duration"] == 0.0

    # Current prompt UUID should be set (drive is in progress)
    assert stats["current_prompt_uuid"] == "prompt-incomplete"


# =============================================================================
# Tests for get_deleg_drv_stats_from_events()
# =============================================================================

def test_deleg_drv_stats_basic_calculation(populated_deleg_drv_events):
    """Test basic DELEG_DRV statistics calculation from events."""
    from macf.event_queries import get_deleg_drv_stats_from_events

    stats = get_deleg_drv_stats_from_events(populated_deleg_drv_events)

    # Should count 2 delegations
    assert stats["count"] == 2

    # Should sum durations: 120 + 180 = 300
    assert stats["total_duration"] == 300.0

    # Should track unique subagent types
    assert set(stats["subagent_types"]) == {"devops-eng", "test-eng"}


def test_deleg_drv_stats_empty_log(test_session_id):
    """Test DELEG_DRV stats with no events."""
    from macf.event_queries import get_deleg_drv_stats_from_events

    stats = get_deleg_drv_stats_from_events(test_session_id)

    assert stats["count"] == 0
    assert stats["total_duration"] == 0.0
    assert stats["subagent_types"] == []


def test_deleg_drv_stats_multiple_same_type(test_session_id):
    """Test DELEG_DRV stats with multiple delegations to same subagent type."""
    from macf.event_queries import get_deleg_drv_stats_from_events

    # Delegate to devops-eng twice
    for i in range(2):
        append_event("deleg_drv_started", {
            "session_id": test_session_id,
            "subagent_type": "devops-eng",
            "timestamp": 1000.0 + i * 100
        })

        append_event("deleg_drv_ended", {
            "session_id": test_session_id,
            "subagent_type": "devops-eng",
            "duration": 50.0
        })

    stats = get_deleg_drv_stats_from_events(test_session_id)

    assert stats["count"] == 2
    assert stats["total_duration"] == 100.0

    # Should list subagent type once per delegation (not deduplicated)
    assert stats["subagent_types"] == ["devops-eng", "devops-eng"]


def test_deleg_drv_stats_session_isolation(populated_deleg_drv_events, different_session_id):
    """Test DELEG_DRV stats only includes events from specified session."""
    from macf.event_queries import get_deleg_drv_stats_from_events

    # Add events for different session
    append_event("deleg_drv_started", {
        "session_id": different_session_id,
        "subagent_type": "learning-curator",
        "timestamp": 9000.0
    })

    append_event("deleg_drv_ended", {
        "session_id": different_session_id,
        "subagent_type": "learning-curator",
        "duration": 999.0
    })

    # Query original session
    stats = get_deleg_drv_stats_from_events(populated_deleg_drv_events)

    assert stats["count"] == 2
    assert "learning-curator" not in stats["subagent_types"]


# =============================================================================
# Tests for get_cycle_number_from_events()
# =============================================================================

def test_cycle_number_from_compaction_detected():
    """Test cycle number extraction from most recent compaction_detected event."""
    from macf.event_queries import get_cycle_number_from_events

    # Simulate compaction progression (compaction_detected carries cycle number)
    append_event("compaction_detected", {"cycle": 200})
    append_event("compaction_detected", {"cycle": 201})
    append_event("compaction_detected", {"cycle": 202})

    cycle = get_cycle_number_from_events()

    # Should return most recent cycle
    assert cycle == 202


def test_cycle_number_empty_log():
    """Test cycle number with no session_started events."""
    from macf.event_queries import get_cycle_number_from_events

    cycle = get_cycle_number_from_events()

    # Should return 0 or 1 as default (implementation decision)
    assert cycle in [0, 1]


def test_cycle_number_ignores_other_events():
    """Test cycle number ignores non-session_started events."""
    from macf.event_queries import get_cycle_number_from_events

    # Add various events without session_started
    append_event("dev_drv_started", {"prompt_uuid": "test"})
    append_event("compaction_detected", {"source": "compact"})

    cycle = get_cycle_number_from_events()

    # Should return default (no session_started found)
    assert cycle in [0, 1]


# =============================================================================
# Tests for get_compaction_count_from_events()
# =============================================================================

def test_compaction_count_basic(populated_compaction_events):
    """Test compaction count with multiple compaction events."""
    from macf.event_queries import get_compaction_count_from_events

    result = get_compaction_count_from_events(populated_compaction_events)

    # Should count 2 compaction events
    assert result["count"] == 2


def test_compaction_count_empty_log(test_session_id):
    """Test compaction count with no events."""
    from macf.event_queries import get_compaction_count_from_events

    result = get_compaction_count_from_events(test_session_id)

    assert result["count"] == 0


def test_compaction_count_session_isolation(populated_compaction_events, different_session_id):
    """Test compaction count only includes events from specified session."""
    from macf.event_queries import get_compaction_count_from_events

    # Add compactions for different session
    for _ in range(3):
        append_event("compaction_detected", {
            "session_id": different_session_id,
            "source": "compact"
        })

    # Query original session - should NOT include other session's compactions
    result = get_compaction_count_from_events(populated_compaction_events)

    assert result["count"] == 2  # Only original session's compactions


def test_compaction_count_distinguishes_sources(test_session_id):
    """Test compaction count distinguishes between different compaction sources."""
    from macf.event_queries import get_compaction_count_from_events

    # User-initiated compaction
    append_event("compaction_detected", {
        "session_id": test_session_id,
        "source": "compact"
    })

    # Auto-compaction (if implementation tracks this separately)
    append_event("compaction_detected", {
        "session_id": test_session_id,
        "source": "auto"
    })

    result = get_compaction_count_from_events(test_session_id)

    # Should count both (implementation may filter by source)
    assert result["count"] >= 1  # At least the user-initiated one


# =============================================================================
# Tests for get_auto_mode_from_events()
# =============================================================================

def test_auto_mode_basic_detection(populated_auto_mode_events):
    """Test auto_mode detection from mode_change events."""
    from macf.event_queries import get_auto_mode_from_events

    auto_mode, source = get_auto_mode_from_events(populated_auto_mode_events)

    assert auto_mode is True
    assert source == "event"


def test_auto_mode_empty_log(test_session_id):
    """Test auto_mode with no events (should return defaults)."""
    from macf.event_queries import get_auto_mode_from_events

    auto_mode, source = get_auto_mode_from_events(test_session_id)

    assert auto_mode is False
    assert source == "default"


def test_auto_mode_priority_ordering(test_session_id):
    """Test most recent mode_change wins."""
    from macf.event_queries import get_auto_mode_from_events

    # First: enable AUTO_MODE
    append_event("mode_change", {
        "mode": "AUTO_MODE",
        "enabled": True,
        "session_id": test_session_id,
        "auth_validated": True
    })

    # Later: disable back to MANUAL_MODE
    append_event("mode_change", {
        "mode": "MANUAL_MODE",
        "enabled": False,
        "session_id": test_session_id,
        "auth_validated": False
    })

    auto_mode, source = get_auto_mode_from_events(test_session_id)

    # Most recent mode_change wins — MANUAL_MODE was last
    assert auto_mode is False
    assert source == "event"


def test_auto_mode_session_isolation(populated_auto_mode_events, different_session_id):
    """Test auto_mode only uses events from specified session."""
    from macf.event_queries import get_auto_mode_from_events

    # Add mode_change for different session (should be ignored)
    append_event("mode_change", {
        "mode": "MANUAL_MODE",
        "enabled": False,
        "session_id": different_session_id,
        "auth_validated": False
    })

    # Query original session — should still see AUTO_MODE
    auto_mode, source = get_auto_mode_from_events(populated_auto_mode_events)

    assert auto_mode is True
    assert source == "event"


# ==================== get_nth_event tests ====================

def test_get_nth_event_returns_most_recent_at_n_zero(isolated_events_log):
    """get_nth_event with n=0 returns most recent event of type."""
    from macf.event_queries import get_nth_event
    from macf.agent_events_log import append_event

    # Add multiple todos_updated events
    append_event("todos_updated", {"count": 10, "items": []})
    append_event("todos_updated", {"count": 20, "items": []})
    append_event("todos_updated", {"count": 30, "items": []})

    result = get_nth_event("todos_updated", n=0)
    assert result is not None
    assert result["data"]["count"] == 30  # Most recent


def test_get_nth_event_returns_previous_at_n_one(isolated_events_log):
    """get_nth_event with n=1 returns second most recent."""
    from macf.event_queries import get_nth_event
    from macf.agent_events_log import append_event

    append_event("todos_updated", {"count": 10, "items": []})
    append_event("todos_updated", {"count": 20, "items": []})
    append_event("todos_updated", {"count": 30, "items": []})

    result = get_nth_event("todos_updated", n=1)
    assert result is not None
    assert result["data"]["count"] == 20  # Previous


def test_get_nth_event_returns_none_when_n_exceeds_count(isolated_events_log):
    """get_nth_event returns None when n exceeds available events."""
    from macf.event_queries import get_nth_event
    from macf.agent_events_log import append_event

    append_event("todos_updated", {"count": 10, "items": []})

    result = get_nth_event("todos_updated", n=5)
    assert result is None


def test_get_nth_event_filters_by_event_type(isolated_events_log):
    """get_nth_event only counts events of specified type."""
    from macf.event_queries import get_nth_event
    from macf.agent_events_log import append_event

    append_event("todos_updated", {"count": 10})
    append_event("other_event", {"data": "ignored"})
    append_event("todos_updated", {"count": 20})
    append_event("other_event", {"data": "ignored"})
    append_event("todos_updated", {"count": 30})

    # n=1 should skip the most recent todos_updated and return count=20
    result = get_nth_event("todos_updated", n=1)
    assert result is not None
    assert result["data"]["count"] == 20
