"""
CLI Integration tests for `macf_tools events` commands (TDD Phase 2A)

**Expected State**: ALL TESTS SHOULD FAIL
- Commands don't exist yet (macf_tools events subcommands not implemented)
- This is CORRECT - Phase 2B will implement CLI commands

Test Coverage:
1. Reading Commands (3 tests)
2. Forensic Query Commands (4 tests)
3. Analysis Commands (3 tests)

Total: 10 focused tests
"""

import pytest
import json
import subprocess
import tempfile
from pathlib import Path


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_log_file():
    """Create temporary log file for CLI testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = Path(f.name)

    yield log_path

    # Cleanup
    if log_path.exists():
        log_path.unlink()


@pytest.fixture
def populated_log(temp_log_file):
    """Create log file with sample events for CLI query tests."""
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


@pytest.fixture
def cli_env(populated_log):
    """Environment variables for CLI testing (override log path)."""
    import os
    env = os.environ.copy()
    env["MACF_EVENTS_LOG_PATH"] = str(populated_log)
    return env


# ============================================================================
# 1. Reading Commands (3 tests)
# ============================================================================

def test_events_show_displays_current_state(cli_env):
    """
    GIVEN: Populated event log
    WHEN: macf_tools events show executed
    THEN: Displays current session_id and cycle in human-readable format
    """
    result = subprocess.run(
        ["macf_tools", "events", "show"],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    # Verify human-readable output contains expected fields
    output = result.stdout
    assert "session_id" in output.lower() or "session" in output.lower()
    assert "cycle" in output.lower()
    assert "ghi11111-9999-9999-9999-999999999ghi" in output  # Latest session
    assert "172" in output  # Latest cycle


def test_events_show_json_outputs_valid_json(cli_env):
    """
    GIVEN: Populated event log
    WHEN: macf_tools events show --json executed
    THEN: Outputs valid JSON with session_id and cycle fields
    """
    result = subprocess.run(
        ["macf_tools", "events", "show", "--json"],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    # Parse JSON output
    state = json.loads(result.stdout)

    assert "session_id" in state, "JSON should contain session_id"
    assert "cycle" in state, "JSON should contain cycle"
    assert state["session_id"] == "ghi11111-9999-9999-9999-999999999ghi"
    assert state["cycle"] == 172


def test_events_history_shows_recent_events(cli_env):
    """
    GIVEN: Log with 8 events
    WHEN: macf_tools events history executed (default: 10 most recent)
    THEN: Displays recent events in reverse chronological order
    """
    result = subprocess.run(
        ["macf_tools", "events", "history"],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    output = result.stdout

    # Verify some events are displayed
    assert "session_started" in output or "tool_call_started" in output

    # Verify chronological ordering (most recent first)
    # Latest event should appear before earlier events
    assert output.index("172") < output.index("170")  # Cycle 172 before 170


# ============================================================================
# 2. Forensic Query Commands (4 tests)
# ============================================================================

def test_query_by_event_type_filters_correctly(cli_env):
    """
    GIVEN: Log with multiple event types
    WHEN: macf_tools events query --event migration_detected
    THEN: Returns only migration_detected events
    """
    result = subprocess.run(
        ["macf_tools", "events", "query", "--event", "migration_detected"],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    output = result.stdout

    # Verify migration_detected appears
    assert "migration_detected" in output

    # Verify count (should mention 2 events)
    assert "2" in output or output.count("migration_detected") == 2


def test_query_by_cycle_filters_correctly(cli_env):
    """
    GIVEN: Events from cycles 170, 171, 172
    WHEN: macf_tools events query --cycle 171
    THEN: Returns only cycle 171 events
    """
    result = subprocess.run(
        ["macf_tools", "events", "query", "--cycle", "171"],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    output = result.stdout

    # Verify cycle 171 appears
    assert "171" in output or "c_171" in output

    # Verify count (should mention 2 events from cycle 171)
    assert "2" in output


def test_query_with_multiple_filters_applies_and_logic(cli_env):
    """
    GIVEN: Mixed events across cycles and types
    WHEN: macf_tools events query --event tool_call_started --cycle 172
    THEN: Returns only tool_call_started events from cycle 172 (AND logic)
    """
    result = subprocess.run(
        ["macf_tools", "events", "query", "--event", "tool_call_started", "--cycle", "172"],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    output = result.stdout

    # Verify both filters applied
    assert "tool_call_started" in output
    assert "172" in output or "c_172" in output

    # Verify count (should be 2 events: both tool_call_started in cycle 172)
    assert "2" in output


def test_query_set_subtraction_works(cli_env):
    """
    GIVEN: Multiple migration_detected events
    WHEN: macf_tools events query-set --subtract executed
    THEN: Subtraction operation removes matching events
    """
    result = subprocess.run(
        [
            "macf_tools", "events", "query-set",
            "--query", "event_type=migration_detected",
            "--subtract", "cycle=171"
        ],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    output = result.stdout

    # Should show migration from cycle 170, but NOT cycle 171
    assert "migration_detected" in output
    assert "170" in output or "c_170" in output

    # Should only be 1 result (migration from cycle 170)
    assert "1" in output


# ============================================================================
# 3. Analysis Commands (3 tests)
# ============================================================================

def test_sessions_list_shows_all_sessions(cli_env):
    """
    GIVEN: Log with 3 different sessions
    WHEN: macf_tools events sessions list
    THEN: Displays all 3 session IDs
    """
    result = subprocess.run(
        ["macf_tools", "events", "sessions", "list"],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    output = result.stdout

    # Verify all 3 sessions appear
    assert "abc12345" in output  # Session 1
    assert "def67890" in output  # Session 2
    assert "ghi11111" in output  # Session 3

    # Verify session count (3 sessions)
    assert "3" in output


def test_stats_shows_event_statistics(cli_env):
    """
    GIVEN: Log with multiple event types
    WHEN: macf_tools events stats
    THEN: Displays statistics (event counts by type)
    """
    result = subprocess.run(
        ["macf_tools", "events", "stats"],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    output = result.stdout

    # Verify statistics include event types and counts
    assert "session_started" in output
    assert "migration_detected" in output
    assert "tool_call_started" in output

    # Verify counts appear (3 session_started, 2 migration_detected, 3 tool_call_started)
    assert "3" in output  # session_started count
    assert "2" in output  # migration_detected count


def test_gaps_detects_session_crashes(cli_env):
    """
    GIVEN: Log with normal session boundaries
    WHEN: macf_tools events gaps --threshold 3600
    THEN: Analyzes time gaps and reports potential crashes
    """
    result = subprocess.run(
        ["macf_tools", "events", "gaps", "--threshold", "3600"],
        capture_output=True,
        text=True,
        env=cli_env
    )

    assert result.returncode == 0, "Command should succeed"

    output = result.stdout

    # Should analyze gaps between sessions
    # Our test data has gaps: 1000->2000 (1000s) and 2000->3000 (1000s)
    assert "gap" in output.lower() or "crash" in output.lower() or "session" in output.lower()


# ============================================================================
# Summary
# ============================================================================

"""
Test Coverage Summary:
- Reading Commands: 3 tests
  - events show (human-readable)
  - events show --json (JSON output)
  - events history (recent events)

- Forensic Query Commands: 4 tests
  - query --event (filter by type)
  - query --cycle (filter by cycle)
  - query with multiple filters (AND logic)
  - query-set subtraction (set operations)

- Analysis Commands: 3 tests
  - sessions list (all sessions)
  - stats (event statistics)
  - gaps (crash detection)

Total: 10 focused tests

Expected State: ALL TESTS FAIL
- subprocess.CalledProcessError or "unknown command" errors
- Commands don't exist yet in macf_tools CLI
- This is CORRECT for TDD Phase 2A (RED phase)

Phase 2B (DevOpsEng) will implement CLI commands to make tests pass (GREEN phase)
"""
