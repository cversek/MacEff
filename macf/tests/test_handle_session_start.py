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
         patch('macf.hooks.handle_session_start.load_project_state') as mock_load_proj, \
         patch('time.time') as mock_time:

        mock_temporal.return_value = {
            'timestamp_formatted': 'Wednesday, October 8, 2025 at 12:26:43 PM EDT',
            'day_of_week': 'Wednesday',
            'time_of_day': 'Afternoon'
        }
        mock_env.return_value = 'Host System'
        mock_cycle.return_value = 17
        mock_time.return_value = 1728400000.0

        # Mock project state with last session ended 5 minutes ago
        mock_load_proj.return_value = {
            'last_session_ended_at': 1728400000.0 - 300.0  # 5 minutes ago
        }

        # Set up state
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


def test_first_session_no_project_state(mock_dependencies):
    """Test hook shows 'First session' when no previous session exists."""
    from macf.hooks.handle_session_start import run
    from unittest.mock import patch

    mock_dependencies['detect_compaction'].return_value = False

    # Mock temporal context and environment
    with patch('macf.hooks.handle_session_start.get_temporal_context') as mock_temporal, \
         patch('macf.hooks.handle_session_start.detect_execution_environment') as mock_env, \
         patch('macf.hooks.handle_session_start.get_current_cycle_project') as mock_cycle, \
         patch('macf.hooks.handle_session_start.load_project_state') as mock_load_proj, \
         patch('time.time') as mock_time:

        mock_temporal.return_value = {
            'timestamp_formatted': 'Wednesday, October 8, 2025 at 12:26:43 PM EDT',
            'day_of_week': 'Wednesday',
            'time_of_day': 'Afternoon'
        }
        mock_env.return_value = 'Host System'
        mock_cycle.return_value = 17
        mock_time.return_value = 1728400000.0

        # Mock empty project state (no previous session)
        mock_load_proj.return_value = {}

        # Set up state
        mock_dependencies['state'].compaction_count = 0

        result = run("")

        # Verify message content shows "First session"
        context = result["hookSpecificOutput"]["additionalContext"]
        assert "First session" in context


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


def test_source_field_compact_detection(mock_dependencies):
    """Test primary detection via source field when source='compact'."""
    from macf.hooks.handle_session_start import run
    import json
    from unittest.mock import patch

    # Prepare input with source='compact'
    input_data = {"source": "compact", "session_id": "test123"}
    stdin_json = json.dumps(input_data)

    # Mock log_hook_event to capture events
    with patch('macf.hooks.handle_session_start.log_hook_event') as mock_log:
        result = run(stdin_json)

        # Verify compaction was detected
        assert result["continue"] is True
        assert "hookSpecificOutput" in result
        assert "additionalContext" in result["hookSpecificOutput"]

        # Verify COMPACTION_CHECK event was logged with source_field method
        compaction_check_calls = [
            call for call in mock_log.call_args_list
            if call[0][0].get('event_type') == 'COMPACTION_CHECK'
        ]
        assert len(compaction_check_calls) == 1

        event = compaction_check_calls[0][0][0]
        assert event['compaction_detected'] is True
        assert event['detection_method'] == "source_field"
        assert event['source'] == "compact"


