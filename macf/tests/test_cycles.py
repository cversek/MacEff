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
    set_auto_mode,
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

    # NOTE: test_config_file_auto_mode_when_no_env_var removed in Cycle 314
    # Config.json path was removed in Cycle 313 (commit ce6089e) - event-first architecture

    def test_defaults_to_manual_mode_when_no_config(self, monkeypatch, isolated_events_log):
        """Returns MANUAL_MODE (False) with default source when no config found."""
        monkeypatch.delenv('MACF_AUTO_MODE', raising=False)

        # Mock find_agent_home to raise exception (no agent home found)
        with patch('macf.utils.cycles.find_agent_home', side_effect=OSError("No agent home")):
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
                with patch('macf.utils.cycles.find_agent_home', side_effect=OSError()):
                    pass

            enabled, source, confidence = detect_auto_mode("test-session")

            assert 0.0 <= confidence <= 1.0
            assert source == expected_source


class TestSetAutoMode:
    """Tests for set_auto_mode() function."""

    def test_auto_mode_emits_event(self):
        """AUTO_MODE emits mode_change event."""
        with patch('macf.agent_events_log.append_event') as mock_append:
            success, message = set_auto_mode(
                enabled=True,
                session_id="test-session",
            )

            assert success is True
            assert "AUTO_MODE" in message
            mock_append.assert_called_once()
            call_args = mock_append.call_args
            assert call_args[1]['event'] == 'mode_change'
            assert call_args[1]['data']['mode'] == 'AUTO_MODE'

    def test_manual_mode_always_allowed_without_auth(self):
        """MANUAL_MODE can be set without auth token."""
        with patch('macf.agent_events_log.append_event'):
            success, message = set_auto_mode(
                enabled=False,
                session_id="test-session",
                auth_token=None,
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

        # Invalid token should fail (before event emission)
        success, message = set_auto_mode(
            enabled=True,
            session_id="test-session",
            auth_token="invalid-token",
            agent_home=tmp_path,
        )

        assert success is False
        assert "Invalid auth token" in message

    def test_handles_errors_gracefully(self):
        """Returns error message when exceptions occur."""
        # Force an error by patching find_agent_home
        with patch('macf.utils.cycles.find_agent_home', side_effect=Exception("Error")):
            success, message = set_auto_mode(
                enabled=True,
                session_id="test-session",
                auth_token="token",
            )

            # Should handle gracefully
            assert isinstance(success, bool)
            assert isinstance(message, str)
