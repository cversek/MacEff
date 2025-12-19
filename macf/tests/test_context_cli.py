"""
Integration tests for context CLI command.

Tests the `macf_tools context` command for token/CLUAC awareness.
Uses subprocess to invoke macf_tools CLI as real integration tests.

CRITICAL: All subprocess tests must use isolated_cli_env fixture to prevent
polluting production event logs with cli_command_invoked events.
"""

import json
import subprocess
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolated_cli_env(tmp_path, monkeypatch):
    """Isolate CLI subprocess calls from production event logs.

    All CLI invocations emit cli_command_invoked events. Without isolation,
    tests pollute the production agent_events_log.jsonl file.

    This fixture is autouse=True so ALL tests in this module get isolation.
    """
    test_log = tmp_path / "test_cli_context.jsonl"
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))
    yield test_log


class TestContextCommand:
    """Test macf_tools context command."""

    def test_context_executes_successfully(self):
        """Test context command runs without errors."""
        result = subprocess.run(
            ['macf_tools', 'context'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should show token usage information

    def test_context_shows_expected_fields(self):
        """Test context command shows expected token/CLUAC fields."""
        result = subprocess.run(
            ['macf_tools', 'context'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Output should contain key CLUAC-related terms
        output_lower = result.stdout.lower()
        assert 'token' in output_lower or 'cluac' in output_lower

    def test_context_json_output(self):
        """Test context command JSON output is valid."""
        result = subprocess.run(
            ['macf_tools', 'context', '--json'],
            capture_output=True, text=True
        )

        assert result.returncode == 0

        # Should be valid JSON
        data = json.loads(result.stdout)

        # Should contain expected fields
        assert 'tokens_used' in data
        assert 'tokens_remaining' in data
        assert 'cluac_level' in data

    def test_context_json_field_types(self):
        """Test context JSON output has correct field types."""
        result = subprocess.run(
            ['macf_tools', 'context', '--json'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)

        # Verify numeric fields
        assert isinstance(data['tokens_used'], int)
        assert isinstance(data['tokens_remaining'], int)
        assert isinstance(data['cluac_level'], int)
        assert isinstance(data['percentage_used'], (int, float))

    def test_context_with_session_parameter(self):
        """Test context command accepts --session parameter."""
        result = subprocess.run(
            ['macf_tools', 'context', '--session', 'test-session-id'],
            capture_output=True, text=True
        )

        # Should execute without crashing (may not find session)
        # Don't assert returncode == 0 since session might not exist
        assert result.returncode in [0, 1]
