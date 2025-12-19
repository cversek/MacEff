"""
Integration tests for time CLI command.

Tests the time command which provides temporal awareness.
Uses subprocess to invoke macf_tools CLI as real integration tests.

CRITICAL: All subprocess tests must use isolated_cli_env fixture to prevent
polluting production event logs with cli_command_invoked events.
"""

import subprocess
from datetime import datetime
import pytest


@pytest.fixture(autouse=True)
def isolated_cli_env(tmp_path, monkeypatch):
    """Isolate CLI subprocess calls from production event logs.

    All CLI invocations emit cli_command_invoked events. Without isolation,
    tests pollute the production agent_events_log.jsonl file.

    This fixture is autouse=True so ALL tests in this module get isolation.
    """
    test_log = tmp_path / "test_cli_time.jsonl"
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))
    yield test_log


class TestTimeCommand:
    """Test macf_tools time command."""

    def test_time_executes_successfully(self):
        """Test time command runs without errors."""
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert result.stdout.strip()  # Should produce output

    def test_time_outputs_iso8601_format(self):
        """Test time outputs valid ISO 8601 timestamp."""
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        timestamp = result.stdout.strip()

        # Should be parseable as ISO 8601
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            pytest.fail(f"Output '{timestamp}' is not valid ISO 8601 format")

    def test_time_includes_timezone(self):
        """Test time output includes timezone information."""
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        timestamp = result.stdout.strip()

        # ISO 8601 with timezone should have + or - offset
        assert '+' in timestamp or '-' in timestamp or timestamp.endswith('Z')

    def test_time_is_current(self):
        """Test time output is reasonably current (within 5 seconds)."""
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        timestamp_str = result.stdout.strip()
        timestamp = datetime.fromisoformat(timestamp_str)
        now = datetime.now(timestamp.tzinfo)

        # Should be within 5 seconds of current time
        diff = abs((now - timestamp).total_seconds())
        assert diff < 5, f"Timestamp difference {diff}s exceeds 5s threshold"

    def test_time_no_stderr_output(self):
        """Test time command produces no error output."""
        result = subprocess.run(
            ['macf_tools', 'time'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert not result.stderr  # Should have no error output
