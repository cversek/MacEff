"""
Integration tests for todos CLI commands.

Tests the 4 todos commands: list, status, auth-collapse, auth-status.
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
    test_log = tmp_path / "test_cli_todos.jsonl"
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))
    yield test_log


class TestTodosListCommand:
    """Test macf_tools todos list command."""

    def test_list_executes_successfully(self):
        """Test list command runs without errors."""
        result = subprocess.run(
            ['macf_tools', 'todos', 'list'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Output should be valid (either todos or "No todos_updated events found")

    def test_list_handles_empty_events_gracefully(self, isolated_cli_env):
        """Test list handles empty event log without errors."""
        # isolated_cli_env creates an empty log file
        result = subprocess.run(
            ['macf_tools', 'todos', 'list'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'No todos_updated events found' in result.stdout


class TestTodosStatusCommand:
    """Test macf_tools todos status command."""

    def test_status_executes_successfully(self):
        """Test status command runs without errors."""
        result = subprocess.run(
            ['macf_tools', 'todos', 'status'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should show status or indicate no events

    def test_status_handles_empty_events_gracefully(self, isolated_cli_env):
        """Test status handles empty event log without errors."""
        result = subprocess.run(
            ['macf_tools', 'todos', 'status'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'No todos_updated events found' in result.stdout


class TestTodosAuthCollapseCommand:
    """Test macf_tools todos auth-collapse command."""

    def test_auth_collapse_validates_reduction(self, isolated_cli_env):
        """Test auth-collapse rejects invalid from/to counts."""
        # Test expansion (to >= from) is rejected
        result = subprocess.run(
            ['macf_tools', 'todos', 'auth-collapse', '--from', '10', '--to', '15'],
            capture_output=True, text=True
        )

        assert result.returncode == 1
        assert 'must be less than' in result.stdout

    def test_auth_collapse_succeeds_with_valid_reduction(self, isolated_cli_env):
        """Test auth-collapse succeeds with valid collapse (from > to)."""
        result = subprocess.run(
            ['macf_tools', 'todos', 'auth-collapse', '--from', '20', '--to', '15'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'Collapse authorized' in result.stdout
        assert '20' in result.stdout and '15' in result.stdout


class TestTodosAuthStatusCommand:
    """Test macf_tools todos auth-status command."""

    def test_auth_status_handles_no_authorization(self, isolated_cli_env):
        """Test auth-status handles empty state gracefully."""
        result = subprocess.run(
            ['macf_tools', 'todos', 'auth-status'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'No pending collapse authorization' in result.stdout
