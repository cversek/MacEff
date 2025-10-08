"""Tests for handle_session_start hook module."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for session_start handler."""
    with patch('macf.hooks.handle_session_start.get_current_session_id') as mock_session, \
         patch('macf.hooks.handle_session_start.detect_compaction') as mock_detect, \
         patch('macf.hooks.handle_session_start.detect_auto_mode') as mock_auto, \
         patch('macf.hooks.handle_session_start.SessionOperationalState') as mock_state_class, \
         patch('macf.hooks.handle_session_start.get_latest_consciousness_artifacts') as mock_artifacts, \
         patch('macf.hooks.handle_session_start.format_consciousness_recovery_message') as mock_format:

        mock_session.return_value = "test-session-123"
        mock_detect.return_value = False
        mock_auto.return_value = (False, "default", 0.0)

        # Mock state instance
        mock_state = MagicMock()
        mock_state.compaction_count = 0
        mock_state.save.return_value = True
        mock_state_class.load.return_value = mock_state

        # Mock artifacts
        mock_artifacts.return_value = MagicMock()

        mock_format.return_value = "Recovery message content"

        yield {
            'session_id': mock_session,
            'detect_compaction': mock_detect,
            'auto_mode': mock_auto,
            'state_class': mock_state_class,
            'state': mock_state,
            'artifacts': mock_artifacts,
            'format_message': mock_format
        }


def test_no_compaction_detected(mock_dependencies):
    """Test hook returns temporal awareness message when no compaction detected."""
    from macf.hooks.handle_session_start import run
    from unittest.mock import patch
    import time

    mock_dependencies['detect_compaction'].return_value = False

    # Mock temporal context and environment
    with patch('macf.hooks.handle_session_start.get_temporal_context') as mock_temporal, \
         patch('macf.hooks.handle_session_start.detect_execution_environment') as mock_env, \
         patch('macf.hooks.handle_session_start.get_current_cycle_project') as mock_cycle, \
         patch('time.time') as mock_time:

        mock_temporal.return_value = {
            'timestamp_formatted': 'Wednesday, October 8, 2025 at 12:26:43 PM EDT',
            'day_of_week': 'Wednesday',
            'time_of_day': 'Afternoon'
        }
        mock_env.return_value = 'Host System'
        mock_cycle.return_value = 17
        mock_time.return_value = 1728400000.0

        # Set up state with previous last_updated 300 seconds ago
        mock_dependencies['state'].last_updated = 1728400000.0 - 300.0
        mock_dependencies['state'].session_started_at = 1728400000.0 - 600.0
        mock_dependencies['state'].compaction_count = 0

        result = run("")

        # Verify structure
        assert result["continue"] is True
        assert "hookSpecificOutput" in result
        assert "hookEventName" in result["hookSpecificOutput"]
        assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "additionalContext" in result["hookSpecificOutput"]

        # Verify message content
        context = result["hookSpecificOutput"]["additionalContext"]
        assert "🏗️ MACF | Session Start" in context
        assert "Wednesday, October 8, 2025 at 12:26:43 PM EDT" in context
        assert "Session: test-ses..." in context
        assert "5m" in context  # 300 seconds formatted
        assert "Compaction count: 0" in context
        assert "MACF Tools" in context

        # Verify state was updated
        assert mock_dependencies['state'].save.called
        mock_dependencies['format_message'].assert_not_called()


def test_compaction_detected_manual_mode(mock_dependencies):
    """Test compaction detected with MANUAL mode recovery protocol."""
    from macf.hooks.handle_session_start import run

    mock_dependencies['detect_compaction'].return_value = True
    mock_dependencies['auto_mode'].return_value = (False, "default", 0.0)
    mock_dependencies['format_message'].return_value = "MANUAL mode recovery instructions"

    result = run("")

    assert "continue" in result
    assert result["continue"] is True
    assert "hookSpecificOutput" in result
    assert "additionalContext" in result["hookSpecificOutput"]
    assert "MANUAL mode recovery" in result["hookSpecificOutput"]["additionalContext"]

    # Verify recovery message was formatted
    mock_dependencies['format_message'].assert_called_once()


def test_compaction_detected_auto_mode(mock_dependencies):
    """Test compaction detected with AUTO mode authorization."""
    from macf.hooks.handle_session_start import run

    mock_dependencies['detect_compaction'].return_value = True
    mock_dependencies['auto_mode'].return_value = (True, "env", 0.9)

    # Mock state with pending todos
    mock_dependencies['state'].pending_todos = [
        {"content": "Task 1", "status": "in_progress", "activeForm": "Working on task 1"}
    ]
    mock_dependencies['format_message'].return_value = "AUTO mode authorization message"

    result = run("")

    assert result["continue"] is True
    assert "hookSpecificOutput" in result
    assert "additionalContext" in result["hookSpecificOutput"]
    assert "AUTO mode" in result["hookSpecificOutput"]["additionalContext"]


def test_compaction_count_increments(mock_dependencies):
    """Test compaction count increments and state saves."""
    from macf.hooks.handle_session_start import run

    mock_dependencies['detect_compaction'].return_value = True
    mock_dependencies['state'].compaction_count = 2

    run("")

    assert mock_dependencies['state'].compaction_count == 3
    assert mock_dependencies['state'].save.call_count == 2  # Saves after increment AND auto_mode update


def test_exception_handling(mock_dependencies):
    """Test hook returns continue even when exception occurs."""
    from macf.hooks.handle_session_start import run

    # Simulate exception in session ID retrieval
    mock_dependencies['session_id'].side_effect = Exception("Session ID error")

    result = run("")

    # Hook should never crash - always returns continue
    assert result == {"continue": True}


def test_empty_stdin_handling(mock_dependencies):
    """Test hook handles empty stdin gracefully."""
    from macf.hooks.handle_session_start import run

    result = run("")

    assert isinstance(result, dict)
    assert "continue" in result
    assert result["continue"] is True


def test_output_format_includes_hook_event_name(mock_dependencies):
    """Test output includes hookEventName for observability."""
    from macf.hooks.handle_session_start import run

    mock_dependencies['detect_compaction'].return_value = True

    result = run("")

    assert "hookSpecificOutput" in result
    assert "hookEventName" in result["hookSpecificOutput"]
    assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
