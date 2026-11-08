"""Tests for macf_tools env command."""
import json
import subprocess
from pathlib import Path

# Derive repo root from test file location (works on any platform)
REPO_ROOT = str(Path(__file__).resolve().parents[1])


class TestEnvCommand:
    """Test suite for env command."""

    def test_env_executes_successfully(self):
        """Test env command returns 0."""
        result = subprocess.run(
            ['python', '-m', 'macf.cli', 'env'],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )
        assert result.returncode == 0

    def test_env_json_valid(self):
        """Test --json outputs valid JSON."""
        result = subprocess.run(
            ['python', '-m', 'macf.cli', 'env', '--json'],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
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
            cwd=REPO_ROOT
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
            cwd=REPO_ROOT
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
            cwd=REPO_ROOT
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


def _identity_home(tmp_path, name="Example2", uuid="0a1b2c3d-0000-4000-8000-000000000000"):
    home = tmp_path / "home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": name}}))
    (home / ".maceff_primary_agent.id").write_text(uuid + "\n")
    return home


def test_env_names_the_card_as_the_daemon_reads_it_whatever_maceff_agent_name_says(tmp_path, monkeypatch):
    """#924: in a container MACEFF_AGENT_NAME is the agents.yaml key, so the process's identity
    read ``example2_0a1b2c`` while the daemon, reading only the home, said ``Example2_0a1b2c``.
    env now reports the home's card, and keeps the other reading beside it only where it differs."""
    from macf.pd.names import agent_card
    from macf.utils import identity
    home = _identity_home(tmp_path)
    monkeypatch.setattr(identity, "get_agent_identity", lambda: "example2_0a1b2c")
    got = identity.reported_identity(home)
    assert got == {"agent_id": agent_card(home), "source": "home", "process_identity": "example2_0a1b2c"}
    assert got["agent_id"] == "Example2_0a1b2c"
    monkeypatch.setattr(identity, "get_agent_identity", lambda: "Example2_0a1b2c")
    assert identity.reported_identity(home)["process_identity"] is None      # nothing to explain
    # A home that names no agent falls back to the process's reading, and says where it came from.
    monkeypatch.setattr(identity, "agent_name_source", lambda: "env")
    assert identity.reported_identity(tmp_path / "empty") == {"agent_id": "Example2_0a1b2c", "source": "env",
                                                              "process_identity": None}


def test_env_prints_the_homes_card_in_a_container_shaped_environment(tmp_path):
    home = _identity_home(tmp_path)
    import os
    env = {**os.environ, "MACEFF_AGENT_HOME_DIR": str(home), "MACEFF_AGENT_NAME": "example2"}
    result = subprocess.run(['python', '-m', 'macf.cli', 'env', '--json'], capture_output=True, text=True,
                            cwd=REPO_ROOT, env=env)
    assert result.returncode == 0, result.stderr
    ident = json.loads(result.stdout)["identity"]
    assert ident["agent_id"] == "Example2_0a1b2c" and ident["source"] == "home"
