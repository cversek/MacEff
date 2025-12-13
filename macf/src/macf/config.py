"""
Configuration management for macf tools with consciousness-aware path resolution.

This module implements the ConsciousnessConfig class following TDD specifications
from test_config.py. It provides intelligent path resolution for consciousness
artifacts across different environments (container, host, fallback).
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Fallback for older Python
    except ImportError:
        tomllib = None  # TOML support not available


class ConfigurationError(Exception):
    """Exception raised for configuration-related errors."""
    pass


class ConsciousnessConfig:
    """
    Configuration for consciousness-aware operations.

    Provides intelligent path resolution for consciousness artifacts:
    - MACF_AGENT_ROOT environment variable (highest priority)
    - Container detection (/.dockerenv exists)
    - Host with .claude project detection
    - Fallback to ~/.macf/{agent}/agent/
    """

    def __init__(self, agent_name: Optional[str] = None):
        """
        Initialize configuration with optional agent name.

        Args:
            agent_name: Agent name for path resolution. If None, triggers detection.
        """
        self._detection_performed = False

        if agent_name:
            self.agent_name = agent_name
        else:
            self.agent_name = self._detect_agent()
            self._detection_performed = True

        self.agent_root = self._find_agent_root()

    def _detect_agent(self) -> str:
        """
        Detect agent name from environment.

        Detection priority:
        1. MACF_AGENT environment variable
        2. Check .claude project structure
        3. Fallback to system USER

        Returns:
            Detected agent name string.
        """
        # 1. Check MACF_AGENT environment variable
        if agent_env := os.getenv("MACF_AGENT"):
            return agent_env

        # 2. Check .claude project structure
        project_root = self._find_claude_project_root()
        if project_root:
            # Extract agent name from .claude subdirectory
            claude_dir = project_root / ".claude"
            if claude_dir.exists():
                # Look for agent-specific subdirectory
                subdirs = [d for d in claude_dir.iterdir() if d.is_dir()]
                if subdirs:
                    return subdirs[0].name

        # 3. Fallback to system USER environment variable
        return os.getenv("USER", "unknown-user")

    def _find_claude_project_root(self) -> Optional[Path]:
        """
        Find project root with .claude directory.

        Walks up directory tree looking for .claude directory.

        Returns:
            Path to project root or None if not found.
        """
        current = Path.cwd()
        while current != current.parent:
            if (current / ".claude").exists():
                return current
            current = current.parent
        return None

    def _find_project_root(self) -> Optional[Path]:
        """
        Alias for _find_claude_project_root for backward compatibility.

        Returns:
            Path to project root or None if not found.
        """
        return self._find_claude_project_root()

    def _is_container(self) -> bool:
        """Check if running in container context."""
        return Path("/.dockerenv").exists()

    def _is_host(self) -> bool:
        """Check if running in host context with project."""
        return self._find_project_root() is not None

    def _find_agent_root(self) -> Path:
        """
        Find agent root directory using detection priority.

        Detection priority (highest to lowest):
        1. MACF_AGENT_ROOT environment variable override
        2. Container detection (/.dockerenv exists)
        3. Host with .claude project
        4. Fallback to home directory

        Returns:
            Path object pointing to agent root directory.
        """

        # 1. Environment variable override (highest priority)
        if env_root := os.getenv("MACF_AGENT_ROOT"):
            return Path(env_root)

        # 2. Container detection (/.dockerenv exists)
        if self._is_container():
            user = os.getenv("USER", "user")
            return Path(f"/home/{user}/agent")

        # 3. Host with .claude project
        if project_root := self._find_project_root():
            # Use project root directly for consciousness-centric workspace
            return project_root / "agent"

        # 4. Fallback to home directory
        return Path.home() / ".macf" / self.agent_name / "agent"

    def get_public_path(self) -> Path:
        """
        Get path to public consciousness artifacts directory.

        Returns:
            Path to agent/public/ directory.
        """
        return self.agent_root / "public"

    def get_private_path(self) -> Path:
        """
        Get path to private consciousness artifacts directory.

        Returns:
            Path to agent/private/ directory.
        """
        return self.agent_root / "private"

    def get_logs_path(self) -> Path:
        """
        Get path to logs directory.

        Returns:
            Path to agent/public/logs/ directory.
        """
        return self.get_public_path() / "logs"

    def get_checkpoints_path(self) -> Path:
        """
        Get path to checkpoints directory.

        Returns:
            Path to agent/public/checkpoints/ directory.
        """
        return self.get_public_path() / "checkpoints"

    def get_reflections_path(self) -> Path:
        """
        Get path to reflections directory.

        Returns:
            Path to agent/public/reflections/ directory.
        """
        return self.get_public_path() / "reflections"

    @property
    def agent_id(self) -> str:
        """
        Get agent identifier for logging paths with multi-agent support.

        Resolution priority:
        1. Container: MACEFF_USER or USER environment variable
        2. Host: .macf/config.json moniker field
        3. Fallback: 'unknown_agent'

        Returns:
            str: Agent identifier suitable for filesystem paths
        """
        # Container context - use env vars
        if self._is_container():
            agent = os.environ.get('MACEFF_USER') or os.environ.get('USER')
            if agent:
                return agent

        # Host context - read from .maceff/config.json
        if self._is_host():
            project_root = self._find_project_root()
            if project_root:
                config_file = project_root / '.maceff' / 'config.json'
                if config_file.exists():
                    try:
                        with open(config_file) as f:
                            config = json.load(f)
                            moniker = config.get('agent_identity', {}).get('moniker')
                            if moniker:
                                return moniker
                    except Exception as e:
                        import sys
                        print(f"⚠️ MACF: Config parse failed (fallback: unknown_agent): {e}", file=sys.stderr)

        # Fallback - use unknown_agent
        return 'unknown_agent'

    def load_config(self) -> dict:
        """
        Load .macf/config.json if it exists.

        Returns:
            dict: Configuration data or empty dict if not found
        """
        config_file = Path.cwd() / '.macf' / 'config.json'
        if config_file.exists():
            try:
                with open(config_file) as f:
                    return json.load(f)
            except Exception as e:
                import sys
                print(f"⚠️ MACF: Config load failed (fallback: empty config): {e}", file=sys.stderr)
                return {}
        return {}

    def _load_settings(self) -> Dict[str, Any]:
        """
        Load settings from TOML configuration file with environment variable overrides.

        Returns:
            dict: Configuration settings with defaults
        """
        # Default settings
        settings = {
            "consciousness": {
                "session_retention_days": 7,
                "checkpoint_format": "structured"
            },
            "paths": {
                "temp_dir": "/tmp/macf",
                "logs_dir": "logs"
            },
            "features": {
                "reflection_enabled": True,
                "strategic_checkpoints": True
            }
        }

        # Try to load from TOML file
        config_file = self.agent_root / "config.toml"
        if config_file.exists() and tomllib:
            try:
                with open(config_file, 'rb') as f:
                    file_settings = tomllib.load(f)
                    # Merge file settings into defaults
                    for section, values in file_settings.items():
                        if section in settings:
                            settings[section].update(values)
                        else:
                            settings[section] = values
            except Exception as e:
                raise ConfigurationError(f"Invalid TOML in {config_file}: {e}")

        # Apply environment variable overrides
        if retention_days := os.getenv("MACF_SESSION_RETENTION_DAYS"):
            try:
                settings["consciousness"]["session_retention_days"] = int(retention_days)
            except ValueError:
                pass

        return settings

    @staticmethod
    def _validate_agent_name(agent_name: str) -> bool:
        """
        Validate agent name format.

        Agent names must:
        - Be non-empty strings
        - Contain only valid filesystem characters
        - Not contain path separators

        Args:
            agent_name: Agent name to validate

        Returns:
            bool: True if valid

        Raises:
            ConfigurationError: If agent name is invalid
        """
        if not agent_name:
            raise ConfigurationError("Agent name cannot be empty")

        if '/' in agent_name or '\\' in agent_name:
            raise ConfigurationError(
                f"Agent name '{agent_name}' cannot contain path separators"
            )

        return True

    def _validate_path_permissions(self, path: Path) -> None:
        """
        Validate that path is writable.

        Args:
            path: Path to validate

        Raises:
            ConfigurationError: If path is not writable
        """
        if not os.access(path, os.W_OK):
            raise ConfigurationError(
                f"Path '{path}' is not writable"
            )