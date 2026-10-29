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
            with patch('macf.hooks.handle_pre_compact.get_cycle_number_from_events', return_value=5):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_5/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={'tokens_used': 140000, 'cl_level': 5}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            result = run("")

                            assert result['continue'] is True
                            assert 'systemMessage' in result

    def test_includes_breadcrumb_and_cluac_in_message(self, isolated_events_log):
        """System message includes breadcrumb and CL level."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.get_cycle_number_from_events', return_value=10):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_10/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={'cl_level': 3}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            result = run("")

                            message = result['systemMessage']
                            assert 'Pre-Compact' in message
                            assert 's_abc/c_10/g_def/p_ghi/t_123' in message
                            assert '3' in message  # CL level

    def test_logs_pre_compact_event_with_token_info(self, isolated_events_log):
        """Appends pre_compact event with token usage data."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.get_cycle_number_from_events', return_value=7):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_7/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={'tokens_used': 145000, 'cl_level': 2}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            result = run("")

                            # Verify event was logged
                            assert isolated_events_log.exists()
                            events = isolated_events_log.read_text().strip().split('\n')
                            assert len(events) >= 1

                            last_event = json.loads(events[-1])
                            assert last_event['event'] == 'pre_compact'
                            assert last_event['data']['session_id'] == 'test-session'
                            assert last_event['data']['cycle'] == 7
                            assert last_event['data']['tokens_used'] == 145000
                            assert last_event['data']['cl_level'] == 2

class TestPreCompactTrigger:
    """The hook records the client's own `trigger` field (#544).

    Claude Code's PreCompact input names who started a compaction in `trigger`
    ("manual" or "auto"). The hook used to read `source`, a SessionStart field the
    PreCompact input never carries, so every compaction was logged as "auto".
    """

    def _run(self, payload, isolated_events_log, notify=None):
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"), \
             patch('macf.hooks.handle_pre_compact.get_cycle_number_from_events', return_value=1), \
             patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'), \
             patch('macf.hooks.handle_pre_compact.get_token_info', return_value={}), \
             patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2026-10-09 11:00 PM'}), \
             patch('macf.channels.telegram.send_telegram_notification', notify or MagicMock()):
            run(json.dumps(payload) if payload is not None else "")
        return json.loads(isolated_events_log.read_text().strip().split('\n')[-1])

    def test_records_manual_trigger(self, isolated_events_log):
        """A typed /compact arrives as trigger "manual" and is recorded as such."""
        event = self._run({"hook_event_name": "PreCompact", "trigger": "manual"}, isolated_events_log)
        assert event['data']['trigger'] == 'manual'

    def test_records_auto_trigger(self, isolated_events_log):
        """A compaction the client started arrives as trigger "auto"."""
        event = self._run({"hook_event_name": "PreCompact", "trigger": "auto"}, isolated_events_log)
        assert event['data']['trigger'] == 'auto'

    def test_missing_trigger_is_unknown_never_auto(self, isolated_events_log):
        """No trigger in the input is recorded as unknown, not guessed as auto."""
        event = self._run(None, isolated_events_log)
        assert event['data']['trigger'] == 'unknown'

    def test_session_start_source_field_is_not_read(self, isolated_events_log):
        """A stray `source` (SessionStart's field) does not pass for the trigger."""
        event = self._run({"source": "manual"}, isolated_events_log)
        assert event['data']['trigger'] == 'unknown'
        assert 'source' not in event['data']

    def test_notice_names_the_trigger(self, isolated_events_log):
        """The compaction notice says the same trigger the event records."""
        notify = MagicMock()
        self._run({"hook_event_name": "PreCompact", "trigger": "manual"}, isolated_events_log, notify)
        sent = notify.call_args[0][0]
        assert 'Trigger: manual' in sent
        assert 'Source:' not in sent

    def test_handles_errors_gracefully(self, isolated_events_log):
        """Returns error message when exception occurs."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', side_effect=Exception("Test error")):
            result = run("")

            assert result['continue'] is True
            assert 'error' in result['systemMessage'].lower()
