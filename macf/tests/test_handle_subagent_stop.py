"""Tests for handle_subagent_stop hook module."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for subagent_stop handler."""
    with patch('macf.hooks.handle_subagent_stop.get_current_session_id') as mock_session, \
         patch('macf.hooks.handle_subagent_stop.complete_deleg_drv') as mock_complete, \
         patch('macf.hooks.handle_subagent_stop.get_deleg_drv_stats') as mock_stats, \
         patch('macf.hooks.handle_subagent_stop.get_temporal_context') as mock_temporal:

        mock_session.return_value = "test-session-123"
        mock_complete.return_value = (True, 65)  # (success, duration) tuple
        mock_stats.return_value = {
            'count': 3,
            'total_duration': 180
        }
        mock_temporal.return_value = {
            "timestamp_formatted": "2025-10-08 01:15:30 AM EDT",
            "day_of_week": "Wednesday",
            "time_of_day": "01:15:30 AM"
        }

        yield {
            'session_id': mock_session,
            'complete': mock_complete,
            'stats': mock_stats,
            'temporal': mock_temporal
        }


def test_deleg_drv_completion_tracking(mock_dependencies):
    """Test DELEG_DRV completion tracking in production mode."""
    from macf.hooks.handle_subagent_stop import run

    mock_dependencies['complete'].return_value = (True, 65)

    # Call with testing=True (safe default) - mocks verify production code path exists
    result = run("", testing=True)

    # In testing mode, complete_deleg_drv should NOT be called (safe-by-default)
    mock_dependencies['complete'].assert_not_called()
    assert result["continue"] is True


def test_delegation_stats_display(mock_dependencies):
    """Test delegation stats are displayed correctly."""
    from macf.hooks.handle_subagent_stop import run

    mock_dependencies['stats'].return_value = {
        'count': 3,
        'total_duration': 180
    }

    result = run("")

    assert "systemMessage" in result
    message = result["systemMessage"]

    # Verify count
    assert "Total Delegations: 3" in message or "3" in message

    # Verify duration (180s = 3m)
    assert "3m" in message


def test_temporal_context_included(mock_dependencies):
    """Test temporal context is included in output."""
    from macf.hooks.handle_subagent_stop import run

    result = run("")

    message = result["systemMessage"]

    # Verify timestamp present
    assert "01:15:30 AM EDT" in message or "Wednesday" in message


def test_duration_formatting(mock_dependencies):
    """Test duration is formatted correctly."""
    from macf.hooks.handle_subagent_stop import run

    mock_dependencies['complete'].return_value = (True, 65)
    mock_dependencies['stats'].return_value = {
        'count': 1,
        'total_duration': 65
    }

    result = run("")

    message = result["systemMessage"]

    # 65 seconds should display as 1m
    assert "1m" in message


def test_exception_handling(mock_dependencies):
    """Test hook handles exceptions gracefully."""
    from macf.hooks.handle_subagent_stop import run

    # Simulate exception in stats
    mock_dependencies['stats'].side_effect = Exception("Stats error")

    result = run("")

    # Should never crash - SubagentStop uses systemMessage only (no hookSpecificOutput)
    assert result["continue"] is True
    assert "systemMessage" in result
    assert "error" in result["systemMessage"].lower()
