"""
Tests for handle_session_end.py hook.

Tests SessionEnd hook tracking of session termination events.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from macf.hooks.handle_session_end import run


class TestSessionEndHook:
    """Tests for SessionEnd hook run() function."""

    def test_returns_continue_true_on_success(self, isolated_events_log):
        """Hook returns continue=True for normal flow."""
        with patch('macf.hooks.handle_session_end.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_session_end.get_cycle_number_from_events', return_value=5):
                with patch('macf.hooks.handle_session_end.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                    with patch('macf.hooks.handle_session_end.get_breadcrumb', return_value='s_abc/c_5/g_def/p_ghi/t_123'):
                        with patch('macf.hooks.handle_session_end.get_token_info', return_value={'tokens_used': 1000}):
                            result = run("", testing=True)

                            assert result['continue'] is True
                            assert 'systemMessage' in result

    def test_includes_session_context_in_message(self, isolated_events_log):
        """System message includes session ID and breadcrumb."""
        with patch('macf.hooks.handle_session_end.get_current_session_id', return_value="test-session-abc123"):
            with patch('macf.hooks.handle_session_end.get_cycle_number_from_events', return_value=10):
                with patch('macf.hooks.handle_session_end.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                    with patch('macf.hooks.handle_session_end.get_breadcrumb', return_value='s_abc/c_10/g_def/p_ghi/t_123'):
                        with patch('macf.hooks.handle_session_end.get_token_info', return_value={}):
                            result = run("", testing=True)

                            message = result['systemMessage']
                            assert 'Session Ended' in message
                            assert 'Session' in message  # Session context included
                            assert 's_abc/c_10/g_def/p_ghi/t_123' in message

    def test_logs_session_ended_event(self, isolated_events_log):
        """Appends session_ended event to event log."""
        with patch('macf.hooks.handle_session_end.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_session_end.get_cycle_number_from_events', return_value=7):
                with patch('macf.hooks.handle_session_end.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                    with patch('macf.hooks.handle_session_end.get_breadcrumb', return_value='s_abc/c_7/g_def/p_ghi/t_123'):
                        with patch('macf.hooks.handle_session_end.get_token_info', return_value={'tokens_used': 5000}):
                            result = run("", testing=True)

                            # Verify event was logged
                            assert isolated_events_log.exists()
                            events = isolated_events_log.read_text().strip().split('\n')
                            assert len(events) >= 1

                            last_event = json.loads(events[-1])
                            assert last_event['event'] == 'session_ended'
                            assert last_event['data']['session_id'] == 'test-session'
                            assert last_event['data']['cycle'] == 7

    def test_parses_stdin_json_for_reason(self, isolated_events_log):
        """Parses stdin JSON to extract termination reason."""
        stdin_data = json.dumps({"reason": "user_logout"})

        with patch('macf.hooks.handle_session_end.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_session_end.get_cycle_number_from_events', return_value=1):
                with patch('macf.hooks.handle_session_end.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                    with patch('macf.hooks.handle_session_end.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                        with patch('macf.hooks.handle_session_end.get_token_info', return_value={}):
                            result = run(stdin_data, testing=True)

                            # Verify reason captured in event
                            events = isolated_events_log.read_text().strip().split('\n')
                            last_event = json.loads(events[-1])
                            assert last_event['data']['reason'] == 'user_logout'

    def test_handles_errors_gracefully(self, isolated_events_log):
        """Returns error message when exception occurs."""
        # Force an error by making get_current_session_id raise
        with patch('macf.hooks.handle_session_end.get_current_session_id', side_effect=Exception("Test error")):
            result = run("", testing=True)

            assert result['continue'] is True
            assert 'error' in result['systemMessage'].lower()

    def test_handles_empty_stdin(self, isolated_events_log):
        """Handles empty stdin gracefully."""
        with patch('macf.hooks.handle_session_end.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_session_end.get_cycle_number_from_events', return_value=1):
                with patch('macf.hooks.handle_session_end.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                    with patch('macf.hooks.handle_session_end.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                        with patch('macf.hooks.handle_session_end.get_token_info', return_value={}):
                            result = run("", testing=True)

                            assert result['continue'] is True
                            # Should use "unknown" as default reason
                            events = isolated_events_log.read_text().strip().split('\n')
                            last_event = json.loads(events[-1])
                            assert last_event['data']['reason'] == 'unknown'
