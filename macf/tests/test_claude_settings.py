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
    _read_autocompact_from_file,
    _bash_pattern_command,
    _find_shadowing_allow_entries,
    toggle_auto_mode_ask_permissions,
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

    def test_writes_to_both_legacy_and_primary_paths(self, tmp_path, monkeypatch):
        """Writes to BOTH ~/.claude.json (legacy) and ~/.claude/settings.json (current CC)."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, 'home', lambda: fake_home)

        result = set_autocompact_enabled(True)
        assert result is True

        legacy = fake_home / ".claude.json"
        primary = fake_home / ".claude" / "settings.json"
        assert legacy.exists()
        assert primary.exists()
        assert json.loads(legacy.read_text())['autoCompactEnabled'] is True
        assert json.loads(primary.read_text())['autoCompactEnabled'] is True

    def test_warns_when_settings_local_overrides(self, tmp_path, monkeypatch, capsys):
        """Prints stderr warning when ~/.claude/settings.local.json has opposing value."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".claude").mkdir()
        local = fake_home / ".claude" / "settings.local.json"
        local.write_text(json.dumps({"autoCompactEnabled": False}))
        monkeypatch.setattr(Path, 'home', lambda: fake_home)

        result = set_autocompact_enabled(True)
        assert result is True  # writes succeeded; warning is informational

        err = capsys.readouterr().err
        assert "settings.local.json" in err
        assert "OVERRIDES" in err


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


class TestBashPatternCommand:
    """Tests for _bash_pattern_command() — strips Bash() and trailing :*."""

    def test_extracts_command_from_bash_pattern(self):
        assert _bash_pattern_command("Bash(gh issue:*)") == "gh issue"
        assert _bash_pattern_command("Bash(gh issue create:*)") == "gh issue create"

    def test_no_trailing_wildcard(self):
        # Some patterns may not have :* — return as-is after Bash() stripping
        assert _bash_pattern_command("Bash(git push)") == "git push"

    def test_non_bash_pattern_returns_none(self):
        assert _bash_pattern_command("Read(src/*)") is None
        assert _bash_pattern_command("invalid") is None
        assert _bash_pattern_command("") is None


class TestFindShadowingAllowEntries:
    """Tests for _find_shadowing_allow_entries() — closes GH issue #67."""

    def test_broader_allow_shadows_narrower_ask(self):
        ask = "Bash(gh issue create:*)"
        allow = ["Bash(gh issue:*)", "Bash(ls:*)"]
        shadows = _find_shadowing_allow_entries(ask, allow)
        assert shadows == ["Bash(gh issue:*)"]

    def test_unrelated_allow_does_not_shadow(self):
        ask = "Bash(gh issue create:*)"
        allow = ["Bash(ls:*)", "Bash(cat:*)", "Bash(git status:*)"]
        shadows = _find_shadowing_allow_entries(ask, allow)
        assert shadows == []

    def test_narrower_allow_does_not_shadow(self):
        # Allow is narrower than ask → not a shadow
        ask = "Bash(gh issue:*)"
        allow = ["Bash(gh issue create:*)"]
        shadows = _find_shadowing_allow_entries(ask, allow)
        assert shadows == []

    def test_exact_match_not_treated_as_shadow(self):
        # Identical entry → not a shadow (handled by add/remove logic, not relocation)
        ask = "Bash(gh issue create:*)"
        allow = ["Bash(gh issue create:*)"]
        shadows = _find_shadowing_allow_entries(ask, allow)
        assert shadows == []

    def test_multiple_shadows(self):
        ask = "Bash(gh issue create:*)"
        allow = ["Bash(gh:*)", "Bash(gh issue:*)", "Bash(ls:*)"]
        shadows = _find_shadowing_allow_entries(ask, allow)
        assert "Bash(gh:*)" in shadows
        assert "Bash(gh issue:*)" in shadows
        assert "Bash(ls:*)" not in shadows

    def test_word_boundary_required(self):
        # "Bash(gh i:*)" should NOT shadow "Bash(gh issue create:*)" — "i" is a
        # different command from "issue", not a prefix on a space boundary.
        ask = "Bash(gh issue create:*)"
        allow = ["Bash(gh i:*)"]
        shadows = _find_shadowing_allow_entries(ask, allow)
        assert shadows == []


class TestToggleAutoModeAskPermissionsShadowFix:
    """Tests for toggle_auto_mode_ask_permissions() with shadow detection."""

    def test_relocates_shadowing_allow_on_enable(self, tmp_path):
        """Pre-existing broad allow that shadows an AUTO_MODE ask gets relocated."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_path = settings_dir / "settings.local.json"
        # Brownfield env: a broad allow that shadows several AUTO_MODE asks
        settings_path.write_text(json.dumps({
            "permissions": {"allow": ["Bash(gh issue:*)"], "ask": [], "deny": []}
        }))

        result = toggle_auto_mode_ask_permissions(True, project_root=tmp_path)
        assert result is not None
        assert any(
            ask_entry == "Bash(gh issue create:*)"
            for ask_entry, _ in result['shadows_relocated']
        )

        # The shadow should be GONE from allow and stashed for restoration
        on_disk = json.loads(settings_path.read_text())
        assert "Bash(gh issue:*)" not in on_disk["permissions"]["allow"]
        assert "_macf_shadowed_allow" in on_disk
        # The stash should record the relocation keyed by an ask entry
        stash_entries = [
            shadowed
            for stash_list in on_disk["_macf_shadowed_allow"].values()
            for shadowed in stash_list
        ]
        assert "Bash(gh issue:*)" in stash_entries

    def test_round_trip_restoration_on_disable(self, tmp_path):
        """Shadowed allow entries are restored when toggling back to MANUAL_MODE."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_path = settings_dir / "settings.local.json"
        settings_path.write_text(json.dumps({
            "permissions": {"allow": ["Bash(gh issue:*)"], "ask": [], "deny": []}
        }))

        toggle_auto_mode_ask_permissions(True, project_root=tmp_path)
        # Now disable
        result = toggle_auto_mode_ask_permissions(False, project_root=tmp_path)
        assert result is not None
        assert "Bash(gh issue:*)" in result['shadows_restored']

        on_disk = json.loads(settings_path.read_text())
        # Restored to allow list
        assert "Bash(gh issue:*)" in on_disk["permissions"]["allow"]
        # Stash drained, key removed
        assert "_macf_shadowed_allow" not in on_disk

    def test_no_shadow_means_no_relocation(self, tmp_path):
        """When no shadows exist, behavior matches the pre-fix path."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_path = settings_dir / "settings.local.json"
        settings_path.write_text(json.dumps({
            "permissions": {"allow": ["Bash(ls:*)"], "ask": [], "deny": []}
        }))

        result = toggle_auto_mode_ask_permissions(True, project_root=tmp_path)
        assert result is not None
        assert result['shadows_relocated'] == []
        # All AUTO_MODE asks added
        on_disk = json.loads(settings_path.read_text())
        assert "Bash(gh issue create:*)" in on_disk["permissions"]["ask"]
        # ls was NOT shadowing anything → still in allow
        assert "Bash(ls:*)" in on_disk["permissions"]["allow"]
