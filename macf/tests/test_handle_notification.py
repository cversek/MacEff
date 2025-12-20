"""
Tests for handle_notification.py hook.

Tests Notification hook tracking of Claude Code notification events.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from macf.hooks.handle_notification import run


class TestNotificationHook:
    """Tests for Notification hook run() function."""

    def test_returns_continue_true_on_success(self, isolated_events_log):
        """Hook returns continue=True for normal flow."""
        with patch('macf.hooks.handle_notification.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_notification.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_notification.get_breadcrumb', return_value='s_abc/c_5/g_def/p_ghi/t_123'):
                    result = run("")

                    assert result['continue'] is True
                    assert 'systemMessage' in result

    def test_extracts_notification_type_from_stdin(self, isolated_events_log):
        """Extracts notification_type field from stdin JSON."""
        stdin_data = json.dumps({
            "notification_type": "permission_prompt",
            "message": "Requesting permission for tool use"
        })

        with patch('macf.hooks.handle_notification.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_notification.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_notification.get_breadcrumb', return_value='s_abc/c_5/g_def/p_ghi/t_123'):
                    result = run(stdin_data)

                    message = result['systemMessage']
                    assert 'permission_prompt' in message

    def test_logs_notification_received_event(self, isolated_events_log):
        """Appends notification_received event to event log."""
        stdin_data = json.dumps({
            "notification_type": "idle_prompt",
            "message": "Session has been idle for 5 minutes"
        })

        with patch('macf.hooks.handle_notification.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_notification.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_notification.get_breadcrumb', return_value='s_abc/c_7/g_def/p_ghi/t_123'):
                    result = run(stdin_data)

                    # Verify event was logged
                    assert isolated_events_log.exists()
                    events = isolated_events_log.read_text().strip().split('\n')
                    assert len(events) >= 1

                    last_event = json.loads(events[-1])
                    assert last_event['event'] == 'notification_received'
                    assert last_event['data']['notification_type'] == 'idle_prompt'
                    assert last_event['data']['session_id'] == 'test-session'

    def test_truncates_long_messages(self, isolated_events_log):
        """Truncates message content exceeding 200 characters."""
        long_message = "x" * 300
        stdin_data = json.dumps({
            "notification_type": "auth_success",
            "message": long_message
        })

        with patch('macf.hooks.handle_notification.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_notification.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_notification.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    result = run(stdin_data)

                    events = isolated_events_log.read_text().strip().split('\n')
                    last_event = json.loads(events[-1])
                    preview = last_event['data']['message_preview']

                    assert len(preview) <= 220  # 200 + truncation marker
                    assert '[...300 chars]' in preview

    def test_defaults_to_unknown_notification_type(self, isolated_events_log):
        """Uses 'unknown' when notification_type not provided."""
        with patch('macf.hooks.handle_notification.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_notification.get_minimal_timestamp', return_value="12:00 PM"):
                with patch('macf.hooks.handle_notification.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    result = run("")

                    events = isolated_events_log.read_text().strip().split('\n')
                    last_event = json.loads(events[-1])
                    assert last_event['data']['notification_type'] == 'unknown'

    def test_handles_errors_gracefully(self, isolated_events_log):
        """Returns error message when exception occurs."""
        with patch('macf.hooks.handle_notification.get_current_session_id', side_effect=Exception("Test error")):
            result = run("")

            assert result['continue'] is True
            assert 'error' in result['systemMessage'].lower()
