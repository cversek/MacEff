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

    assert "systemMessage" in result
    message = result["systemMessage"]

    # Verify count displayed
    assert "Total Drives: 5" in message or "5" in message

    # Verify duration formatted (3600s = 1h 0m)
    assert "1h" in message


def test_uuid_truncation(mock_dependencies):
    """Test UUID is truncated to first 8 characters."""
    from macf.hooks.handle_stop import run

    mock_dependencies['stats'].return_value = {
        'count': 1,
        'total_duration': 60,
        'prompt_uuid': 'dda5c541-e66d-4c55-ad30-68d54d6a73cb'
    }

    result = run("")

    message = result["systemMessage"]

    # UUID should be truncated
    assert "dda5c541" in message
    # Full UUID should NOT be present
    assert "dda5c541-e66d-4c55-ad30-68d54d6a73cb" not in message


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

    message = result["systemMessage"]
    assert "45s" in message


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

    message = result["systemMessage"]
    assert "5m" in message


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

    message = result["systemMessage"]
    assert "2h" in message and "15m" in message


def test_exception_handling(mock_dependencies):
    """Test hook handles exceptions gracefully."""
    from macf.hooks.handle_stop import run

    # Simulate exception in stats retrieval
    mock_dependencies['stats'].side_effect = Exception("Stats error")

    result = run("")

    # Should never crash
    assert result == {"continue": True}


def test_saves_session_end_time_to_project_state(mock_dependencies):
    """Test Stop hook saves end time to project state for cross-session tracking."""
    from macf.hooks.handle_stop import run
    from unittest.mock import patch

    with patch('macf.hooks.handle_stop.load_project_state') as mock_load, \
         patch('macf.hooks.handle_stop.save_project_state') as mock_save, \
         patch('macf.hooks.handle_stop.get_temporal_context') as mock_temporal, \
         patch('macf.hooks.handle_stop.detect_execution_environment') as mock_env, \
         patch('macf.hooks.handle_stop.get_current_cycle_project') as mock_cycle, \
         patch('time.time') as mock_time:

        mock_load.return_value = {}
        mock_time.return_value = 1728400000.0
        mock_temporal.return_value = {
            'timestamp_formatted': 'Wednesday, October 8, 2025 at 12:26:43 PM EDT',
            'day_of_week': 'Wednesday',
            'time_of_day': 'Afternoon'
        }
        mock_env.return_value = 'Host System'
        mock_cycle.return_value = 17

        result = run("")

        # Verify project state was loaded and saved
        mock_load.assert_called_once()
        mock_save.assert_called_once()

        # Verify the saved state contains last_session_ended_at
        saved_state = mock_save.call_args[0][0]
        assert 'last_session_ended_at' in saved_state
        assert saved_state['last_session_ended_at'] == 1728400000.0

        # Verify hook continues normally
        assert result["continue"] is True
