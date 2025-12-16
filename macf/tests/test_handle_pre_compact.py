"""
Tests for handle_pre_compact.py hook.

Tests PreCompact hook tracking of imminent compaction events.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from macf.hooks.handle_pre_compact import run


class TestPreCompactHook:
    """Tests for PreCompact hook run() function."""

    def test_returns_continue_true_on_success(self, isolated_events_log):
        """Hook returns continue=True for normal flow."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.load_agent_state', return_value={'current_cycle_number': 5}):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_5/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={'tokens_used': 140000, 'cluac_level': 5}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            result = run("", testing=True)

                            assert result['continue'] is True
                            assert 'systemMessage' in result

    def test_includes_breadcrumb_and_cluac_in_message(self, isolated_events_log):
        """System message includes breadcrumb and CLUAC level."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.load_agent_state', return_value={'current_cycle_number': 10}):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_10/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={'cluac_level': 3}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            result = run("", testing=True)

                            message = result['systemMessage']
                            assert 'Pre-Compact' in message
                            assert 's_abc/c_10/g_def/p_ghi/t_123' in message
                            assert '3' in message  # CLUAC level

    def test_logs_pre_compact_event_with_token_info(self, isolated_events_log):
        """Appends pre_compact event with token usage data."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.load_agent_state', return_value={'current_cycle_number': 7}):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_7/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={'tokens_used': 145000, 'cluac_level': 2}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            result = run("", testing=True)

                            # Verify event was logged
                            assert isolated_events_log.exists()
                            events = isolated_events_log.read_text().strip().split('\n')
                            assert len(events) >= 1

                            last_event = json.loads(events[-1])
                            assert last_event['event'] == 'pre_compact'
                            assert last_event['data']['session_id'] == 'test-session'
                            assert last_event['data']['cycle'] == 7
                            assert last_event['data']['tokens_used'] == 145000
                            assert last_event['data']['cluac_level'] == 2

    def test_captures_compaction_source_from_stdin(self, isolated_events_log):
        """Captures source field (auto/manual) from stdin."""
        stdin_data = json.dumps({"source": "manual"})

        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.load_agent_state', return_value={}):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            result = run(stdin_data, testing=True)

                            # Verify source captured in event
                            events = isolated_events_log.read_text().strip().split('\n')
                            last_event = json.loads(events[-1])
                            assert last_event['data']['source'] == 'manual'

    def test_defaults_to_auto_source_when_missing(self, isolated_events_log):
        """Defaults source to 'auto' when not provided."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.load_agent_state', return_value={}):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            result = run("", testing=True)

                            events = isolated_events_log.read_text().strip().split('\n')
                            last_event = json.loads(events[-1])
                            assert last_event['data']['source'] == 'auto'

    def test_handles_errors_gracefully(self, isolated_events_log):
        """Returns error message when exception occurs."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', side_effect=Exception("Test error")):
            result = run("", testing=True)

            assert result['continue'] is True
            assert 'error' in result['systemMessage'].lower()
