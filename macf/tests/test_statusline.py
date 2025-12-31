"""
Tests for statusline formatting utilities.

Tests cover:
- Token formatting with 'k' suffix
- Statusline string formatting
- Project detection from env vars and filesystem
- Statusline data gathering integration
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from macf.utils.statusline import (
    format_tokens,
    format_statusline,
    detect_project,
    get_statusline_data
)


class TestFormatTokens:
    """Test token count formatting with 'k' suffix."""

    def test_large_values(self):
        """Large values (>= 10k) get 'k' suffix."""
        assert format_tokens(60000) == "60k"
        assert format_tokens(200000) == "200k"
        assert format_tokens(155000) == "155k"

    def test_small_values(self):
        """Small values (< 10k) remain numeric."""
        assert format_tokens(9500) == "9500"
        assert format_tokens(5000) == "5000"
        assert format_tokens(0) == "0"

    def test_boundary_value(self):
        """10k threshold is exact."""
        assert format_tokens(10000) == "10k"
        assert format_tokens(9999) == "9999"

    def test_truncation(self):
        """Formatting truncates fractional k values."""
        assert format_tokens(15500) == "15k"  # 15.5k -> 15k
        assert format_tokens(99999) == "99k"  # 99.999k -> 99k


class TestFormatStatusline:
    """Test statusline string formatting."""

    def test_full_statusline_with_project(self):
        """Full statusline with all fields."""
        result = format_statusline("manny", "NeuroVEP", "Container Linux", 60000, 200000, 70)
        assert result == "manny | NeuroVEP | Container Linux | 60k/200k CLUAC 70"

    def test_statusline_without_project(self):
        """Project field omitted when None."""
        result = format_statusline("agent", None, "Host macOS", 60000, 200000, 70)
        assert result == "agent | Host macOS | 60k/200k CLUAC 70"

    def test_statusline_low_tokens(self):
        """Small token values remain numeric."""
        result = format_statusline("test", "Project", "Host", 5000, 9500, 95)
        assert result == "test | Project | Host | 5000/9500 CLUAC 95"

    def test_statusline_zero_cluac(self):
        """CLUAC can be zero (context exhausted)."""
        result = format_statusline("agent", "proj", "Env", 200000, 200000, 0)
        assert result == "agent | proj | Env | 200k/200k CLUAC 0"


class TestDetectProject:
    """Test project name detection."""

    def test_env_var_takes_priority(self, monkeypatch):
        """MACF_PROJECT env var overrides filesystem detection."""
        monkeypatch.setenv("MACF_PROJECT", "EnvProject")
        assert detect_project() == "EnvProject"

    def test_no_env_var_no_claude_dir(self, monkeypatch, tmp_path):
        """Returns None when no env var and no .claude/ dir."""
        monkeypatch.delenv("MACF_PROJECT", raising=False)
        assert detect_project(str(tmp_path)) is None

    def test_detect_from_claude_directory(self, monkeypatch, tmp_path):
        """Detects project from directory containing .claude/."""
        monkeypatch.delenv("MACF_PROJECT", raising=False)

        # Create structure: tmp_path/MyProject/.claude/
        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()

        # Workspace path is inside project
        workspace = project_dir / "subdir"
        workspace.mkdir()

        assert detect_project(str(workspace)) == "MyProject"

    def test_detect_walks_up_tree(self, monkeypatch, tmp_path):
        """Walks up directory tree to find .claude/."""
        monkeypatch.delenv("MACF_PROJECT", raising=False)

        # Create structure: tmp_path/ProjectRoot/.claude/
        project_root = tmp_path / "ProjectRoot"
        project_root.mkdir()
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()

        # Workspace is nested several levels deep
        deep_dir = project_root / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)

        assert detect_project(str(deep_dir)) == "ProjectRoot"


class TestGetStatuslineData:
    """Test statusline data gathering integration."""

    @patch("macf.utils.statusline.ConsciousnessConfig")
    @patch("macf.utils.statusline.detect_execution_environment")
    @patch("macf.utils.statusline.detect_project")
    @patch("macf.utils.statusline.get_token_info")
    def test_data_from_macf_sources(
        self, mock_token_info, mock_detect_project, mock_detect_env, mock_config
    ):
        """Gathers data from MACF sources when no CC JSON provided."""
        # Setup mocks
        mock_config_instance = MagicMock()
        mock_config_instance.agent_id = "test_agent"
        mock_config.return_value = mock_config_instance

        mock_detect_project.return_value = "TestProject"
        mock_detect_env.return_value = "Host macOS"
        mock_token_info.return_value = {
            "tokens_used": 50000,
            "cluac_level": 75
        }

        result = get_statusline_data()

        assert result["agent_name"] == "test_agent"
        assert result["project"] == "TestProject"
        assert result["environment"] == "Host macOS"
        assert result["tokens_used"] == 50000
        assert result["cluac"] == 75

    @patch("macf.utils.statusline.ConsciousnessConfig")
    @patch("macf.utils.statusline.detect_execution_environment")
    @patch("macf.utils.statusline.detect_project")
    def test_data_from_cc_json(self, mock_detect_project, mock_detect_env, mock_config):
        """Claude Code JSON takes priority for token counts."""
        # Setup mocks
        mock_config_instance = MagicMock()
        mock_config_instance.agent_id = "manny"
        mock_config.return_value = mock_config_instance

        mock_detect_project.return_value = "NeuroVEP"
        mock_detect_env.return_value = "Container Linux"

        # Provide CC JSON with token data
        cc_json = {
            "tokens_used": 120000,
            "tokens_total": 200000,
            "cluac": 40
        }

        result = get_statusline_data(cc_json)

        assert result["agent_name"] == "manny"
        assert result["project"] == "NeuroVEP"
        assert result["tokens_used"] == 120000
        assert result["tokens_total"] == 200000
        assert result["cluac"] == 40

    @patch("macf.utils.statusline.ConsciousnessConfig")
    @patch("macf.utils.statusline.detect_execution_environment")
    @patch("macf.utils.statusline.detect_project")
    def test_cluac_calculation_from_cc_json(
        self, mock_detect_project, mock_detect_env, mock_config
    ):
        """Calculates CLUAC from CC JSON when not provided."""
        # Setup mocks
        mock_config_instance = MagicMock()
        mock_config_instance.agent_id = "agent"
        mock_config.return_value = mock_config_instance

        mock_detect_project.return_value = None
        mock_detect_env.return_value = "Host"

        # CC JSON with tokens but no CLUAC
        cc_json = {
            "tokens_used": 50000,
            "tokens_total": 200000
        }

        result = get_statusline_data(cc_json)

        # CLUAC = (200000 - 50000) / 200000 * 100 = 75%
        assert result["cluac"] == 75

    @patch("macf.utils.statusline.ConsciousnessConfig")
    @patch("macf.utils.statusline.detect_execution_environment")
    @patch("macf.utils.statusline.detect_project")
    @patch("macf.utils.statusline.get_token_info")
    def test_graceful_failure_handling(
        self, mock_token_info, mock_detect_project, mock_detect_env, mock_config
    ):
        """Graceful fallback when components fail."""
        # Config and env failures are caught, others return None
        mock_config.side_effect = Exception("Config failed")
        mock_detect_project.return_value = None  # Returns None, doesn't raise
        mock_detect_env.side_effect = Exception("Env detection failed")
        mock_token_info.side_effect = Exception("Token info failed")

        result = get_statusline_data()

        # Should return safe defaults for caught exceptions
        assert result["agent_name"] == "unknown"
        assert result["project"] is None
        assert result["environment"] == "Unknown"
        assert result["tokens_used"] == 0
        assert result["cluac"] == 100
