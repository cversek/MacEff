"""
Integration tests for breadcrumb CLI command.

Tests the breadcrumb command: generate breadcrumbs for current context.
Uses subprocess to invoke macf_tools CLI as real integration tests.

CRITICAL: All subprocess tests must use isolated_cli_env fixture to prevent
polluting production event logs with cli_command_invoked events.
"""

import json
import subprocess
import pytest


@pytest.fixture(autouse=True)
def isolated_cli_env(tmp_path, monkeypatch):
    """Isolate CLI subprocess calls from production event logs.

    All CLI invocations emit cli_command_invoked events. Without isolation,
    tests pollute the production agent_events_log.jsonl file.

    This fixture is autouse=True so ALL tests in this module get isolation.
    """
    test_log = tmp_path / "test_cli_breadcrumb.jsonl"
    monkeypatch.setenv("MACF_EVENTS_LOG_PATH", str(test_log))
    yield test_log


class TestBreadcrumbCommand:
    """Test macf_tools breadcrumb command."""

    def test_breadcrumb_executes_successfully(self):
        """Test breadcrumb command runs without errors."""
        result = subprocess.run(
            ['macf_tools', 'breadcrumb'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should output a breadcrumb string
        assert len(result.stdout.strip()) > 0

    def test_breadcrumb_format_structure(self):
        """Test breadcrumb has expected s/c/g/p/t structure."""
        result = subprocess.run(
            ['macf_tools', 'breadcrumb'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        breadcrumb = result.stdout.strip()

        # Should contain breadcrumb component separators
        assert '/' in breadcrumb
        # Should start with s_ (session component)
        assert breadcrumb.startswith('s_')

    def test_breadcrumb_json_output(self):
        """Test breadcrumb --json flag outputs valid JSON with components."""
        result = subprocess.run(
            ['macf_tools', 'breadcrumb', '--json'],
            capture_output=True, text=True
        )

        assert result.returncode == 0

        # Parse JSON output
        data = json.loads(result.stdout)

        # Verify structure
        assert 'breadcrumb' in data
        assert 'components' in data

        # Verify breadcrumb is a string
        assert isinstance(data['breadcrumb'], str)

        # Verify components is a dict
        assert isinstance(data['components'], dict)

    def test_breadcrumb_json_components(self):
        """Test --json output includes expected breadcrumb components."""
        result = subprocess.run(
            ['macf_tools', 'breadcrumb', '--json'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)

        components = data['components']

        # Should have session component (always present)
        assert 'session_id' in components
        # Other components (cycle, git, prompt, timestamp) may be present
        # depending on context, but session is always there

    def test_breadcrumb_consistent_output(self):
        """Test breadcrumb generates consistent format across invocations."""
        # Run twice in quick succession
        result1 = subprocess.run(
            ['macf_tools', 'breadcrumb'],
            capture_output=True, text=True
        )
        result2 = subprocess.run(
            ['macf_tools', 'breadcrumb'],
            capture_output=True, text=True
        )

        assert result1.returncode == 0
        assert result2.returncode == 0

        # Both should have same structure (same session, similar format)
        breadcrumb1 = result1.stdout.strip()
        breadcrumb2 = result2.stdout.strip()

        # Both should start with same session
        session1 = breadcrumb1.split('/')[0]
        session2 = breadcrumb2.split('/')[0]
        assert session1 == session2
