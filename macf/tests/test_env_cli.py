"""Tests for macf_tools env command."""
import json
import subprocess


class TestEnvCommand:
    """Test suite for env command."""

    def test_env_executes_successfully(self):
        """Test env command returns 0."""
        result = subprocess.run(
            ['python', '-m', 'macf.cli', 'env'],
            capture_output=True,
            text=True,
            cwd='/Users/cversek/gitwork/cversek/MacEff'
        )
        assert result.returncode == 0

    def test_env_json_valid(self):
        """Test --json outputs valid JSON."""
        result = subprocess.run(
            ['python', '-m', 'macf.cli', 'env', '--json'],
            capture_output=True,
            text=True,
            cwd='/Users/cversek/gitwork/cversek/MacEff'
        )
        assert result.returncode == 0
        # Should parse without error
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_env_json_contains_required_sections(self):
        """Test JSON output contains all required sections."""
        result = subprocess.run(
            ['python', '-m', 'macf.cli', 'env', '--json'],
            capture_output=True,
            text=True,
            cwd='/Users/cversek/gitwork/cversek/MacEff'
        )
        data = json.loads(result.stdout)

        # Check required top-level sections
        required_sections = ['versions', 'time', 'paths', 'session', 'system', 'environment', 'config']
        for section in required_sections:
            assert section in data, f"Missing required section: {section}"

    def test_env_versions_section(self):
        """Test versions section contains expected fields."""
        result = subprocess.run(
            ['python', '-m', 'macf.cli', 'env', '--json'],
            capture_output=True,
            text=True,
            cwd='/Users/cversek/gitwork/cversek/MacEff'
        )
        data = json.loads(result.stdout)

        versions = data['versions']
        assert 'macf' in versions
        assert 'claude_code' in versions
        assert 'python_path' in versions
        assert 'python_version' in versions

    def test_env_pretty_print_contains_sections(self):
        """Test pretty-print output contains section headers."""
        result = subprocess.run(
            ['python', '-m', 'macf.cli', 'env'],
            capture_output=True,
            text=True,
            cwd='/Users/cversek/gitwork/cversek/MacEff'
        )
        output = result.stdout

        # Check section headers in pretty-print
        assert 'Versions' in output
        assert 'Time' in output
        assert 'Paths' in output
        assert 'Session' in output
        assert 'System' in output
        assert 'Environment' in output
        assert 'Config' in output
