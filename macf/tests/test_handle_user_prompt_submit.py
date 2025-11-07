"""Tests for handle_user_prompt_submit hook module."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for user_prompt_submit handler."""
    with patch('macf.hooks.handle_user_prompt_submit.get_current_session_id') as mock_session, \
         patch('macf.hooks.handle_user_prompt_submit.get_temporal_context') as mock_temporal, \
         patch('macf.hooks.handle_user_prompt_submit.start_dev_drv') as mock_start_drv, \
         patch('macf.hooks.handle_user_prompt_submit.get_token_info') as mock_token, \
         patch('macf.hooks.handle_user_prompt_submit.detect_auto_mode') as mock_auto, \
         patch('macf.hooks.handle_user_prompt_submit.get_breadcrumb') as mock_breadcrumb, \
         patch('macf.hooks.handle_user_prompt_submit.get_rich_environment_string') as mock_env, \
         patch('macf.hooks.handle_user_prompt_submit.get_last_user_prompt_uuid') as mock_prompt_uuid:

        mock_session.return_value = "test-session-123"
        mock_temporal.return_value = {
            "timestamp_formatted": "2025-10-08 12:45:30 AM EDT",
            "day_of_week": "Wednesday",
            "time_of_day": "12:45:30 AM"
        }
        mock_start_drv.return_value = None
        mock_token.return_value = {
            'cluac_level': 50,
            'tokens_used': 100000,
            'tokens_remaining': 100000
        }
        mock_auto.return_value = (False, "default", 0.0)
        mock_breadcrumb.return_value = "s_test/c_1/g_abc1234/p_def5678/t_1234567890"
        mock_env.return_value = "Host System"
        mock_prompt_uuid.return_value = "prompt-uuid-abc123"

        yield {
            'session_id': mock_session,
            'temporal': mock_temporal,
            'start_drv': mock_start_drv,
            'token_info': mock_token,
            'auto_mode': mock_auto,
            'breadcrumb': mock_breadcrumb,
            'environment': mock_env,
            'prompt_uuid': mock_prompt_uuid
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


def test_breadcrumb_displayed(mock_dependencies):
    """Test breadcrumb is displayed in output."""
    from macf.hooks.handle_user_prompt_submit import run

    result = run("")

    context = result["hookSpecificOutput"]["additionalContext"]
    assert "s_test/c_1/g_abc1234/p_def5678/t_1234567890" in context


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
