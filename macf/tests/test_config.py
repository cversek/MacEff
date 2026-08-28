"""
Test specifications for macf.config module.

This module tests the configuration management system including:
- Agent name detection and resolution
- Path resolution in different environments
- TOML settings loading with proper precedence
- Environment variable overrides

Following TDD principles - these tests define the expected behavior
for the configuration module that will be implemented.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import pytest

# Import consciousness config classes
from macf.config import ConsciousnessConfig, ConfigurationError


class TestConsciousnessConfig:
    """Test suite for the ConsciousnessConfig class."""

    def test_init_with_explicit_agent_name(self, mock_config):
        """
        Test configuration initialization with explicit agent name.

        When an agent name is explicitly provided, the config should:
        - Use that agent name directly
        - Skip agent detection logic
        - Proceed to path resolution
        """
        config = ConsciousnessConfig(agent_name="test-agent")
        assert config.agent_name == "test-agent"
        assert not config._detection_performed

    def test_init_without_agent_name_triggers_detection(self, mock_config):
        """
        Test configuration initialization without agent name triggers detection.

        When no agent name is provided, the config should:
        - Attempt to detect agent name from environment
        - Set detection_performed flag
        - Use detected name or fallback
        """
        with patch.object(ConsciousnessConfig, '_detect_agent') as mock_detect:
            mock_detect.return_value = "detected-agent"
            config = ConsciousnessConfig()

        mock_detect.assert_called_once()
        assert config.agent_name == "detected-agent"
        assert config._detection_performed


class TestAgentDetection:
    """Test suite for agent name detection logic."""

    def test_detect_agent_from_claude_project_dir(self, temp_claude_project, monkeypatch):
        """
        Test agent detection from .claude project directory.

        When running in a .claude project directory, should:
        - Extract agent name from directory structure
        - Use project-specific configuration
        """
        # Clear MACF_AGENT to ensure project detection is used
        monkeypatch.delenv("MACF_AGENT", raising=False)
        monkeypatch.delenv("MACF_AGENT_ROOT", raising=False)

        # Mock both _find_claude_project_root and _find_project_root
        with patch.object(ConsciousnessConfig, '_find_claude_project_root', return_value=temp_claude_project):
            with patch.object(ConsciousnessConfig, '_find_project_root', return_value=temp_claude_project):
                config = ConsciousnessConfig()
                agent_name = config.agent_name

        assert agent_name == "test-project-agent"

    def test_detect_agent_from_environment_variable(self, monkeypatch):
        """
        Test agent detection from MACF_AGENT environment variable.

        When MACF_AGENT is set, should:
        - Use that value as agent name
        - Skip other detection methods
        """
        monkeypatch.setenv("MACF_AGENT", "env-specified-agent")
        config = ConsciousnessConfig()
        agent_name = config._detect_agent()

        assert agent_name == "env-specified-agent"

    def test_detect_agent_fallback_to_system_user(self, monkeypatch):
        """
        Test agent detection fallback to system user.

        When no other detection method works, should:
        - Use system username as fallback
        - Ensure non-empty result
        """
        monkeypatch.delenv("MACF_AGENT", raising=False)
        config = ConsciousnessConfig()

        with patch.object(config, '_find_claude_project_root', return_value=None):
            agent_name = config._detect_agent()

        assert agent_name is not None
        assert len(agent_name) > 0
        assert agent_name == os.getenv("USER", "unknown-user")


class TestPathResolution:
    """Test suite for path resolution in different environments."""

    def test_find_agent_root_in_container_environment(self, monkeypatch):
        """
        Test path resolution in container environment.

        When running in container (/.dockerenv exists), should:
        - Use /home/{user}/agent/ path structure
        - Create directories if they don't exist
        - Return absolute path
        """
        monkeypatch.setenv("USER", "testuser")
        monkeypatch.delenv("MACF_AGENT_ROOT", raising=False)

        # Mock _is_container to return True and _find_project_root to return None
        with patch.object(ConsciousnessConfig, '_is_container', return_value=True):
            with patch.object(ConsciousnessConfig, '_find_project_root', return_value=None):
                config = ConsciousnessConfig(agent_name="testuser")
                agent_root = config.agent_root

        expected_path = Path("/home/testuser/agent")
        assert agent_root == expected_path

    def test_find_agent_root_in_host_environment(self, temp_claude_project, monkeypatch):
        """
        Test path resolution in host environment with .claude ancestor.

        When running in host with .claude project directory, should:
        - Find .claude directory in ancestors
        - Use project_root/agent/ structure
        - Return project-relative path

        The cwd walk is a FALLBACK, so this asserts it only with no declared
        agent home. That precondition used to hold by accident; it is stated
        now because a declared home outranks the walk (#252).
        """
        monkeypatch.delenv("MACF_AGENT_ROOT", raising=False)
        monkeypatch.delenv("MACEFF_AGENT_HOME_DIR", raising=False)

        with patch.object(ConsciousnessConfig, '_is_container', return_value=False):
            with patch.object(ConsciousnessConfig, '_find_project_root', return_value=temp_claude_project):
                config = ConsciousnessConfig(agent_name="test-agent")
                agent_root = config.agent_root

        # Should use project_root/agent structure
        expected_path = temp_claude_project / "agent"
        assert agent_root == expected_path

    def test_find_agent_root_fallback_to_home(self, monkeypatch):
        """
        Test path resolution fallback to home directory.

        When no container or project environment detected, should:
        - Use ~/.macf/{agent}/agent/ structure
        - Create in user home directory
        - Ensure path is writable

        Last resort: reached only when nothing is declared and nothing is found.
        """
        monkeypatch.delenv("MACF_AGENT_ROOT", raising=False)
        monkeypatch.delenv("MACEFF_AGENT_HOME_DIR", raising=False)

        with patch.object(ConsciousnessConfig, '_is_container', return_value=False):
            with patch.object(ConsciousnessConfig, '_find_project_root', return_value=None):
                with patch.object(Path, 'home', return_value=Path("/home/testuser")):
                    config = ConsciousnessConfig(agent_name="test-agent")
                    agent_root = config.agent_root

        expected_path = Path("/home/testuser/.macf/test-agent/agent")
        assert agent_root == expected_path

    def test_find_agent_root_with_env_override(self, monkeypatch):
        """
        Test path resolution with MACF_AGENT_ROOT override.

        When MACF_AGENT_ROOT is set, should:
        - Use that path directly
        - Skip environment detection
        - Validate path is absolute
        """
        override_path = "/custom/agent/root"
        monkeypatch.setenv("MACF_AGENT_ROOT", override_path)

        config = ConsciousnessConfig(agent_name="test-agent")
        agent_root = config._find_agent_root()

        assert agent_root == Path(override_path)

    def test_declared_agent_home_outranks_the_cwd_walk(self, tmp_path, monkeypatch):
        """A declared home wins over wherever the process happens to be.

        `utils.paths.find_agent_home` documents MACEFF_AGENT_HOME_DIR as
        "explicit configuration takes precedence"; this resolver did not consult
        it, so a caller arriving through ConsciousnessConfig resolved by the
        launch directory with the declared home set and ignored.

        Two things followed, and the second is why this test exists rather than
        a docs fix. `macf_tools time` reported an agent as having no checkpoints
        depending on where it was invoked from. And the suite's autouse
        isolation fixture works by setting this variable — so anything resolved
        through here was never isolated, and would have written wherever the
        walk landed.
        """
        declared = tmp_path / "declared_home"
        declared.mkdir()
        elsewhere = tmp_path / "somewhere_else"
        (elsewhere / ".claude").mkdir(parents=True)

        monkeypatch.delenv("MACF_AGENT_ROOT", raising=False)
        monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(declared))
        from macf.utils.paths import find_agent_home
        find_agent_home.cache_clear()

        with patch.object(ConsciousnessConfig, '_is_container', return_value=False):
            # A cwd walk that WOULD succeed, to prove precedence rather than
            # absence: the walk must lose while it is still able to answer.
            with patch.object(ConsciousnessConfig, '_find_project_root', return_value=elsewhere):
                agent_root = ConsciousnessConfig(agent_name="test-agent").agent_root

        find_agent_home.cache_clear()
        assert agent_root == declared / "agent", (
            "the declared agent home lost to the launch directory"
        )


class TestTOMLSettingsLoading:
    """Test suite for TOML configuration file loading."""

    def test_load_settings_with_valid_toml(self, temp_config_file):
        """
        Test loading valid TOML configuration file.

        When valid config.toml exists, should:
        - Parse TOML content correctly
        - Load all sections and values
        - Handle nested configuration structures
        """
        config_content = """
        [consciousness]
        session_retention_days = 7
        checkpoint_format = "structured"

        [paths]
        temp_dir = "/tmp/macf"
        logs_dir = "logs"

        [features]
        reflection_enabled = true
        strategic_checkpoints = true
        """

        with patch("builtins.open", mock_open(read_data=config_content)):
            config = ConsciousnessConfig(agent_name="test-agent")
            settings = config._load_settings()

        assert settings["consciousness"]["session_retention_days"] == 7
        assert settings["consciousness"]["checkpoint_format"] == "structured"
        assert settings["features"]["reflection_enabled"] is True

    def test_load_settings_with_missing_file(self, temp_dir):
        """
        Test loading settings when config file doesn't exist.

        When config.toml doesn't exist, should:
        - Return default configuration structure
        - Not raise exceptions
        - Provide sensible defaults for all required values
        """
        config = ConsciousnessConfig(agent_name="test-agent")

        with patch.object(config, 'agent_root', temp_dir):
            settings = config._load_settings()

        # Should return defaults, not empty dict
        assert "consciousness" in settings
        assert "paths" in settings
        assert settings["consciousness"]["session_retention_days"] == 7

    def test_load_settings_with_invalid_toml(self, temp_dir, monkeypatch):
        """
        Test loading settings with malformed TOML.

        When config.toml contains syntax errors, should:
        - Raise ConfigurationError with helpful message
        - Include file path in error
        - Not crash the application
        """
        invalid_content = """
        [consciousness
        missing_closing_bracket = true
        """

        # Ensure tomllib is available for this test
        import macf.config
        if macf.config.tomllib is None:
            pytest.skip("tomllib not available - cannot test TOML parsing errors")

        config = ConsciousnessConfig(agent_name="test-agent")

        # Mock the config file to exist and contain invalid TOML
        with patch.object(Path, 'exists', return_value=True):
            with patch("builtins.open", mock_open(read_data=invalid_content)):
                with pytest.raises(ConfigurationError) as exc_info:
                    config._load_settings()

        assert "Invalid TOML" in str(exc_info.value)
        assert "config.toml" in str(exc_info.value)

    def test_settings_precedence_env_over_file(self, monkeypatch, temp_config_file):
        """
        Test that environment variables override file settings.

        When both config file and env vars are present, should:
        - Use env var values over file values
        - Only override specific keys that have env vars
        - Keep file values for keys without env vars
        """
        config_content = """
        [consciousness]
        session_retention_days = 7
        checkpoint_format = "structured"
        """

        monkeypatch.setenv("MACF_SESSION_RETENTION_DAYS", "14")

        with patch("builtins.open", mock_open(read_data=config_content)):
            config = ConsciousnessConfig(agent_name="test-agent")
            settings = config._load_settings()

        # Env var should override
        assert settings["consciousness"]["session_retention_days"] == 14
        # File value should remain
        assert settings["consciousness"]["checkpoint_format"] == "structured"


class TestConfigurationValidation:
    """Test suite for configuration validation logic."""

    def test_validate_agent_name_format(self):
        """
        Test validation of agent name format.

        Agent names should:
        - Be non-empty strings
        - Contain only valid filesystem characters
        - Not contain path separators
        """
        # Valid names
        assert ConsciousnessConfig._validate_agent_name("test-agent")
        assert ConsciousnessConfig._validate_agent_name("DevOpsEng")
        assert ConsciousnessConfig._validate_agent_name("agent_01")

        # Invalid names
        with pytest.raises(ConfigurationError):
            ConsciousnessConfig._validate_agent_name("")
        with pytest.raises(ConfigurationError):
            ConsciousnessConfig._validate_agent_name("agent/with/slash")
        with pytest.raises(ConfigurationError):
            ConsciousnessConfig._validate_agent_name("agent\\with\\backslash")

    def test_validate_path_permissions(self, temp_dir):
        """
        Test validation of path permissions.

        Agent root paths should:
        - Be writable by current user
        - Allow directory creation
        - Have appropriate permissions for logs/checkpoints
        """
        config = ConsciousnessConfig(agent_name="test-agent")

        # Should not raise for writable directory
        config._validate_path_permissions(temp_dir)

        # Should raise for read-only directory
        readonly_dir = temp_dir / "readonly"
        readonly_dir.mkdir(mode=0o444)

        with pytest.raises(ConfigurationError):
            config._validate_path_permissions(readonly_dir)


# Test Fixtures and Utilities

@pytest.fixture
def mock_config():
    """Mock configuration for basic testing."""
    return {
        "consciousness": {
            "session_retention_days": 7,
            "checkpoint_format": "structured"
        },
        "paths": {
            "temp_dir": "/tmp/macf",
            "logs_dir": "logs"
        },
        "features": {
            "reflection_enabled": True
        }
    }

@pytest.fixture
def temp_claude_project(tmp_path):
    """Create temporary .claude project structure."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    agent_dir = claude_dir / "test-project-agent"
    agent_dir.mkdir()

    return tmp_path  # Return project root, not .claude directory

@pytest.fixture
def mock_container_env(monkeypatch):
    """Mock container environment indicators."""
    monkeypatch.setenv("USER", "testuser")

    with patch('os.path.exists') as mock_exists:
        mock_exists.side_effect = lambda p: p == "/.dockerenv"
        yield

@pytest.fixture
def temp_config_file(tmp_path):
    """Create temporary config file for testing."""
    config_file = tmp_path / "config.toml"
    return config_file

@pytest.fixture
def temp_dir(tmp_path):
    """Provide temporary directory for testing."""
    return tmp_path


class TestConsciousnessArtifactPaths:
    """checkpoints/reflections paths must point where the artifacts are written (#116)."""

    def test_checkpoints_path_resolves_under_private(self):
        config = ConsciousnessConfig(agent_name="test-agent")
        path = config.get_checkpoints_path()
        # Artifacts are written under agent/private/, not public.
        assert path == config.get_private_path() / "checkpoints"
        assert path.parent.name == "private"
        assert "public" not in path.parts

    def test_reflections_path_resolves_under_private(self):
        config = ConsciousnessConfig(agent_name="test-agent")
        path = config.get_reflections_path()
        assert path == config.get_private_path() / "reflections"
        assert path.parent.name == "private"
        assert "public" not in path.parts