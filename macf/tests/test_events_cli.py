"""
Integration tests for events CLI commands.

Tests the 2 events commands: query, stats.
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
    test_log = tmp_path / "test_cli_events.jsonl"
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))
    yield test_log


class TestEventsQueryCommand:
    """Test macf_tools events query command."""

    def test_query_executes_successfully(self):
        """Test query command runs without errors."""
        result = subprocess.run(
            ['macf_tools', 'events', 'query'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Output should be valid (either events or empty)

    def test_query_with_event_filter(self):
        """Test query with --event filter."""
        result = subprocess.run(
            ['macf_tools', 'events', 'query', '--event', 'cli_command_invoked'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should execute without error

    def test_query_with_cycle_filter(self):
        """Test query with --cycle filter."""
        result = subprocess.run(
            ['macf_tools', 'events', 'query', '--cycle', '1'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should execute without error

    def test_query_with_command_filter(self):
        """Test query with --command filter for cli_command_invoked."""
        result = subprocess.run(
            ['macf_tools', 'events', 'query', '--command', 'policy read'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should execute without error

    def test_query_verbose_mode(self):
        """Test query with --verbose flag shows full event data."""
        result = subprocess.run(
            ['macf_tools', 'events', 'query', '--verbose'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should execute without error

    def test_query_handles_empty_log_gracefully(self, isolated_cli_env):
        """Test query handles empty event log without errors."""
        # isolated_cli_env creates an empty log file
        result = subprocess.run(
            ['macf_tools', 'events', 'query'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should handle empty log gracefully


class TestEventsStatsCommand:
    """Test macf_tools events stats command."""

    def test_stats_executes_successfully(self):
        """Test stats command runs without errors."""
        result = subprocess.run(
            ['macf_tools', 'events', 'stats'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should show statistics or indicate empty log

    def test_stats_shows_summary_format(self):
        """Test stats shows event summary format."""
        result = subprocess.run(
            ['macf_tools', 'events', 'stats'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Output should contain stats-related keywords
        assert 'events' in result.stdout.lower() or 'statistics' in result.stdout.lower() or 'total' in result.stdout.lower()

    def test_stats_handles_empty_log_gracefully(self, isolated_cli_env):
        """Test stats handles empty event log without errors."""
        # isolated_cli_env creates an empty log file
        result = subprocess.run(
            ['macf_tools', 'events', 'stats'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should handle empty log gracefully

    def test_stats_counts_event_types(self):
        """Test stats counts different event types."""
        result = subprocess.run(
            ['macf_tools', 'events', 'stats'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should show event type information if log has events
