"""
Integration tests for hook event logging.

Tests that all 6 MACF hooks append events to agent_events_log.jsonl
with breadcrumbs and preserved stdin.
"""
import json
import tempfile
from pathlib import Path

import pytest

# Import hooks
from macf.hooks.handle_session_start import run as session_start_run
from macf.hooks.handle_user_prompt_submit import run as user_prompt_submit_run
from macf.hooks.handle_stop import run as stop_run
from macf.hooks.handle_pre_tool_use import run as pre_tool_use_run
from macf.hooks.handle_post_tool_use import run as post_tool_use_run
from macf.hooks.handle_subagent_stop import run as subagent_stop_run

# Import event log functions
from macf.agent_events_log import set_log_path, read_events, query_events
from macf.utils import parse_breadcrumb


@pytest.fixture
def temp_log_file():
    """Create temporary log file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as f:
        log_path = Path(f.name)

    # Set log path for testing
    set_log_path(log_path)

    yield log_path

    # Cleanup
    set_log_path(None)
    if log_path.exists():
        log_path.unlink()


@pytest.fixture
def temp_agent_state(tmp_path):
    """Create temporary .maceff directory with agent_state.json."""
    maceff_dir = tmp_path / ".maceff"
    maceff_dir.mkdir()

    agent_state = {
        "current_cycle_number": 100,
        "cycles_completed": 99,
        "last_session_id": "old-session-123"
    }

    state_file = maceff_dir / "agent_state.json"
    state_file.write_text(json.dumps(agent_state, indent=2))

    return maceff_dir


def test_session_start_appends_event(temp_log_file, temp_agent_state, monkeypatch):
    """SessionStart hook returns valid output structure.

    Note: testing=True prevents side effects (event appending) per safe-by-default.
    This test verifies return value structure, not event log content.
    Event appending is verified in agent_events_log tests.
    """
    # Mock find_project_root to return temp directory
    monkeypatch.setattr(
        'macf.utils.find_project_root',
        lambda: temp_agent_state.parent
    )

    # Mock get_current_session_id to return consistent session
    test_session_id = "test-session-current"
    monkeypatch.setattr(
        'macf.hooks.handle_session_start.get_current_session_id',
        lambda: test_session_id
    )

    # Update agent_state to match current session (no migration)
    agent_state_file = temp_agent_state / "agent_state.json"
    agent_state = json.loads(agent_state_file.read_text())
    agent_state["last_session_id"] = test_session_id
    agent_state_file.write_text(json.dumps(agent_state, indent=2))

    # Run SessionStart hook with testing=True (safe-by-default, no side effects)
    stdin_data = {"source": "normal"}
    result = session_start_run(json.dumps(stdin_data), testing=True)

    # Verify hook returned successfully with valid structure
    assert result["continue"] is True
    assert "hookSpecificOutput" in result
    # Hook output should contain additionalContext (consciousness injection)
    hook_output = result["hookSpecificOutput"]
    assert "additionalContext" in hook_output


# NOTE: test_migration_detected_has_file_size removed - relied on deleted load_agent_state
# Migration detection now uses event-first approach via detect_session_migration()


def test_dev_drv_lifecycle(temp_log_file, temp_agent_state, monkeypatch):
    """UserPromptSubmit + Stop creates dev_drv_started + dev_drv_ended events."""
    # Mock find_project_root
    monkeypatch.setattr(
        'macf.utils.find_project_root',
        lambda: temp_agent_state.parent
    )

    # Mock get_last_user_prompt_uuid
    test_prompt_uuid = "test-prompt-uuid-123"
    monkeypatch.setattr(
        'macf.utils.session.get_last_user_prompt_uuid',
        lambda session_id: test_prompt_uuid
    )

    # Start DEV_DRV
    stdin_data = {"session_id": "test-session"}
    result = user_prompt_submit_run(json.dumps(stdin_data), testing=True)
    assert result["continue"] is True

    # End DEV_DRV
    result = stop_run("", testing=True)
    assert result["continue"] is True

    # Read events
    events = list(read_events(limit=10))

    # Should have both events
    started_events = [e for e in events if e["event"] == "dev_drv_started"]
    ended_events = [e for e in events if e["event"] == "dev_drv_ended"]

    assert len(started_events) == 1
    assert len(ended_events) == 1

    # Verify started event
    assert started_events[0]["data"]["prompt_uuid"] == test_prompt_uuid

    # Verify ended event has duration
    assert "duration_seconds" in ended_events[0]["data"]


def test_tool_calls_logged(temp_log_file, temp_agent_state, monkeypatch):
    """PreToolUse + PostToolUse create tool_call events."""
    # Mock find_project_root
    monkeypatch.setattr(
        'macf.utils.find_project_root',
        lambda: temp_agent_state.parent
    )

    # Simulate tool call
    stdin_data = {
        "tool_name": "Read",
        "tool_input": {"file_path": "/test/file.txt"}
    }

    # Pre-tool
    result = pre_tool_use_run(json.dumps(stdin_data), testing=True)
    assert result["continue"] is True

    # Post-tool
    result = post_tool_use_run(json.dumps(stdin_data), testing=True)
    assert result["continue"] is True

    # Read events
    events = list(read_events(limit=10))

    # Should have both events
    started_events = [e for e in events if e["event"] == "tool_call_started"]
    completed_events = [e for e in events if e["event"] == "tool_call_completed"]

    assert len(started_events) == 1
    assert len(completed_events) == 1

    # Verify tool name and file_path captured
    assert started_events[0]["data"]["tool"] == "Read"
    assert started_events[0]["data"]["file_path"] == "/test/file.txt"

    assert completed_events[0]["data"]["tool"] == "Read"
    assert completed_events[0]["data"]["success"] is True


def test_delegation_logged(temp_log_file, temp_agent_state, monkeypatch):
    """SubagentStop creates delegation_completed event."""
    # Mock find_project_root
    monkeypatch.setattr(
        'macf.utils.find_project_root',
        lambda: temp_agent_state.parent
    )

    # Simulate delegation completion
    stdin_data = {
        "subagent_type": "DevOpsEng"
    }

    result = subagent_stop_run(json.dumps(stdin_data), testing=True)
    assert result["continue"] is True

    # Read events
    events = list(read_events(limit=10))

    # Should have delegation_completed event
    delegation_events = [e for e in events if e["event"] == "delegation_completed"]
    assert len(delegation_events) == 1

    event = delegation_events[0]
    assert event["data"]["agent_type"] == "DevOpsEng"
    assert event["data"]["success"] is True
    assert "duration_seconds" in event["data"]


def test_breadcrumbs_valid(temp_log_file, temp_agent_state, monkeypatch):
    """All events have valid breadcrumbs with s_/c_/g_/p_/t_ format."""
    # Mock find_project_root
    monkeypatch.setattr(
        'macf.utils.find_project_root',
        lambda: temp_agent_state.parent
    )

    # Generate some events
    session_start_run("{}", testing=True)
    pre_tool_use_run(json.dumps({"tool_name": "Read", "tool_input": {}}), testing=True)
    post_tool_use_run(json.dumps({"tool_name": "Read", "tool_input": {}}), testing=True)

    # Read all events
    events = list(read_events(limit=10))

    # All events should have valid breadcrumbs
    for event in events:
        breadcrumb = event.get("breadcrumb", "")

        # Parse breadcrumb
        parsed = parse_breadcrumb(breadcrumb)

        # Should have all components
        assert parsed is not None
        assert "session_id" in parsed
        assert "cycle" in parsed
        assert "git_hash" in parsed
        assert "timestamp" in parsed

        # Session ID should be shortened (8 chars)
        assert len(parsed["session_id"]) == 8

        # Cycle should be a number
        assert isinstance(parsed["cycle"], int)

        # Git hash should be shortened (7 chars)
        assert len(parsed["git_hash"]) == 7


def test_hook_input_preserved(temp_log_file, temp_agent_state, monkeypatch):
    """Complete stdin JSON preserved in hook_input field."""
    # Mock find_project_root
    monkeypatch.setattr(
        'macf.utils.find_project_root',
        lambda: temp_agent_state.parent
    )

    # Create stdin with multiple fields
    stdin_data = {
        "tool_name": "Bash",
        "tool_input": {
            "command": "ls -la",
            "timeout": 5000
        },
        "session_id": "test-session-123",
        "extra_field": "should be preserved"
    }

    # Run hook
    pre_tool_use_run(json.dumps(stdin_data), testing=True)

    # Read events
    events = list(read_events(limit=1))
    assert len(events) == 1

    event = events[0]

    # hook_input should match original stdin exactly
    assert event["hook_input"] == stdin_data

    # All fields should be preserved
    assert event["hook_input"]["tool_name"] == "Bash"
    assert event["hook_input"]["tool_input"]["command"] == "ls -la"
    assert event["hook_input"]["extra_field"] == "should be preserved"
