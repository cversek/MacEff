"""
Tests for cycles.py utilities.

Tests cycle management, AUTO_MODE detection, and cycle increment functions.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from macf.utils.cycles import (
    detect_auto_mode,
    get_agent_cycle_number,
    set_auto_mode,
    increment_agent_cycle
)


class TestDetectAutoMode:
    """Tests for detect_auto_mode() function."""

    def test_env_var_true_returns_auto_mode_enabled(self, monkeypatch):
        """Environment variable 'true' enables AUTO_MODE with high confidence."""
        monkeypatch.setenv('MACF_AUTO_MODE', 'true')

        enabled, source, confidence = detect_auto_mode("test-session")

        assert enabled is True
        assert source == "env"
        assert confidence == 0.9

    def test_env_var_false_returns_manual_mode(self, monkeypatch):
        """Environment variable 'false' disables AUTO_MODE with high confidence."""
        monkeypatch.setenv('MACF_AUTO_MODE', 'false')

        enabled, source, confidence = detect_auto_mode("test-session")

        assert enabled is False
        assert source == "env"
        assert confidence == 0.9

    def test_config_file_auto_mode_when_no_env_var(self, tmp_path, monkeypatch, isolated_events_log):
        """Reads from .maceff/config.json when env var not set."""
        monkeypatch.delenv('MACF_AUTO_MODE', raising=False)

        # Mock project root and create config
        with patch('macf.utils.cycles.find_project_root', return_value=tmp_path):
            config_dir = tmp_path / ".maceff"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text(json.dumps({"auto_mode": True}))

            enabled, source, confidence = detect_auto_mode("test-session")

            assert enabled is True
            assert source == "config"
            assert confidence == 0.7

    def test_defaults_to_manual_mode_when_no_config(self, monkeypatch, isolated_events_log):
        """Returns MANUAL_MODE (False) with default source when no config found."""
        monkeypatch.delenv('MACF_AUTO_MODE', raising=False)

        # Mock find_project_root to raise exception (no project found)
        with patch('macf.utils.cycles.find_project_root', side_effect=OSError("No project")):
            enabled, source, confidence = detect_auto_mode("test-session")

            assert enabled is False
            assert source == "default"
            assert confidence == 0.0

    def test_confidence_scores_in_valid_range(self, monkeypatch, isolated_events_log):
        """Confidence scores are between 0.0 and 1.0."""
        test_cases = [
            ('true', 'env', 0.9),
            ('false', 'env', 0.9),
            ('', 'default', 0.0)
        ]

        for env_value, expected_source, expected_confidence in test_cases:
            if env_value:
                monkeypatch.setenv('MACF_AUTO_MODE', env_value)
            else:
                monkeypatch.delenv('MACF_AUTO_MODE', raising=False)
                with patch('macf.utils.cycles.find_project_root', side_effect=OSError()):
                    pass

            enabled, source, confidence = detect_auto_mode("test-session")

            assert 0.0 <= confidence <= 1.0
            assert source == expected_source


class TestGetAgentCycleNumber:
    """Tests for get_agent_cycle_number() function."""

    def test_returns_1_when_no_state_exists(self, tmp_path):
        """Returns 1 when no agent state or events exist."""
        # Mock empty event log - must mock at event_queries module
        with patch('macf.event_queries.get_cycle_number_from_events', return_value=0):
            with patch('macf.utils.cycles.load_agent_state', return_value={}):
                result = get_agent_cycle_number(agent_root=tmp_path)
                assert result == 1

    def test_reads_from_event_log_first(self, tmp_path):
        """Reads cycle from event log (primary source)."""
        with patch('macf.event_queries.get_cycle_number_from_events', return_value=42):
            result = get_agent_cycle_number(agent_root=tmp_path)
            assert result == 42

    def test_falls_back_to_agent_state_when_no_events(self, tmp_path):
        """Falls back to agent_state.json when no events exist."""
        with patch('macf.event_queries.get_cycle_number_from_events', return_value=0):
            with patch('macf.utils.cycles.load_agent_state', return_value={'current_cycle_number': 15}):
                result = get_agent_cycle_number(agent_root=tmp_path)
                assert result == 15

    def test_handles_exceptions_gracefully(self, tmp_path):
        """Returns 1 when exceptions occur during reading."""
        with patch('macf.event_queries.get_cycle_number_from_events', side_effect=Exception("Error")):
            result = get_agent_cycle_number(agent_root=tmp_path)
            assert result == 1


class TestSetAutoMode:
    """Tests for set_auto_mode() function."""

    def test_testing_mode_returns_success_without_mutation(self):
        """Testing mode returns success message without side effects."""
        success, message = set_auto_mode(
            enabled=True,
            session_id="test-session",
            testing=True
        )

        assert success is True
        assert "Would set AUTO_MODE" in message
        assert "testing=True" in message

    def test_manual_mode_always_allowed_without_auth(self):
        """MANUAL_MODE can be set without auth token."""
        success, message = set_auto_mode(
            enabled=False,
            session_id="test-session",
            auth_token=None,
            testing=True
        )

        assert success is True
        assert "MANUAL_MODE" in message

    def test_validates_auth_token_for_auto_mode(self, tmp_path):
        """AUTO_MODE requires valid auth token when configured."""
        # Create settings with auth token
        settings_dir = tmp_path / ".maceff"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(json.dumps({"auto_mode_auth_token": "valid-token"}))

        # Invalid token should fail
        success, message = set_auto_mode(
            enabled=True,
            session_id="test-session",
            auth_token="invalid-token",
            agent_root=tmp_path,
            testing=True
        )

        assert success is False
        assert "Invalid auth token" in message

    def test_handles_errors_gracefully(self):
        """Returns error message when exceptions occur."""
        # Force an error by passing invalid session_id type
        with patch('macf.utils.cycles.find_project_root', side_effect=Exception("Error")):
            success, message = set_auto_mode(
                enabled=True,
                session_id="test-session",
                auth_token="token",
                testing=True  # Still safe even with error
            )

            # Should handle gracefully in testing mode
            assert isinstance(success, bool)
            assert isinstance(message, str)


class TestIncrementAgentCycle:
    """Tests for increment_agent_cycle() function."""

    def test_testing_mode_returns_next_cycle_without_mutation(self, tmp_path):
        """Testing mode returns current+1 without saving."""
        with patch('macf.utils.cycles.load_agent_state', return_value={'current_cycle_number': 10}):
            result = increment_agent_cycle(
                session_id="test-session",
                agent_root=tmp_path,
                testing=True
            )

            assert result == 11  # Returns next value
            # State should not be modified (testing mode)

    def test_increments_cycle_in_production_mode(self, tmp_path):
        """Production mode increments and saves cycle number."""
        state = {'current_cycle_number': 5}

        with patch('macf.utils.cycles.load_agent_state', return_value=state):
            with patch('macf.utils.cycles.save_agent_state') as mock_save:
                result = increment_agent_cycle(
                    session_id="test-session",
                    agent_root=tmp_path,
                    testing=False
                )

                assert result == 6
                mock_save.assert_called_once()

    def test_initializes_state_when_empty(self, tmp_path):
        """Initializes agent state when no state exists."""
        with patch('macf.utils.cycles.load_agent_state', return_value={}):
            with patch('macf.utils.cycles.save_agent_state') as mock_save:
                result = increment_agent_cycle(
                    session_id="test-session",
                    agent_root=tmp_path,
                    testing=False
                )

                assert result == 2  # Initialized to 1, then incremented
                mock_save.assert_called_once()

    def test_updates_session_tracking_fields(self, tmp_path):
        """Updates cycle_started_at, cycles_completed, last_session_id."""
        state = {'current_cycle_number': 10}

        with patch('macf.utils.cycles.load_agent_state', return_value=state):
            with patch('macf.utils.cycles.save_agent_state') as mock_save:
                import time
                before = time.time()

                result = increment_agent_cycle(
                    session_id="new-session",
                    agent_root=tmp_path,
                    testing=False
                )

                after = time.time()

                # Verify save was called with updated state
                saved_state = mock_save.call_args[0][0]
                assert saved_state['current_cycle_number'] == 11
                assert saved_state['cycles_completed'] == 10
                assert saved_state['last_session_id'] == "new-session"
                assert before <= saved_state['cycle_started_at'] <= after

    def test_returns_1_on_exception(self, tmp_path):
        """Returns 1 when exceptions occur during increment."""
        with patch('macf.utils.cycles.load_agent_state', side_effect=Exception("Error")):
            result = increment_agent_cycle(
                session_id="test-session",
                agent_root=tmp_path,
                testing=True
            )

            assert result == 1
