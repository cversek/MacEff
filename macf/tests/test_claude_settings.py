"""
Tests for claude_settings.py utilities.

Tests Claude Code settings reading/writing functions for autocompact
and permission mode configuration.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from macf.utils.claude_settings import (
    get_autocompact_setting,
    set_autocompact_enabled,
    set_permission_mode,
    _read_autocompact_from_file
)


class TestGetAutocompactSetting:
    """Tests for get_autocompact_setting() function."""

    def test_returns_true_when_env_var_true(self, monkeypatch):
        """Environment variable 'true' enables autocompact."""
        monkeypatch.setenv('CLAUDE_AUTOCOMPACT', 'true')
        assert get_autocompact_setting() is True

    def test_returns_false_when_env_var_false(self, monkeypatch):
        """Environment variable 'false' disables autocompact."""
        monkeypatch.setenv('CLAUDE_AUTOCOMPACT', 'false')
        assert get_autocompact_setting() is False

    def test_reads_project_settings_when_no_env_var(self, tmp_path, monkeypatch):
        """Reads from .claude/settings.local.json when env var not set."""
        monkeypatch.delenv('CLAUDE_AUTOCOMPACT', raising=False)

        # Create project settings file
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.local.json"
        settings_file.write_text(json.dumps({"autoCompact": True}))

        result = get_autocompact_setting(project_root=tmp_path)
        assert result is True

    def test_returns_false_when_no_settings_found(self, tmp_path, monkeypatch):
        """Default to False when no settings found anywhere."""
        monkeypatch.delenv('CLAUDE_AUTOCOMPACT', raising=False)

        # No settings files exist
        result = get_autocompact_setting(project_root=tmp_path)
        assert result is False

    def test_handles_missing_settings_file_gracefully(self, tmp_path, monkeypatch):
        """Returns False when settings files don't exist."""
        monkeypatch.delenv('CLAUDE_AUTOCOMPACT', raising=False)

        # Directory exists but no settings file
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()

        result = get_autocompact_setting(project_root=tmp_path)
        assert result is False


class TestSetAutocompactEnabled:
    """Tests for set_autocompact_enabled() function."""

    def test_creates_settings_file_when_missing(self, tmp_path, monkeypatch):
        """Creates ~/.claude.json if it doesn't exist."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, 'home', lambda: fake_home)

        result = set_autocompact_enabled(True)
        assert result is True

        settings_path = fake_home / ".claude.json"
        assert settings_path.exists()

        settings = json.loads(settings_path.read_text())
        assert settings['autoCompactEnabled'] is True

    def test_updates_existing_settings_file(self, tmp_path, monkeypatch):
        """Updates existing ~/.claude.json preserving other settings."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, 'home', lambda: fake_home)

        # Create existing settings
        settings_path = fake_home / ".claude.json"
        existing = {"otherSetting": "value"}
        settings_path.write_text(json.dumps(existing))

        result = set_autocompact_enabled(False)
        assert result is True

        settings = json.loads(settings_path.read_text())
        assert settings['autoCompactEnabled'] is False
        assert settings['otherSetting'] == "value"

    def test_writes_atomically_via_temp_file(self, tmp_path, monkeypatch):
        """Uses temp file pattern for atomic writes."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, 'home', lambda: fake_home)

        result = set_autocompact_enabled(True)
        assert result is True

        # Verify no .tmp file left behind
        assert not (fake_home / ".claude.json.tmp").exists()
        assert (fake_home / ".claude.json").exists()

    def test_returns_false_on_write_error(self, monkeypatch):
        """Returns False when write fails."""
        # Mock Path.home() to raise error
        def mock_home():
            raise OSError("Permission denied")
        monkeypatch.setattr(Path, 'home', mock_home)

        result = set_autocompact_enabled(True)
        assert result is False


class TestSetPermissionMode:
    """Tests for set_permission_mode() function."""

    def test_creates_settings_when_missing(self, tmp_path):
        """Creates .claude/settings.local.json if missing."""
        settings_dir = tmp_path / ".claude"

        result = set_permission_mode("accept-edits", project_root=tmp_path)
        assert result is True

        settings_path = settings_dir / "settings.local.json"
        assert settings_path.exists()

        settings = json.loads(settings_path.read_text())
        assert settings['permissions']['defaultMode'] == "accept-edits"

    def test_updates_existing_permission_settings(self, tmp_path):
        """Updates permission mode in existing settings."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_path = settings_dir / "settings.local.json"

        # Existing settings
        existing = {"permissions": {"defaultMode": "default"}, "other": "value"}
        settings_path.write_text(json.dumps(existing))

        result = set_permission_mode("plan", project_root=tmp_path)
        assert result is True

        settings = json.loads(settings_path.read_text())
        assert settings['permissions']['defaultMode'] == "plan"
        assert settings['other'] == "value"

    def test_creates_permissions_dict_if_missing(self, tmp_path):
        """Creates permissions dict if not present in existing file."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_path = settings_dir / "settings.local.json"

        # Existing settings without permissions
        existing = {"other": "value"}
        settings_path.write_text(json.dumps(existing))

        result = set_permission_mode("bypassPermissions", project_root=tmp_path)
        assert result is True

        settings = json.loads(settings_path.read_text())
        assert settings['permissions']['defaultMode'] == "bypassPermissions"

    def test_returns_false_on_write_error(self, tmp_path):
        """Returns False when directory creation fails."""
        # Make directory read-only to cause write failure
        tmp_path.chmod(0o444)

        result = set_permission_mode("plan", project_root=tmp_path)

        # Restore permissions for cleanup
        tmp_path.chmod(0o755)

        assert result is False


class TestReadAutocompactFromFile:
    """Tests for _read_autocompact_from_file() helper."""

    def test_returns_none_when_file_missing(self, tmp_path):
        """Returns None when settings file doesn't exist."""
        settings_path = tmp_path / "nonexistent.json"
        result = _read_autocompact_from_file(settings_path)
        assert result is None

    def test_reads_autocompact_key(self, tmp_path):
        """Reads 'autocompact' key from JSON."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"autocompact": True}))

        result = _read_autocompact_from_file(settings_path)
        assert result is True

    def test_reads_camel_case_key(self, tmp_path):
        """Reads 'autoCompact' camelCase variant."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"autoCompact": False}))

        result = _read_autocompact_from_file(settings_path)
        assert result is False

    def test_returns_none_when_key_missing(self, tmp_path):
        """Returns None when no autocompact key found."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"other": "value"}))

        result = _read_autocompact_from_file(settings_path)
        assert result is None

    def test_handles_malformed_json_gracefully(self, tmp_path):
        """Returns None on JSON decode error."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{ invalid json }")

        result = _read_autocompact_from_file(settings_path)
        assert result is None
