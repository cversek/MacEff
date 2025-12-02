"""
TDD Tests for Event-First Read Operations (Phase 5A).

These tests define expected behavior for migrating from mutable state file reads
to event-first queries. Tests should FAIL initially (red phase) until
implementation replaces state file reads with event_queries calls.

Migration Pattern:
    OLD: Read session_state.json → Extract dev_drv_count
    NEW: get_dev_drv_stats_from_events(session_id) → stats["count"]

Test Coverage:
    1. Event queries return correct data when events exist
    2. Graceful fallback when events missing (backward compatibility)
    3. Session isolation - queries don't cross session boundaries
    4. Integration - event_queries functions work with real hook outputs
"""
import pytest
import uuid
import json
from pathlib import Path

from macf.agent_events_log import append_event
from macf.event_queries import (
    get_dev_drv_stats_from_events,
    get_deleg_drv_stats_from_events,
    get_cycle_number_from_events,
    get_compaction_count_from_events,
    get_auto_mode_from_events
)


# =============================================================================
# Fixtures for Test Isolation
# =============================================================================

@pytest.fixture
def test_session_id():
    """Unique session ID for test isolation."""
    return f"test-evt-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def other_session_id():
    """Different session ID for isolation tests."""
    return f"other-evt-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def realistic_session_events(test_session_id):
    """
    Create realistic event sequence simulating actual session.

    Simulates:
    - Session start with cycle number
    - User submits prompt (DEV_DRV starts)
    - Work happens
    - Stop hook fires (DEV_DRV ends)
    - Delegation occurs during work
    """
    # Session initialization
    append_event("session_started", {
        "session_id": test_session_id,
        "cycle": 203,
        "timestamp": 1000.0
    })

    # Auto mode detection
    append_event("auto_mode_detected", {
        "session_id": test_session_id,
        "auto_mode": True,
        "source": "env_var",
        "confidence": 1.0
    })

    # First DEV_DRV cycle
    append_event("dev_drv_started", {
        "session_id": test_session_id,
        "prompt_uuid": "msg_01ABC123",
        "timestamp": 1100.0
    })

    # Delegation during DEV_DRV
    append_event("deleg_drv_started", {
        "session_id": test_session_id,
        "subagent_type": "test-eng",
        "timestamp": 1150.0
    })

    append_event("deleg_drv_ended", {
        "session_id": test_session_id,
        "subagent_type": "test-eng",
        "duration": 45.0
    })

    # DEV_DRV completes
    append_event("dev_drv_ended", {
        "session_id": test_session_id,
        "prompt_uuid": "msg_01ABC123",
        "duration": 120.0
    })

    return test_session_id


# =============================================================================
# Test Group 1: Event Queries Return Correct Data
# =============================================================================

def test_event_first_dev_drv_stats(realistic_session_events):
    """
    Test DEV_DRV stats come from events, not state files.

    This test will FAIL until implementation switches to event-first reads.
    """
    stats = get_dev_drv_stats_from_events(realistic_session_events)

    # Verify correct stats from event log
    assert stats["count"] == 1, "Should count 1 completed DEV_DRV"
    assert stats["total_duration"] == 120.0, "Should sum durations from events"
    assert stats["current_prompt_uuid"] == "msg_01ABC123", "Should track current prompt"


def test_event_first_deleg_drv_stats(realistic_session_events):
    """
    Test DELEG_DRV stats come from events, not state files.

    This test will FAIL until implementation switches to event-first reads.
    """
    stats = get_deleg_drv_stats_from_events(realistic_session_events)

    # Verify delegation stats from events
    assert stats["count"] == 1, "Should count 1 delegation"
    assert stats["total_duration"] == 45.0, "Should sum delegation durations"
    assert "test-eng" in stats["subagent_types"], "Should track subagent types"


def test_event_first_cycle_number(realistic_session_events):
    """
    Test cycle number comes from events, not state files.

    This test will FAIL until implementation switches to event-first reads.
    """
    cycle = get_cycle_number_from_events()

    # Should get cycle from most recent session_started event
    assert cycle == 203, "Should return cycle from events, not state file"


def test_event_first_auto_mode(realistic_session_events):
    """
    Test auto_mode detection comes from events, not state files.

    This test will FAIL until implementation switches to event-first reads.
    """
    auto_mode, source, confidence = get_auto_mode_from_events(realistic_session_events)

    # Should detect from events
    assert auto_mode is True, "Should detect auto_mode from events"
    assert source == "env_var", "Should preserve source information"
    assert confidence == 1.0, "Should preserve confidence value"


# =============================================================================
# Test Group 2: Graceful Fallback (Backward Compatibility)
# =============================================================================

def test_event_first_with_missing_events(test_session_id):
    """
    Test graceful handling when expected events don't exist.

    Backward compatibility scenario: querying sessions that haven't logged
    certain event types yet (historical gaps).
    """
    # No events logged for this session

    # Should return safe defaults, not crash
    dev_stats = get_dev_drv_stats_from_events(test_session_id)
    assert dev_stats["count"] == 0
    assert dev_stats["total_duration"] == 0.0
    assert dev_stats["current_prompt_uuid"] is None

    deleg_stats = get_deleg_drv_stats_from_events(test_session_id)
    assert deleg_stats["count"] == 0
    assert deleg_stats["total_duration"] == 0.0
    assert deleg_stats["subagent_types"] == []

    cycle = get_cycle_number_from_events()
    assert isinstance(cycle, int)
    assert cycle >= 0

    count = get_compaction_count_from_events(test_session_id)
    assert count == 0

    auto_mode, source, confidence = get_auto_mode_from_events(test_session_id)
    assert auto_mode is False
    assert source == "default"
    assert confidence == 0.0


