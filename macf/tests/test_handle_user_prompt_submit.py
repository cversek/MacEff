"""Tests for handle_user_prompt_submit hook module."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for user_prompt_submit handler."""
    with patch('macf.hooks.handle_user_prompt_submit.get_current_session_id') as mock_session, \
         patch('macf.hooks.handle_user_prompt_submit.get_temporal_context') as mock_temporal, \
         patch('macf.hooks.handle_user_prompt_submit.start_dev_drv') as mock_start_drv, \
         patch('macf.hooks.handle_user_prompt_submit.get_current_cycle_project') as mock_cycle:

        mock_session.return_value = "test-session-123"
        mock_temporal.return_value = {
            "timestamp_formatted": "2025-10-08 12:45:30 AM EDT",
            "day_of_week": "Wednesday",
            "time_of_day": "12:45:30 AM"
        }
        mock_start_drv.return_value = "prompt-uuid-abc123"
        mock_cycle.return_value = 18

        yield {
            'session_id': mock_session,
            'temporal': mock_temporal,
            'start_drv': mock_start_drv,
            'cycle': mock_cycle
        }


def test_dev_drv_start_tracking(mock_dependencies):
    """Test DEV_DRV start tracking is initiated."""
    from macf.hooks.handle_user_prompt_submit import run

    result = run("")

    # Verify start_dev_drv was called
    mock_dependencies['start_drv'].assert_called_once_with("test-session-123")
    assert result["continue"] is True


def test_temporal_awareness_included(mock_dependencies):
    """Test output includes temporal awareness context."""
    from macf.hooks.handle_user_prompt_submit import run

    result = run("")

    assert "hookSpecificOutput" in result
    assert "additionalContext" in result["hookSpecificOutput"]

    context = result["hookSpecificOutput"]["additionalContext"]
    assert "12:45:30 AM EDT" in context
    assert "Wednesday" in context


def test_dual_visibility_output_format(mock_dependencies):
    """Test output uses dual visibility (additionalContext + systemMessage)."""
    from macf.hooks.handle_user_prompt_submit import run

    result = run("")

    # Both fields should be present with same content
    assert "hookSpecificOutput" in result
    assert "additionalContext" in result["hookSpecificOutput"]
    assert "systemMessage" in result["hookSpecificOutput"]

    # Content should match
    additional = result["hookSpecificOutput"]["additionalContext"]
    system = result["hookSpecificOutput"]["systemMessage"]
    assert additional == system


def test_cycle_number_displayed(mock_dependencies):
    """Test cycle number is displayed in output."""
    from macf.hooks.handle_user_prompt_submit import run

    mock_dependencies['cycle'].return_value = 18

    result = run("")

    context = result["hookSpecificOutput"]["additionalContext"]
    assert "Cycle: 18" in context or "Cycle 18" in context


def test_exception_handling(mock_dependencies):
    """Test hook handles exceptions gracefully."""
    from macf.hooks.handle_user_prompt_submit import run

    # Simulate exception in temporal context
    mock_dependencies['temporal'].side_effect = Exception("Temporal error")

    result = run("")

    # Should return minimal valid output
    assert result["continue"] is True
    assert "hookSpecificOutput" in result
    assert "hookEventName" in result["hookSpecificOutput"]


def test_hook_event_name_present(mock_dependencies):
    """Test hookEventName is present for observability."""
    from macf.hooks.handle_user_prompt_submit import run

    result = run("")

    assert "hookSpecificOutput" in result
    assert "hookEventName" in result["hookSpecificOutput"]
    assert result["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