def test_source_field_startup_no_detection(mock_dependencies):
    """Test no compaction detected when source='startup'."""
    from macf.hooks.handle_session_start import run
    import json
    from unittest.mock import patch

    # Prepare input with source='startup'
    input_data = {"source": "startup", "session_id": "test123"}
    stdin_json = json.dumps(input_data)

    # Mock temporal context and environment for non-compaction path
    with patch('macf.hooks.handle_session_start.get_temporal_context') as mock_temporal, \
         patch('macf.hooks.handle_session_start.detect_execution_environment') as mock_env, \
         patch('macf.hooks.handle_session_start.get_current_cycle_project') as mock_cycle, \
         patch('macf.hooks.handle_session_start.load_project_state') as mock_load_proj, \
         patch('time.time') as mock_time:

        mock_temporal.return_value = {
            'timestamp_formatted': 'Wednesday, October 8, 2025 at 12:26:43 PM EDT',
            'day_of_week': 'Wednesday',
            'time_of_day': 'Afternoon'
        }
        mock_env.return_value = 'Host System'
        mock_cycle.return_value = 17
        mock_time.return_value = 1728400000.0
        mock_load_proj.return_value = {}

        # Mock detect_compaction to ensure it's NOT called (source field takes precedence)
        mock_dependencies['detect_compaction'].return_value = False

        result = run(stdin_json)

        # Verify no compaction detected (normal session start message)
        assert result["continue"] is True
        context = result["hookSpecificOutput"]["additionalContext"]
        assert "🏗️ MACF | Session Start" in context
        assert "Session Context:" in context

        # Verify recovery message was NOT formatted (no compaction)
        mock_dependencies['format_message'].assert_not_called()


def test_source_field_missing_fallback_to_transcript(mock_dependencies):
    """Test fallback to transcript scanning when source field missing."""
    from macf.hooks.handle_session_start import run
    import json
    from unittest.mock import patch

    # Prepare input WITHOUT source field
    input_data = {"session_id": "test123"}
    stdin_json = json.dumps(input_data)

    # Mock detect_compaction to return True (transcript detection)
    mock_dependencies['detect_compaction'].return_value = True

    with patch('macf.hooks.handle_session_start.log_hook_event') as mock_log:
        result = run(stdin_json)

        # Verify compaction was detected via fallback
        assert result["continue"] is True
        assert "hookSpecificOutput" in result

        # Verify COMPACTION_CHECK event used compact_boundary method
        compaction_check_calls = [
            call for call in mock_log.call_args_list
            if call[0][0].get('event_type') == 'COMPACTION_CHECK'
        ]
        assert len(compaction_check_calls) == 1

        event = compaction_check_calls[0][0][0]
        assert event['compaction_detected'] is True
        assert event['detection_method'] == "compact_boundary"


def test_source_compact_logs_method(mock_dependencies):
    """Test detection_method='source_field' logged when source='compact'."""
    from macf.hooks.handle_session_start import run
    import json
    from unittest.mock import patch

    # Prepare input with source='compact'
    input_data = {"source": "compact", "session_id": "test123"}
    stdin_json = json.dumps(input_data)

    with patch('macf.hooks.handle_session_start.log_hook_event') as mock_log:
        run(stdin_json)

        # Find COMPACTION_CHECK event
        compaction_check_calls = [
            call for call in mock_log.call_args_list
            if call[0][0].get('event_type') == 'COMPACTION_CHECK'
        ]

        assert len(compaction_check_calls) == 1
        event = compaction_check_calls[0][0][0]

        # Verify exact fields logged
        assert event['hook_name'] == "session_start"
        assert event['event_type'] == "COMPACTION_CHECK"
        assert event['compaction_detected'] is True
        assert event['detection_method'] == "source_field"
        assert event['source'] == "compact"
        assert 'session_id' in event


def test_cycle_increments_on_compaction(mock_dependencies):
    """Test cycle number increments in project state when compaction detected."""
    from macf.hooks.handle_session_start import run
    import json
    from unittest.mock import patch

    # Prepare input with source='compact'
    input_data = {"source": "compact", "session_id": "test123"}
    stdin_json = json.dumps(input_data)

    mock_dependencies['detect_compaction'].return_value = True

    with patch('macf.hooks.handle_session_start.increment_cycle_project') as mock_increment:
        # Mock increment_cycle_project to return new cycle number
        mock_increment.return_value = 20

        result = run(stdin_json)

        # Verify increment_cycle_project was called with session_id
        mock_increment.assert_called_once_with("test-session-123")

        # Verify hook continues successfully
        assert result["continue"] is True
        assert "hookSpecificOutput" in result
