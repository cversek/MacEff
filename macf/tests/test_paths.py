"""
Tests for path resolution functions.

Tests the three-way path semantics:
- find_maceff_root(): MacEff installation location
- find_project_root(): User's project/workspace
- find_agent_home(): Agent's persistent home (SACRED)
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from macf.utils.paths import find_maceff_root, find_project_root, find_agent_home


@pytest.fixture(autouse=True)
def clear_path_caches():
    """Clear LRU caches before each test."""
    find_maceff_root.cache_clear()
    find_project_root.cache_clear()
    find_agent_home.cache_clear()
    yield


class TestFindMaceffRoot:
    """Test find_maceff_root() - MacEff installation location."""

    def test_uses_maceff_root_dir_env_var(self, tmp_path):
        """Test MACEFF_ROOT_DIR env var takes priority."""
        # Create framework/ marker
        (tmp_path / "framework").mkdir()

        with patch.dict(os.environ, {"MACEFF_ROOT_DIR": str(tmp_path)}):
            result = find_maceff_root()
            assert result == tmp_path

    def test_maceff_root_dir_requires_framework_marker(self, tmp_path):
        """Test MACEFF_ROOT_DIR without framework/ falls through."""
        # No framework/ marker - should fall through to other methods
        with patch.dict(os.environ, {"MACEFF_ROOT_DIR": str(tmp_path)}, clear=False):
            # Will fall through and use git/discovery methods
            result = find_maceff_root()
            # Result should NOT be tmp_path since it lacks framework/
            # (actual result depends on test environment)
            assert result != tmp_path or not tmp_path.exists()

    def test_finds_framework_via_git_root(self, tmp_path, monkeypatch):
        """Test discovery via git root with framework/ marker."""
        # Clear env var
        monkeypatch.delenv("MACEFF_ROOT_DIR", raising=False)

        # Create git repo with framework/
        (tmp_path / ".git").mkdir()
        (tmp_path / "framework").mkdir()

        # Mock git command to return tmp_path
        def mock_run(*args, **kwargs):
            class Result:
                returncode = 0
                stdout = str(tmp_path)
            return Result()

        with patch("subprocess.run", mock_run):
            result = find_maceff_root()
            assert result == tmp_path


class TestFindProjectRoot:
    """Test find_project_root() - User's project/workspace."""

    def test_uses_claude_project_dir_env_var(self, tmp_path):
        """Test CLAUDE_PROJECT_DIR env var takes priority."""
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            result = find_project_root()
            assert result == tmp_path

    def test_finds_project_via_claude_markers(self, tmp_path, monkeypatch):
        """Test discovery via .claude/ or CLAUDE.md markers."""
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

        # Create git repo with Claude markers
        (tmp_path / ".git").mkdir()
        (tmp_path / ".claude").mkdir()

        def mock_run(*args, **kwargs):
            class Result:
                returncode = 0
                stdout = str(tmp_path)
            return Result()

        with patch("subprocess.run", mock_run):
            result = find_project_root()
            assert result == tmp_path

    def test_fallback_to_cwd(self, tmp_path, monkeypatch):
        """Test fallback to current working directory."""
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)

        # Mock git failing
        def mock_run(*args, **kwargs):
            class Result:
                returncode = 1
                stdout = ""
            return Result()

        with patch("subprocess.run", mock_run):
            result = find_project_root()
            assert result == tmp_path


class TestFindAgentHome:
    """Test find_agent_home() - Agent's persistent home (SACRED)."""

    def test_uses_maceff_agent_home_dir_env_var(self, tmp_path):
        """Test MACEFF_AGENT_HOME_DIR env var takes priority."""
        agent_home = tmp_path / "my_agent_home"
        agent_home.mkdir()

        with patch.dict(os.environ, {"MACEFF_AGENT_HOME_DIR": str(agent_home)}):
            result = find_agent_home()
            assert result == agent_home

    def test_creates_agent_home_if_env_var_set(self, tmp_path):
        """Test creates directory if MACEFF_AGENT_HOME_DIR set but doesn't exist."""
        agent_home = tmp_path / "new_agent_home"
        assert not agent_home.exists()

        with patch.dict(os.environ, {"MACEFF_AGENT_HOME_DIR": str(agent_home)}):
            result = find_agent_home()
            assert result == agent_home
            assert agent_home.exists()

    def test_defaults_to_home_dir(self, monkeypatch, tmp_path):
        """Test default to ~ (user home) when no env var and no project marker."""
        monkeypatch.delenv("MACEFF_AGENT_HOME_DIR", raising=False)

        # Create a directory without .maceff/agent_events_log.jsonl marker
        no_marker_dir = tmp_path / "no_marker"
        no_marker_dir.mkdir()

        # Mock Path.cwd() and Path.home() to control the detection
        with patch.object(Path, "cwd", return_value=no_marker_dir):
            with patch.object(Path, "home", return_value=tmp_path):
                result = find_agent_home()
                # Should return home directory itself (no project marker found)
                assert result == tmp_path

    def test_detects_project_via_event_log_marker(self, monkeypatch, tmp_path):
        """Test project detection via .maceff/agent_events_log.jsonl marker."""
        monkeypatch.delenv("MACEFF_AGENT_HOME_DIR", raising=False)

        # Create project with .maceff/agent_events_log.jsonl marker
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()
        maceff_dir = project_dir / ".maceff"
        maceff_dir.mkdir()
        (maceff_dir / "agent_events_log.jsonl").touch()

        # Mock cwd to be inside the project
        with patch.object(Path, "cwd", return_value=project_dir):
            result = find_agent_home()
            assert result == project_dir

    def test_agent_home_is_sacred(self):
        """Document the SACRED principle - agent continuity across projects."""
        # This is a documentation test - the principle is:
        # Agent home persists across project reassignments.
        # Event log at {MACEFF_AGENT_HOME_DIR}/agent_events_log.jsonl
        # survives when agent moves from Project A to Project B.
        #
        # Implementation: find_agent_home() returns consistent path
        # regardless of CLAUDE_PROJECT_DIR or current working directory.
        pass


class TestPathSemanticsSeparation:
    """Test that the three path functions have distinct semantics."""

    def test_different_env_vars_produce_different_results(self, tmp_path):
        """Test each function respects its own env var."""
        maceff_root = tmp_path / "maceff"
        maceff_root.mkdir()
        (maceff_root / "framework").mkdir()

        project_root = tmp_path / "project"
        project_root.mkdir()

        agent_home = tmp_path / "agent"
        agent_home.mkdir()

        env = {
            "MACEFF_ROOT_DIR": str(maceff_root),
            "CLAUDE_PROJECT_DIR": str(project_root),
            "MACEFF_AGENT_HOME_DIR": str(agent_home),
        }

        with patch.dict(os.environ, env):
            assert find_maceff_root() == maceff_root
            assert find_project_root() == project_root
            assert find_agent_home() == agent_home

            # All three are different
            assert find_maceff_root() != find_project_root()
            assert find_project_root() != find_agent_home()
            assert find_maceff_root() != find_agent_home()
