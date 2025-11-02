"""
Configuration management for macf tools with consciousness-aware path resolution.

This module implements the ConsciousnessConfig class following TDD specifications
from test_config.py. It provides intelligent path resolution for consciousness
artifacts across different environments (container, host, fallback).
"""

import json
import os
from pathlib import Path
from typing import Optional


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
        1. Check .claude project structure
        2. Fallback to generic agent name

        Returns:
            Detected agent name string.
        """
        # Check .claude project structure
        project_root = self._find_project_root()
        if project_root and (project_root / ".claude").exists():
            # Use project directory name
            return project_root.name

        # Fallback to generic agent name
        return "agent"

    def _find_project_root(self) -> Optional[Path]:
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
                    except Exception:
                        pass  # Fall through to fallback

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
            except Exception:
                return {}
        return {}