def test_event_first_partial_events(test_session_id):
    """
    Test handling of incomplete event sequences.

    Example: dev_drv_started exists but dev_drv_ended doesn't (still in progress).
    """
    # Start a DEV_DRV but don't end it
    append_event("dev_drv_started", {
        "session_id": test_session_id,
        "prompt_uuid": "msg_INCOMPLETE",
        "timestamp": 5000.0
    })

    stats = get_dev_drv_stats_from_events(test_session_id)

    # Should NOT count incomplete drive
    assert stats["count"] == 0, "Incomplete drives shouldn't be counted"

    # But should track it as current
    assert stats["current_prompt_uuid"] == "msg_INCOMPLETE", "Should track in-progress drive"


# =============================================================================
# Test Group 3: Session Isolation
# =============================================================================

def test_event_first_session_isolation_dev_drv(realistic_session_events, other_session_id):
    """
    Test DEV_DRV queries only return events from specified session.

    Critical for multi-session environments - must not leak across sessions.
    """
    # Add events for different session
    append_event("dev_drv_started", {
        "session_id": other_session_id,
        "prompt_uuid": "msg_OTHER",
        "timestamp": 9000.0
    })

    append_event("dev_drv_ended", {
        "session_id": other_session_id,
        "prompt_uuid": "msg_OTHER",
        "duration": 999.0
    })

    # Query should only see realistic_session_events data
    stats = get_dev_drv_stats_from_events(realistic_session_events)

    assert stats["count"] == 1, "Should NOT count other session's drives"
    assert stats["total_duration"] == 120.0, "Should NOT include other session's duration"
    assert stats["current_prompt_uuid"] != "msg_OTHER", "Should NOT see other session's prompts"


def test_event_first_session_isolation_delegation(realistic_session_events, other_session_id):
    """
    Test DELEG_DRV queries only return events from specified session.
    """
    # Add delegation for different session
    append_event("deleg_drv_started", {
        "session_id": other_session_id,
        "subagent_type": "devops-eng",
        "timestamp": 9000.0
    })

    append_event("deleg_drv_ended", {
        "session_id": other_session_id,
        "subagent_type": "devops-eng",
        "duration": 999.0
    })

    # Query should only see realistic_session_events data
    stats = get_deleg_drv_stats_from_events(realistic_session_events)

    assert stats["count"] == 1, "Should NOT count other session's delegations"
    assert "devops-eng" not in stats["subagent_types"], "Should NOT see other session's subagents"


def test_event_first_session_isolation_compaction(test_session_id, other_session_id):
    """
    Test compaction count queries only return events from specified session.
    """
    # Add compaction for target session
    append_event("compaction_detected", {
        "session_id": test_session_id,
        "source": "compact"
    })

    # Add compactions for different session
    for _ in range(5):
        append_event("compaction_detected", {
            "session_id": other_session_id,
            "source": "compact"
        })

    # Query should only count test_session_id compactions
    count = get_compaction_count_from_events(test_session_id)

    assert count == 1, "Should NOT count other session's compactions"


# =============================================================================
# Test Group 4: Integration with Hook Outputs
# =============================================================================

def test_event_first_realistic_workflow(test_session_id):
    """
    Test event-first reads work with realistic hook event sequence.

    Simulates complete workflow:
    1. Session starts (SessionStart hook logs session_started)
    2. User submits prompt (UserPromptSubmit hook logs dev_drv_started)
    3. Agent does work
    4. Stop hook logs dev_drv_ended
    5. Query functions can reconstruct state
    """
    # Simulate SessionStart hook
    append_event("session_started", {
        "session_id": test_session_id,
        "cycle": 204,
        "timestamp": 1000.0
    })

    # Simulate UserPromptSubmit hook
    append_event("dev_drv_started", {
        "session_id": test_session_id,
        "prompt_uuid": "msg_01XYZ789",
        "timestamp": 1050.0
    })

    # Simulate Stop hook
    append_event("dev_drv_ended", {
        "session_id": test_session_id,
        "prompt_uuid": "msg_01XYZ789",
        "duration": 85.5
    })

    # Verify event-first queries reconstruct state correctly
    cycle = get_cycle_number_from_events()
    assert cycle == 204, "Should get cycle from session_started event"

    dev_stats = get_dev_drv_stats_from_events(test_session_id)
    assert dev_stats["count"] == 1, "Should count completed DEV_DRV"
    assert dev_stats["total_duration"] == 85.5, "Should sum durations accurately"
    assert dev_stats["current_prompt_uuid"] == "msg_01XYZ789", "Should track current prompt"


def test_event_first_multiple_drives_same_session(test_session_id):
    """
    Test event-first reads correctly handle multiple DEV_DRV cycles in one session.

    Real sessions have multiple user prompts, each creating a DEV_DRV.
    """
    # Session starts
    append_event("session_started", {
        "session_id": test_session_id,
        "cycle": 205
    })

    # Multiple DEV_DRV cycles
    prompts_and_durations = [
        ("msg_01AAA", 100.0),
        ("msg_01BBB", 150.0),
        ("msg_01CCC", 75.0)
    ]

    for prompt_uuid, duration in prompts_and_durations:
        append_event("dev_drv_started", {
            "session_id": test_session_id,
            "prompt_uuid": prompt_uuid,
            "timestamp": 2000.0
        })

        append_event("dev_drv_ended", {
            "session_id": test_session_id,
            "prompt_uuid": prompt_uuid,
            "duration": duration
        })

    # Verify event-first query aggregates correctly
    stats = get_dev_drv_stats_from_events(test_session_id)

    assert stats["count"] == 3, "Should count all completed drives"
    assert stats["total_duration"] == 325.0, "Should sum all durations"
    assert stats["current_prompt_uuid"] == "msg_01CCC", "Should track most recent prompt"
