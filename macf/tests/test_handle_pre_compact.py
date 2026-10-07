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

    # Claude Code's PreCompact input, key for key as a recorded event carries it
    # (values made generic). It has no `source`: that field belongs to SessionStart.
    PRECOMPACT_INPUT = {
        "session_id": "test-session",
        "transcript_path": "/tmp/test-transcript.jsonl",
        "cwd": "/tmp",
        "scratchpad_dir": "/tmp/scratchpad",
        "prompt_id": "test-prompt",
        "hook_event_name": "PreCompact",
        "trigger": "manual",
        "custom_instructions": None,
    }

    def test_records_the_trigger_claude_code_sends(self, isolated_events_log):
        """Records `trigger` from the hook input: "manual" covers a /compact and
        any compaction not driven by context size."""
        stdin_data = json.dumps(self.PRECOMPACT_INPUT)

        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.get_cycle_number_from_events', return_value=1):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            run(stdin_data)

                            events = isolated_events_log.read_text().strip().split('\n')
                            last_event = json.loads(events[-1])
                            assert last_event['data']['trigger'] == 'manual'

    def test_records_an_auto_trigger(self, isolated_events_log):
        """Records "auto" for a compaction driven by context size."""
        stdin_data = json.dumps(dict(self.PRECOMPACT_INPUT, trigger="auto"))

        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.get_cycle_number_from_events', return_value=1):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            run(stdin_data)

                            events = isolated_events_log.read_text().strip().split('\n')
                            last_event = json.loads(events[-1])
                            assert last_event['data']['trigger'] == 'auto'

    def test_missing_trigger_is_recorded_as_unknown(self, isolated_events_log):
        """A missing trigger is recorded as "unknown", never as one of its real values."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.get_cycle_number_from_events', return_value=1):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            run("")

                            events = isolated_events_log.read_text().strip().split('\n')
                            last_event = json.loads(events[-1])
                            assert last_event['data']['trigger'] == 'unknown'

    def test_notice_names_the_trigger(self, isolated_events_log):
        """The COMPACTION IMMINENT notice carries the trigger the hook received."""
        stdin_data = json.dumps(self.PRECOMPACT_INPUT)

        with patch('macf.hooks.handle_pre_compact.get_current_session_id', return_value="test-session"):
            with patch('macf.hooks.handle_pre_compact.get_cycle_number_from_events', return_value=1):
                with patch('macf.hooks.handle_pre_compact.get_breadcrumb', return_value='s_abc/c_1/g_def/p_ghi/t_123'):
                    with patch('macf.hooks.handle_pre_compact.get_token_info', return_value={}):
                        with patch('macf.hooks.handle_pre_compact.get_temporal_context', return_value={'timestamp_formatted': '2025-10-08 12:00 PM'}):
                            with patch('macf.channels.telegram.send_telegram_notification') as notify:
                                run(stdin_data)

                                text = notify.call_args.args[0]
                                assert 'Trigger: manual' in text
                                assert 'Source:' not in text

    def test_handles_errors_gracefully(self, isolated_events_log):
        """Returns error message when exception occurs."""
        with patch('macf.hooks.handle_pre_compact.get_current_session_id', side_effect=Exception("Test error")):
            result = run("")

            assert result['continue'] is True
            assert 'error' in result['systemMessage'].lower()
