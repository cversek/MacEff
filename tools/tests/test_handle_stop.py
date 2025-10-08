"""Tests for handle_stop hook module."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for stop handler."""
    with patch('macf.hooks.handle_stop.get_current_session_id') as mock_session, \
         patch('macf.hooks.handle_stop.complete_dev_drv') as mock_complete, \
         patch('macf.hooks.handle_stop.get_dev_drv_stats') as mock_stats:

        mock_session.return_value = "test-session-123"
        mock_complete.return_value = (True, 45)  # (success, duration) tuple
        mock_stats.return_value = {
            'count': 5,
            'total_duration': 3600,
            'prompt_uuid': 'dda5c541-e66d-4c55-ad30-68d54d6a73cb'
        }

        yield {
            'session_id': mock_session,
            'complete': mock_complete,
            'stats': mock_stats
        }


def test_dev_drv_completion_tracking(mock_dependencies):
    """Test DEV_DRV completion is tracked with duration."""
    from macf.hooks.handle_stop import run

    mock_dependencies['complete'].return_value = (True, 45)

    result = run("")

    # Verify complete_dev_drv was called
    mock_dependencies['complete'].assert_called_once_with("test-session-123")
    assert result["continue"] is True


def test_stats_display_format(mock_dependencies):
    """Test stats are displayed with correct formatting."""
    from macf.hooks.handle_stop import run

    mock_dependencies['stats'].return_value = {
        'count': 5,
        'total_duration': 3600,
        'prompt_uuid': 'abc123'
    }

    result = run("")

    assert "hookSpecificOutput" in result
    context = result["hookSpecificOutput"]["additionalContext"]

    # Verify count displayed
    assert "Total Drives: 5" in context or "5" in context

    # Verify duration formatted (3600s = 1h 0m)
    assert "1h" in context


def test_uuid_truncation(mock_dependencies):
    """Test UUID is truncated to first 8 characters."""
    from macf.hooks.handle_stop import run

    mock_dependencies['stats'].return_value = {
        'count': 1,
        'total_duration': 60,
        'prompt_uuid': 'dda5c541-e66d-4c55-ad30-68d54d6a73cb'
    }

    result = run("")

    context = result["hookSpecificOutput"]["additionalContext"]

    # UUID should be truncated
    assert "dda5c541" in context
    # Full UUID should NOT be present
    assert "dda5c541-e66d-4c55-ad30-68d54d6a73cb" not in context


def test_duration_formatting_seconds(mock_dependencies):
    """Test duration displays as seconds when less than 60s."""
    from macf.hooks.handle_stop import run

    mock_dependencies['complete'].return_value = (True, 45)
    mock_dependencies['stats'].return_value = {
        'count': 1,
        'total_duration': 45,
        'prompt_uuid': 'abc'
    }

    result = run("")

    context = result["hookSpecificOutput"]["additionalContext"]
    assert "45s" in context


def test_duration_formatting_minutes(mock_dependencies):
    """Test duration displays as minutes when >= 60s."""
    from macf.hooks.handle_stop import run

    mock_dependencies['complete'].return_value = (True, 300)
    mock_dependencies['stats'].return_value = {
        'count': 1,
        'total_duration': 300,
        'prompt_uuid': 'abc'
    }

    result = run("")

    context = result["hookSpecificOutput"]["additionalContext"]
    assert "5m" in context


def test_duration_formatting_hours(mock_dependencies):
    """Test duration displays as hours and minutes."""
    from macf.hooks.handle_stop import run

    mock_dependencies['complete'].return_value = (True, 8100)
    mock_dependencies['stats'].return_value = {
        'count': 1,
        'total_duration': 8100,  # 2h 15m
        'prompt_uuid': 'abc'
    }

    result = run("")

    context = result["hookSpecificOutput"]["additionalContext"]
    assert "2h" in context and "15m" in context


def test_exception_handling(mock_dependencies):
    """Test hook handles exceptions gracefully."""
    from macf.hooks.handle_stop import run

    # Simulate exception in stats retrieval
    mock_dependencies['stats'].side_effect = Exception("Stats error")

    result = run("")

    # Should never crash
    assert result == {"continue": True}
