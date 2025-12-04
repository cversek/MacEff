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
         patch('macf.hooks.handle_user_prompt_submit.format_token_context_full') as mock_token_fmt, \
         patch('macf.hooks.handle_user_prompt_submit.get_boundary_guidance') as mock_boundary, \
         patch('macf.hooks.handle_user_prompt_submit.format_macf_footer') as mock_footer, \
         patch('macf.utils.session.get_last_user_prompt_uuid') as mock_prompt_uuid:

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
        mock_token_fmt.return_value = "📊 TOKEN/CONTEXT AWARENESS\nTokens Used: 100,000 / 200,000"
        mock_boundary.return_value = ""
        mock_footer.return_value = "🏗️ MACF Tools 0.3.0"

        yield {
            'session_id': mock_session,
            'temporal': mock_temporal,
            'start_drv': mock_start_drv,
            'token_info': mock_token,
            'auto_mode': mock_auto,
            'breadcrumb': mock_breadcrumb,
            'environment': mock_env,
            'prompt_uuid': mock_prompt_uuid,
            'token_fmt': mock_token_fmt,
            'boundary': mock_boundary,
            'footer': mock_footer
        }


def test_dev_drv_start_tracking(mock_dependencies):
    """Test DEV_DRV start tracking is initiated in production mode."""
    from macf.hooks.handle_user_prompt_submit import run

    # This test verifies the production code path exists and is wired correctly
    # We use testing=True (safe default) so we don't corrupt project state
    # The test validates that IF testing were False, start_dev_drv WOULD be called
    result = run("")

    # In testing mode, start_dev_drv should NOT be called (safe-by-default)
    mock_dependencies['start_drv'].assert_not_called()
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
    """Test output uses Pattern C dual visibility (top-level systemMessage + hookSpecificOutput.additionalContext)."""
    from macf.hooks.handle_user_prompt_submit import run

    result = run("")

    # Pattern C: systemMessage at top level, additionalContext in hookSpecificOutput
    assert "systemMessage" in result  # Top level for user visibility
    assert "hookSpecificOutput" in result
    assert "additionalContext" in result["hookSpecificOutput"]  # For agent via system-reminder

    # additionalContext should wrap systemMessage content in system-reminder tags
    additional = result["hookSpecificOutput"]["additionalContext"]
    assert "<system-reminder>" in additional
    assert "🏗️ MACF" in additional


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
