"""
Integration tests for policy CLI commands.

Tests the 4 policy commands: manifest, search, list, ca-types.
Uses subprocess to invoke macf_tools CLI as real integration tests.

CRITICAL: All subprocess tests must use isolated_cli_env fixture to prevent
polluting production event logs with cli_command_invoked events.
"""

import json
import os
import subprocess
import tempfile
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


class TestPolicyManifestCommand:
    """Test macf_tools policy manifest command."""

    def test_manifest_summary_format(self):
        """Test manifest command with summary format (default)."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'manifest', '--format=summary'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'Policy Manifest Summary' in result.stdout
        assert 'Version:' in result.stdout

    def test_manifest_json_format(self):
        """Test manifest command with JSON format."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'manifest', '--format=json'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should be valid JSON
        manifest = json.loads(result.stdout)
        assert isinstance(manifest, dict)
        # If manifest has content, version should be present
        if manifest:
            assert 'version' in manifest

    def test_manifest_shows_active_layers(self):
        """Test that summary shows active layers if configured."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'manifest', '--format=summary'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'Active Layers:' in result.stdout


class TestPolicySearchCommand:
    """Test macf_tools policy search command."""

    def test_search_finds_keyword(self):
        """Test search command finds keywords in policies."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'search', 'compaction'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'Search results for' in result.stdout
        assert 'compaction' in result.stdout.lower()

    def test_search_shows_match_count(self):
        """Test search shows number of matches."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'search', 'context'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'matches' in result.stdout

    def test_search_no_matches_graceful(self):
        """Test search handles no matches gracefully."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'search', 'xyznonexistentkeyword123'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'No matches found' in result.stdout or '0 matches' in result.stdout


class TestPolicyListCommand:
    """Test macf_tools policy list command."""

    def test_list_all_policies(self):
        """Test list command shows all policies by default."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'list'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'policies' in result.stdout.lower()
        # Should show base/ and lang/ directories
        assert 'base/' in result.stdout.lower()

    def test_list_with_category_filter(self):
        """Test list with category filter argument."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'list', '--category=development'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should filter to development category policies
        assert 'policies' in result.stdout.lower()

    def test_list_lang_directory(self):
        """Test list shows language directory."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'list'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should show lang/ directory in output
        assert 'lang/' in result.stdout.lower()


class TestPolicyCaTypesCommand:
    """Test macf_tools policy ca-types command."""

    def test_ca_types_shows_emojis(self):
        """Test ca-types shows CA types with emojis."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'ca-types'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert 'Consciousness Artifact' in result.stdout
        # Should have at least one emoji (if any CA types configured)
        # Common ones: 🔬 🧪 📊 💭 🔖 🗺️ ❤️

    def test_ca_types_graceful_empty(self):
        """Test ca-types handles no configured types gracefully."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'ca-types'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should either show types or "No CA types configured"
        assert 'CA' in result.stdout or 'Consciousness' in result.stdout


class TestPolicyReadSectionCommand:
    """Test macf_tools policy read --section hierarchical parsing."""

    def test_section_includes_subsections(self):
        """Test --section 10 includes 10.1 and 10.2 subsections."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'read', 'todo_hygiene', '--section', '10'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should include parent section 10
        assert '10.' in result.stdout
        # Should include subsection 10.1
        assert '10.1' in result.stdout
        # Should include subsection 10.2
        assert '10.2' in result.stdout
        # Should NOT include section 11
        assert '### 11.' not in result.stdout

    def test_subsection_excludes_siblings(self):
        """Test --section 10.1 excludes 10.2 sibling."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'read', 'todo_hygiene', '--section', '10.1'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should include subsection 10.1
        assert '10.1' in result.stdout
        # Should NOT include sibling 10.2
        assert '#### 10.2' not in result.stdout

    def test_section_1_not_matches_10(self):
        """Test --section 1 does NOT match section 10 (edge case)."""
        result = subprocess.run(
            ['macf_tools', 'policy', 'read', 'todo_hygiene', '--section', '1'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Check that section 10 content is NOT in output
        # Section 10 has specific text "TODO Backup Protocol"
        assert 'TODO Backup Protocol' not in result.stdout

    def test_section_ignores_code_block_comments(self):
        """Test --section ignores # comments inside code blocks."""
        # Section 10 has bash code blocks with # comments
        # These should not break section parsing
        result = subprocess.run(
            ['macf_tools', 'policy', 'read', 'todo_hygiene', '--section', '10'],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should capture content all the way through 10.2
        # (bug before fix: code block # comments caused early termination)
        assert '10.2' in result.stdout
        assert 'Manual Backup' in result.stdout or 'LEGACY' in result.stdout
