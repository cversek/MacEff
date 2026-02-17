"""Tests for handle_pre_tool_use hook module."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for pre_tool_use handler."""
    with patch('macf.hooks.handle_pre_tool_use.get_current_session_id') as mock_session, \
         patch('macf.hooks.handle_pre_tool_use.start_deleg_drv') as mock_start, \
         patch('macf.hooks.handle_pre_tool_use.get_minimal_timestamp') as mock_timestamp:

        mock_session.return_value = "test-session-123"
        mock_start.return_value = None
        mock_timestamp.return_value = "11:45:23 PM"

        yield {
            'session_id': mock_session,
            'start_deleg': mock_start,
            'timestamp': mock_timestamp
        }


def test_task_tool_deleg_drv_start(mock_dependencies, hook_stdin_task_tool):
    """Test Task tool triggers DELEG_DRV start tracking."""
    from macf.hooks.handle_pre_tool_use import run

    # Event log isolation via fixtures - code runs same as production
    result = run(hook_stdin_task_tool)

    # start_deleg_drv should be called (event-first architecture - events isolated via fixtures)
    mock_dependencies['start_deleg'].assert_called_once()

    # Verify output contains delegation emoji (compressed format — no descriptions)
    assert "hookSpecificOutput" in result
    context = result["hookSpecificOutput"]["additionalContext"]
    assert "📜" in context


def test_read_file_tracking(mock_dependencies, hook_stdin_read_tool):
    """Test Read tool displays filename only (not full path)."""
    from macf.hooks.handle_pre_tool_use import run

    result = run(hook_stdin_read_tool)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Should show file emoji (compressed format — no filenames)
    assert "📄" in context


def test_write_file_tracking(mock_dependencies, hook_stdin_write_tool):
    """Test Write tool displays filename only."""
    from macf.hooks.handle_pre_tool_use import run

    result = run(hook_stdin_write_tool)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Should show file emoji (compressed format — no filenames)
    assert "📄" in context


def test_bash_command_tracking(mock_dependencies, hook_stdin_bash_tool):
    """Test Bash command is truncated to 40 characters."""
    from macf.hooks.handle_pre_tool_use import run

    result = run(hook_stdin_bash_tool)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Should show bash emoji (compressed format — no commands)
    assert "⚙️" in context
    # Full command should not be present
    assert "very long command that exceeds forty characters and needs truncation" not in context


def test_minimal_timestamp_included(mock_dependencies, hook_stdin_read_tool):
    """Test output starts with MACF tag and minimal timestamp."""
    from macf.hooks.handle_pre_tool_use import run

    mock_dependencies['timestamp'].return_value = "11:45:23 PM"

    result = run(hook_stdin_read_tool)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Should start with MACF tag and timestamp
    assert "MACF" in context
    assert "11:45:23 PM" in context


def test_empty_stdin_handling(mock_dependencies, hook_stdin_empty):
    """Test hook handles empty stdin gracefully."""
    from macf.hooks.handle_pre_tool_use import run

    result = run(hook_stdin_empty)

    assert isinstance(result, dict)
    assert result["continue"] is True
    assert "hookSpecificOutput" in result


def test_exception_handling(mock_dependencies):
    """Test hook handles exceptions gracefully."""
    from macf.hooks.handle_pre_tool_use import run

    # Simulate exception in session ID
    mock_dependencies['session_id'].side_effect = Exception("Session error")

    result = run("")

    # Should return minimal valid output
    assert result["continue"] is True
    assert "hookSpecificOutput" in result


# ==================== TODO Collapse Authorization Tests ====================
# DEPRECATED: v0.4.0 removes TODO system in favor of Task System

@pytest.mark.xfail(reason="DEPRECATED: v0.4.0 removes TODO system")
def test_todowrite_collapse_blocked_without_auth(mock_dependencies, isolated_events_log):
    """TodoWrite collapse is blocked when no authorization exists."""
    from macf.hooks.handle_pre_tool_use import run
    from macf.agent_events_log import append_event
    import json

    # Set up previous TODO state
    append_event("todos_updated", {"count": 50, "items": []})

    # Attempt collapse: 50 -> 10
    stdin = json.dumps({
        "tool_name": "TodoWrite",
        "tool_input": {"todos": [{"content": f"Item {i}", "status": "pending", "activeForm": "Test"} for i in range(10)]}
    })

    result = run(stdin)

    assert result["continue"] is False
    assert "TODO Collapse Blocked" in result["hookSpecificOutput"]["message"]
    assert "50" in result["hookSpecificOutput"]["message"]
    assert "10" in result["hookSpecificOutput"]["message"]


@pytest.mark.xfail(reason="DEPRECATED: v0.4.0 removes TODO system")
def test_todowrite_collapse_allowed_with_auth(mock_dependencies, isolated_events_log):
    """TodoWrite collapse is allowed when proper authorization exists."""
    from macf.hooks.handle_pre_tool_use import run
    from macf.agent_events_log import append_event
    import json

    # Set up previous TODO state
    append_event("todos_updated", {"count": 50, "items": []})
    # Add authorization
    append_event("todos_auth_collapse", {"from_count": 50, "to_count": 10, "reason": "test"})

    # Attempt collapse: 50 -> 10
    stdin = json.dumps({
        "tool_name": "TodoWrite",
        "tool_input": {"todos": [{"content": f"Item {i}", "status": "pending", "activeForm": "Test"} for i in range(10)]}
    })

    result = run(stdin)

    assert result["continue"] is True  # Allowed with auth


@pytest.mark.xfail(reason="DEPRECATED: v0.4.0 removes TODO system")
def test_todowrite_expansion_always_allowed(mock_dependencies, isolated_events_log):
    """TodoWrite expansion (adding items) is always allowed."""
    from macf.hooks.handle_pre_tool_use import run
    from macf.agent_events_log import append_event
    import json

    # Set up previous TODO state
    append_event("todos_updated", {"count": 10, "items": []})

    # Attempt expansion: 10 -> 50
    stdin = json.dumps({
        "tool_name": "TodoWrite",
        "tool_input": {"todos": [{"content": f"Item {i}", "status": "pending", "activeForm": "Test"} for i in range(50)]}
    })

    result = run(stdin)

    assert result["continue"] is True  # Expansion always allowed


@pytest.mark.xfail(reason="DEPRECATED: v0.4.0 removes TODO system")
def test_todowrite_auth_single_use(mock_dependencies, isolated_events_log):
    """Authorization is consumed after use (single-use)."""
    from macf.hooks.handle_pre_tool_use import run
    from macf.agent_events_log import append_event
    from macf.event_queries import get_latest_event
    import json

    # Set up state and auth
    append_event("todos_updated", {"count": 50, "items": []})
    append_event("todos_auth_collapse", {"from_count": 50, "to_count": 10, "reason": "test"})

    # First collapse uses auth
    stdin = json.dumps({
        "tool_name": "TodoWrite",
        "tool_input": {"todos": [{"content": f"Item {i}", "status": "pending", "activeForm": "Test"} for i in range(10)]}
    })
    result = run(stdin)
    assert result["continue"] is True

    # Check that auth was cleared
    cleared = get_latest_event("todos_auth_cleared")
    assert cleared is not None
    assert cleared["data"]["reason"] == "consumed_by_todowrite"
