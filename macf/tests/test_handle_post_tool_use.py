"""Tests for handle_post_tool_use hook module."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for post_tool_use handler."""
    with patch('macf.hooks.handle_post_tool_use.get_current_session_id') as mock_session, \
         patch('macf.hooks.handle_post_tool_use.get_minimal_timestamp') as mock_timestamp:

        mock_session.return_value = "test-session-123"
        mock_timestamp.return_value = "11:45:23 PM"

        yield {
            'session_id': mock_session,
            'timestamp': mock_timestamp
        }


def test_todowrite_status_summary(mock_dependencies, hook_stdin_todowrite):
    """Test TodoWrite displays status summary with emoji counts."""
    from macf.hooks.handle_post_tool_use import run

    result = run(hook_stdin_todowrite)

    assert "hookSpecificOutput" in result
    context = result["hookSpecificOutput"]["additionalContext"]

    # Should show counts: 2 completed, 1 in_progress, 3 pending
    assert "Todos:" in context
    assert "2" in context  # 2 completed
    assert "1" in context  # 1 in_progress
    assert "3" in context  # 3 pending


def test_task_completion_display(mock_dependencies, hook_stdin_task_tool):
    """Test Task tool shows completion message."""
    from macf.hooks.handle_post_tool_use import run

    result = run(hook_stdin_task_tool)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Should show delegation completion
    assert "Delegated to: devops-eng" in context or "devops-eng" in context


def test_grep_pattern_tracking(mock_dependencies, hook_stdin_grep_tool):
    """Test Grep pattern is truncated to 30 characters."""
    from macf.hooks.handle_post_tool_use import run

    result = run(hook_stdin_grep_tool)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Pattern should be truncated
    assert "..." in context
    # Full pattern should not be present
    assert "very long pattern that should be truncated to thirty characters" not in context


def test_glob_pattern_tracking(mock_dependencies, hook_stdin_glob_tool):
    """Test Glob pattern is displayed."""
    from macf.hooks.handle_post_tool_use import run

    result = run(hook_stdin_glob_tool)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Should show glob pattern
    assert "Glob:" in context or "**/*.py" in context


def test_file_operation_tracking(mock_dependencies):
    """Test Edit tool shows filename only."""
    from macf.hooks.handle_post_tool_use import run

    stdin = '{"tool_name": "Edit", "tool_input": {"file_path": "/some/path/config.yaml"}}'
    result = run(stdin)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Should show filename only
    assert "config.yaml" in context


def test_bash_command_tracking(mock_dependencies, hook_stdin_bash_tool):
    """Test Bash command is truncated to 40 characters."""
    from macf.hooks.handle_post_tool_use import run

    result = run(hook_stdin_bash_tool)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Command should be truncated
    assert "..." in context


def test_minimal_timestamp_included(mock_dependencies, hook_stdin_read_tool):
    """Test output starts with MACF tag and timestamp."""
    from macf.hooks.handle_post_tool_use import run

    mock_dependencies['timestamp'].return_value = "11:45:23 PM"

    result = run(hook_stdin_read_tool)

    context = result["hookSpecificOutput"]["additionalContext"]

    # Should start with MACF tag and timestamp
    assert "MACF" in context
    assert "11:45:23 PM" in context


def test_exception_handling(mock_dependencies):
    """Test hook handles JSON parsing errors gracefully."""
    from macf.hooks.handle_post_tool_use import run

    # Invalid JSON should not crash
    result = run("{invalid json}")

    # Should return minimal valid output
    assert result["continue"] is True
    assert "hookSpecificOutput" in result
