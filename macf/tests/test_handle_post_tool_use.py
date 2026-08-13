"""Tests for handle_post_tool_use hook module (silenced output, event-only)."""
import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_dependencies():
    """Mock external dependencies for post_tool_use handler."""
    with patch('macf.hooks.handle_post_tool_use.get_current_session_id') as mock_session, \
         patch('macf.hooks.handle_post_tool_use.append_event') as mock_append, \
         patch('macf.hooks.handle_post_tool_use.log_hook_event') as mock_log:

        mock_session.return_value = "test-session-123"

        yield {
            'session_id': mock_session,
            'append_event': mock_append,
            'log_hook_event': mock_log,
        }


def test_silent_output(mock_dependencies, hook_stdin_read_tool):
    """PostToolUse returns continue=True with no hookSpecificOutput."""
    from macf.hooks.handle_post_tool_use import run

    result = run(hook_stdin_read_tool)

    assert result["continue"] is True
    assert "hookSpecificOutput" not in result


def test_event_emission(mock_dependencies, hook_stdin_read_tool):
    """PostToolUse emits tool_call_completed event."""
    from macf.hooks.handle_post_tool_use import run

    run(hook_stdin_read_tool)

    mock_dependencies['append_event'].assert_called_once()
    call_args = mock_dependencies['append_event'].call_args
    assert call_args[1]['event'] == 'tool_call_completed' or call_args[0][0] == 'tool_call_completed'


def test_event_contains_tool_name(mock_dependencies, hook_stdin_bash_tool):
    """Event data includes tool name."""
    from macf.hooks.handle_post_tool_use import run

    run(hook_stdin_bash_tool)

    call_args = mock_dependencies['append_event'].call_args
    # data is second positional arg or keyword
    event_data = call_args[1].get('data') or call_args[0][1]
    assert event_data['tool'] == 'Bash'
    assert event_data['success'] is True


def test_large_stdout_sanitized(mock_dependencies):
    """Large tool_response stdout is replaced with size metadata.

    Sized relative to the threshold rather than against a literal, so this keeps
    asserting its guarantee if the threshold moves. It previously used a 1000
    byte payload against a stdout-specific limit of 500; the rule is now uniform
    and size-based, so content between the old and new limits is retained. That
    is a deliberate fidelity gain -- the entire stdout-shaped category accounted
    for 1.7% of bytes in the measurement that motivated the change.
    """
    from macf.hooks.handle_post_tool_use import run
    from macf.agent_events_log import ELIDE_THRESHOLD_BYTES

    large_output = "x" * (ELIDE_THRESHOLD_BYTES + 1)
    stdin = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
        "tool_response": {"stdout": large_output}
    })

    run(stdin)

    call_args = mock_dependencies['append_event'].call_args
    hook_input = call_args[1].get('hook_input') or call_args[0][2]
    assert hook_input['tool_response']['stdout'] == f'[{len(large_output)} bytes]'
    assert hook_input['tool_response']['stdout_size'] == len(large_output)
    # The command is irreplaceable and rides along untouched regardless of size.
    assert hook_input['tool_input']['command'] == 'echo hello'


def test_exception_handling(mock_dependencies):
    """Hook handles JSON parsing errors gracefully."""
    from macf.hooks.handle_post_tool_use import run

    result = run("{invalid json}")

    assert result["continue"] is True
    assert "hookSpecificOutput" not in result
