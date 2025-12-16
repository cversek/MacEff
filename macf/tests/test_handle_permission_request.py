"""
Tests for handle_permission_request.py hook.

Tests PermissionRequest hook tracking of permission dialog events.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from macf.hooks.handle_permission_request import run


class TestPermissionRequestHook:
    """Tests for PermissionRequest hook run() function."""

    def test_returns_continue_true_on_success(self, isolated_events_log):
        """Hook returns continue=True for normal flow."""
        with patch('macf.hooks.handle_permission_request.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_permission_request.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_permission_request.get_breadcrumb', return_value='s_abc/c_5/g_def/p_ghi/t_123'):
                    result = run("", testing=True)

                    assert result['continue'] is True
                    assert 'systemMessage' in result

    def test_extracts_tool_name_from_stdin(self, isolated_events_log):
        """Extracts tool_name from stdin JSON."""
        stdin_data = json.dumps({
            "tool_name": "Write",
            "type": "file_write",
            "tool_input": {"file_path": "/test/file.py"}
        })

        with patch('macf.hooks.handle_permission_request.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_permission_request.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_permission_request.get_breadcrumb', return_value='s_abc/c_5/g_def/p_ghi/t_123'):
                    result = run(stdin_data, testing=True)

                    message = result['systemMessage']
                    assert 'Write' in message

    def test_logs_permission_requested_event(self, isolated_events_log):
        """Appends permission_requested event to event log."""
        stdin_data = json.dumps({
            "tool_name": "Bash",
            "type": "command_execution",
            "tool_input": {"command": "pytest tests/"}
        })

        with patch('macf.hooks.handle_permission_request.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_permission_request.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_permission_request.get_breadcrumb', return_value='s_abc/c_7/g_def/p_ghi/t_123'):
                    result = run(stdin_data, testing=True)

                    # Verify event was logged
                    assert isolated_events_log.exists()
                    events = isolated_events_log.read_text().strip().split('\n')
                    assert len(events) >= 1

                    last_event = json.loads(events[-1])
                    assert last_event['event'] == 'permission_requested'
                    assert last_event['data']['tool_name'] == 'Bash'
                    assert last_event['data']['permission_type'] == 'command_execution'

    def test_truncates_large_tool_input_preview(self, isolated_events_log):
        """Truncates tool_input preview exceeding 200 characters."""
        large_input = {"data": "x" * 300}
        stdin_data = json.dumps({
            "tool_name": "Write",
            "type": "file_write",
            "tool_input": large_input
        })

        with patch('macf.hooks.handle_permission_request.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_permission_request.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_permission_request.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    result = run(stdin_data, testing=True)

                    events = isolated_events_log.read_text().strip().split('\n')
                    last_event = json.loads(events[-1])
                    preview = last_event['data']['tool_input_preview']

                    assert len(preview) <= 220  # 200 + truncation marker
                    assert '[...' in preview and 'chars]' in preview

    def test_defaults_to_unknown_when_fields_missing(self, isolated_events_log):
        """Uses 'unknown' defaults when tool_name or type not provided."""
        with patch('macf.hooks.handle_permission_request.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_permission_request.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_permission_request.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    result = run("", testing=True)

                    events = isolated_events_log.read_text().strip().split('\n')
                    last_event = json.loads(events[-1])
                    assert last_event['data']['tool_name'] == 'unknown'
                    assert last_event['data']['permission_type'] == 'unknown'

    def test_handles_errors_gracefully(self, isolated_events_log):
        """Returns error message when exception occurs."""
        with patch('macf.hooks.handle_permission_request.get_current_session_id', side_effect=Exception("Test error")):
            result = run("", testing=True)

            assert result['continue'] is True
            assert 'error' in result['systemMessage'].lower()
