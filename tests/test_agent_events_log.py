"""
Unit tests for agent_events_log module (TDD Phase 1A)

**Expected State**: ALL TESTS SHOULD FAIL
- Import errors (module doesn't exist yet)
- AttributeErrors (functions don't exist yet)

This is CORRECT - Phase 1B will create the implementation.

Test Coverage:
1. Event Append Atomicity (5 tests)
2. Query Filtering Accuracy (5 tests)
3. Set Operations Correctness (3 tests)
4. State Reconstruction Correctness (4 tests)
5. Performance Tests (3 tests)

Total: 20 focused tests
"""

import pytest
import json
import tempfile
import time
import threading
from pathlib import Path
from typing import List, Dict

# These imports will fail initially - that's expected!
from macf.agent_events_log import (
    append_event,
    query_events,
    query_set_operations,
    reconstruct_state_at,
    get_current_state,
    read_events,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_log_file():
    """Create temporary log file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = Path(f.name)

    yield log_path

    # Cleanup
    if log_path.exists():
        log_path.unlink()


@pytest.fixture
def populated_log(temp_log_file):
    """Create log file with sample events for query tests."""
    events = [
        # Cycle 170 events
        {
            "timestamp": 1000.0,
            "event": "session_started",
            "breadcrumb": "s_abc12345/c_170/g_44545c6/p_none/t_1000",
            "data": {"session_id": "abc12345-1234-1234-1234-123456789abc", "cycle": 170},
            "hook_input": {}
        },
        {
            "timestamp": 1100.0,
            "event": "migration_detected",
            "breadcrumb": "s_abc12345/c_170/g_44545c6/p_none/t_1100",
            "data": {"orphaned_todo_size": 8400, "current_cycle": 170},
            "hook_input": {}
        },
        {
            "timestamp": 1200.0,
            "event": "tool_call_started",
            "breadcrumb": "s_abc12345/c_170/g_44545c6/p_xyz123/t_1200",
            "data": {"tool": "Read"},
            "hook_input": {}
        },
        # Cycle 171 events
        {
            "timestamp": 2000.0,
            "event": "session_started",
            "breadcrumb": "s_def67890/c_171/g_44545c6/p_none/t_2000",
            "data": {"session_id": "def67890-5678-5678-5678-567890abcdef", "cycle": 171},
            "hook_input": {}
        },
        {
            "timestamp": 2100.0,
            "event": "migration_detected",
            "breadcrumb": "s_def67890/c_171/g_44545c6/p_none/t_2100",
            "data": {"orphaned_todo_size": 50, "current_cycle": 171},
            "hook_input": {}
        },
        # Cycle 172 events with different git hash
        {
            "timestamp": 3000.0,
            "event": "session_started",
            "breadcrumb": "s_ghi11111/c_172/g_eb34edc/p_none/t_3000",
            "data": {"session_id": "ghi11111-9999-9999-9999-999999999ghi", "cycle": 172},
            "hook_input": {}
        },
        {
            "timestamp": 3100.0,
            "event": "tool_call_started",
            "breadcrumb": "s_ghi11111/c_172/g_eb34edc/p_abc456/t_3100",
            "data": {"tool": "Bash"},
            "hook_input": {}
        },
        {
            "timestamp": 3200.0,
            "event": "tool_call_started",
            "breadcrumb": "s_ghi11111/c_172/g_eb34edc/p_abc789/t_3200",
            "data": {"tool": "Read"},
            "hook_input": {}
        },
    ]

    # Write events to file
    with open(temp_log_file, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')

    return temp_log_file


# ============================================================================
# 1. Event Append Atomicity (5 tests)
# ============================================================================

def test_single_event_append_succeeds(temp_log_file):
    """
    GIVEN: Empty log file
    WHEN: append_event() called once
    THEN: Log contains exactly one valid JSON line with required fields
    """
    result = append_event(
        "session_started",
        {"session_id": "abc123", "cycle": 170}
    )

    assert result is True, "append_event should return True on success"

    # Read and verify
    with open(temp_log_file, 'r') as f:
        lines = f.readlines()

    assert len(lines) == 1, "Should have exactly one line"

    event = json.loads(lines[0])
    assert "timestamp" in event, "Event must have timestamp"
    assert "event" in event, "Event must have event type"
    assert "breadcrumb" in event, "Event must have breadcrumb"
    assert "data" in event, "Event must have data field"
    assert event["event"] == "session_started"


def test_concurrent_appends_dont_corrupt(temp_log_file):
    """
    GIVEN: Empty log file
    WHEN: 10 threads simultaneously append different events
    THEN: Log contains exactly 10 valid JSON lines with unique timestamps
    """
    num_threads = 10
    results = []

    def append_worker(thread_id):
        result = append_event(
            "tool_call_started",
            {"tool": f"Tool{thread_id}", "thread": thread_id}
        )
        results.append(result)

    threads = [threading.Thread(target=append_worker, args=(i,)) for i in range(num_threads)]

    # Start all threads simultaneously
    for t in threads:
        t.start()

    # Wait for completion
    for t in threads:
        t.join()

    # Verify results
    assert all(results), "All appends should succeed"

    with open(temp_log_file, 'r') as f:
        lines = f.readlines()

    assert len(lines) == num_threads, f"Should have exactly {num_threads} lines"

    # Verify all lines are valid JSON
    events = []
    for line in lines:
        event = json.loads(line)
        events.append(event)

    # Verify unique timestamps
    timestamps = [e["timestamp"] for e in events]
    assert len(set(timestamps)) == num_threads, "All timestamps should be unique"


def test_append_with_hook_input_preserves_data(temp_log_file):
    """
    GIVEN: Event with hook_input dict
    WHEN: append_event() called with hook_input parameter
    THEN: Written event includes complete hook_input field matching original
    """
    hook_input_data = {
        "source": "compact",
        "stdin": {"session_id": "abc123"},
        "nested": {"key": "value"}
    }

    result = append_event(
        "migration_detected",
        {"orphaned_todo_size": 8400},
        hook_input=hook_input_data
    )

    assert result is True

    # Read and verify
    with open(temp_log_file, 'r') as f:
        event = json.loads(f.readline())

    assert "hook_input" in event, "Event must have hook_input field"
    assert event["hook_input"] == hook_input_data, "hook_input must match original exactly"


def test_append_returns_failure_on_error(temp_log_file):
    """
    GIVEN: Unwritable log location (permissions test)
    WHEN: append_event() called
    THEN: Returns False (graceful failure, no exception)
    """
    # Make file read-only
    temp_log_file.chmod(0o444)

    try:
        result = append_event("test_event", {"data": "test"})
        assert result is False, "append_event should return False on permission error"
    finally:
        # Restore permissions for cleanup
        temp_log_file.chmod(0o644)


def test_breadcrumb_generation_includes_all_components(temp_log_file):
    """
    GIVEN: Event appended
    WHEN: Read event from log
    THEN: Breadcrumb matches format s_X/c_N/g_Y/p_Z/t_T with all 5 components
    """
    result = append_event("test_event", {"test": "data"})
    assert result is True

    with open(temp_log_file, 'r') as f:
        event = json.loads(f.readline())

    breadcrumb = event["breadcrumb"]
    parts = breadcrumb.split('/')

    assert len(parts) == 5, "Breadcrumb must have 5 components"
    assert parts[0].startswith("s_"), "First component must be s_ (session)"
    assert parts[1].startswith("c_"), "Second component must be c_ (cycle)"
    assert parts[2].startswith("g_"), "Third component must be g_ (git)"
    assert parts[3].startswith("p_"), "Fourth component must be p_ (prompt)"
    assert parts[4].startswith("t_"), "Fifth component must be t_ (timestamp)"


# ============================================================================
# 2. Query Filtering Accuracy (5 tests)
# ============================================================================

def test_query_by_event_type(populated_log):
    """
    GIVEN: Log with 3 session_started, 2 migration_detected, 3 tool_call_started
    WHEN: Query for migration_detected events
    THEN: Returns exactly 2 events, all with correct type
    """
    results = query_events({'event_type': 'migration_detected'})

    assert len(results) == 2, "Should return exactly 2 migration_detected events"
    assert all(e["event"] == "migration_detected" for e in results)


def test_query_by_cycle_number(populated_log):
    """
    GIVEN: Events from cycles 170, 171, 172
    WHEN: Query for cycle 171 events
    THEN: Returns only events from cycle 171
    """
    results = query_events({'breadcrumb': {'c': 171}})

    assert len(results) == 2, "Should return 2 events from cycle 171"
    assert all("c_171" in e["breadcrumb"] for e in results)


def test_query_by_git_hash(populated_log):
    """
    GIVEN: Events from git states g_44545c6 and g_eb34edc
    WHEN: Query for g_eb34edc events
    THEN: Returns only events from g_eb34edc
    """
    results = query_events({'breadcrumb': {'g': 'eb34edc'}})

    assert len(results) == 3, "Should return 3 events from g_eb34edc"
    assert all("g_eb34edc" in e["breadcrumb"] for e in results)


def test_query_by_timestamp_range(populated_log):
    """
    GIVEN: Events with timestamps 1000-3200
    WHEN: Query for events between 1500 and 2500
    THEN: Returns only events in that range
    """
    results = query_events({'breadcrumb': {'t_min': 1500, 't_max': 2500}})

    assert len(results) == 2, "Should return 2 events in timestamp range"
    for event in results:
        assert 1500 <= event["timestamp"] <= 2500


def test_query_with_multiple_filters(populated_log):
    """
    GIVEN: Mixed events across cycles/types
    WHEN: Query with multiple filters (event_type AND cycle)
    THEN: Returns only events matching ALL filters
    """
    results = query_events({
        'event_type': 'tool_call_started',
        'breadcrumb': {'c': 172}
    })

    assert len(results) == 2, "Should return 2 tool_call_started events from cycle 172"
    assert all(e["event"] == "tool_call_started" for e in results)
    assert all("c_172" in e["breadcrumb"] for e in results)


# ============================================================================
# 3. Set Operations Correctness (3 tests)
# ============================================================================

def test_union_combines_results(populated_log):
    """
    GIVEN: Query A (cycle 170) returns 3 events, Query B (cycle 171) returns 2 events
    WHEN: Union operation performed
    THEN: Returns 5 unique events (3 + 2)
    """
    results = query_set_operations([
        {'breadcrumb': {'c': 170}},
        {'breadcrumb': {'c': 171}}
    ], "union")

    assert len(results) == 5, "Union should return 5 unique events"


def test_intersection_finds_common(populated_log):
    """
    GIVEN: Query A (cycle 170) and Query B (git g_44545c6)
    WHEN: Intersection operation performed
    THEN: Returns only events matching BOTH criteria
    """
    results = query_set_operations([
        {'breadcrumb': {'c': 170}},
        {'breadcrumb': {'g': '44545c6'}}
    ], "intersection")

    assert len(results) == 3, "Should return 3 events in cycle 170 AND git g_44545c6"
    assert all("c_170" in e["breadcrumb"] for e in results)
    assert all("g_44545c6" in e["breadcrumb"] for e in results)


def test_subtraction_removes_matches(populated_log):
    """
    GIVEN: Query A (all migration_detected) and Query B (cycle 171)
    WHEN: Subtraction operation performed
    THEN: Returns migrations NOT in cycle 171
    """
    results = query_set_operations([
        {'event_type': 'migration_detected'},
        {'breadcrumb': {'c': 171}}
    ], "subtraction")

    assert len(results) == 1, "Should return 1 migration (cycle 170 only)"
    assert results[0]["event"] == "migration_detected"
    assert "c_170" in results[0]["breadcrumb"]


# ============================================================================
# 4. State Reconstruction Correctness (4 tests)
# ============================================================================

def test_reconstruct_session_id_tracking(populated_log):
    """
    GIVEN: Events with multiple session_started events
    WHEN: reconstruct_state_at() called for different timestamps
    THEN: Returns correct session_id for each point in time
    """
    # After first session started
    state1 = reconstruct_state_at(1500.0)
    assert state1["session_id"] == "abc12345-1234-1234-1234-123456789abc"

    # After second session started
    state2 = reconstruct_state_at(2500.0)
    assert state2["session_id"] == "def67890-5678-5678-5678-567890abcdef"

    # After third session started
    state3 = reconstruct_state_at(3500.0)
    assert state3["session_id"] == "ghi11111-9999-9999-9999-999999999ghi"


def test_reconstruct_cycle_tracking(populated_log):
    """
    GIVEN: Events with multiple cycles
    WHEN: reconstruct_state_at() called
    THEN: Returns correct cycle for each timestamp
    """
    state1 = reconstruct_state_at(1500.0)
    assert state1["cycle"] == 170

    state2 = reconstruct_state_at(2500.0)
    assert state2["cycle"] == 171

    state3 = reconstruct_state_at(3500.0)
    assert state3["cycle"] == 172


def test_get_current_state_returns_latest(populated_log):
    """
    GIVEN: Multiple events across sessions/cycles
    WHEN: get_current_state() called
    THEN: Returns most recent session_id and cycle
    """
    state = get_current_state()

    assert state["session_id"] == "ghi11111-9999-9999-9999-999999999ghi"
    assert state["cycle"] == 172


def test_minimal_redundancy_preserved(populated_log):
    """
    GIVEN: Multiple tool_call events in same session
    WHEN: Read events
    THEN: session_id appears only in session_started, not repeated
    """
    # Count how many events have session_id in data
    with open(populated_log, 'r') as f:
        events = [json.loads(line) for line in f]

    session_id_count = sum(1 for e in events if "session_id" in e.get("data", {}))
    session_started_count = sum(1 for e in events if e["event"] == "session_started")

    assert session_id_count == session_started_count, \
        "session_id should only appear in session_started events"


# ============================================================================
# 5. Performance Tests (3 tests)
# ============================================================================

def test_single_append_under_5ms(temp_log_file):
    """
    GIVEN: Existing log
    WHEN: Append 1 event and measure time
    THEN: Operation completes in < 5ms (average over 100 runs)
    """
    durations = []

    for i in range(100):
        start = time.perf_counter()
        append_event("test_event", {"iteration": i})
        end = time.perf_counter()
        durations.append((end - start) * 1000)  # Convert to ms

    avg_duration = sum(durations) / len(durations)
    assert avg_duration < 5.0, f"Average append time {avg_duration:.2f}ms exceeds 5ms target"


def test_concurrent_appends_maintain_atomicity(temp_log_file):
    """
    GIVEN: 10 threads appending simultaneously
    WHEN: Each thread appends 10 events
    THEN: All 100 events written correctly, avg time < 10ms
    """
    num_threads = 10
    events_per_thread = 10
    durations = []

    def append_worker(thread_id):
        for i in range(events_per_thread):
            start = time.perf_counter()
            append_event("test_event", {"thread": thread_id, "iteration": i})
            end = time.perf_counter()
            durations.append((end - start) * 1000)

    threads = [threading.Thread(target=append_worker, args=(i,)) for i in range(num_threads)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify all events written
    with open(temp_log_file, 'r') as f:
        lines = f.readlines()

    assert len(lines) == num_threads * events_per_thread

    # Check average duration
    avg_duration = sum(durations) / len(durations)
    assert avg_duration < 10.0, f"Average concurrent append {avg_duration:.2f}ms exceeds 10ms"


def test_recent_query_under_10ms(populated_log):
    """
    GIVEN: Log with events
    WHEN: read_events(limit=10, reverse=True) called
    THEN: Returns recent events in < 10ms
    """
    durations = []

    for _ in range(10):
        start = time.perf_counter()
        events = list(read_events(limit=10, reverse=True))
        end = time.perf_counter()
        durations.append((end - start) * 1000)

    avg_duration = sum(durations) / len(durations)
    assert avg_duration < 10.0, f"Average query time {avg_duration:.2f}ms exceeds 10ms target"
    assert len(events) <= 10, "Should return at most 10 events"


# ============================================================================
# Summary
# ============================================================================

"""
Test Coverage Summary:
- Event Append Atomicity: 5 tests
- Query Filtering Accuracy: 5 tests
- Set Operations Correctness: 3 tests
- State Reconstruction Correctness: 4 tests
- Performance Tests: 3 tests

Total: 20 focused tests

Expected State: ALL TESTS FAIL
- ModuleNotFoundError: No module named 'macf.agent_events_log'
- This is CORRECT for TDD Phase 1A (RED phase)

Phase 1B (DevOpsEng) will implement the module to make tests pass (GREEN phase)
"""
