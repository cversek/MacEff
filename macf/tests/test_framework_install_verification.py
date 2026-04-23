"""Regression tests for framework install post-hook verification (issue #52).

The framework install's global→local migration is non-atomic: it clears the
global hooks block BEFORE writing the local one. If the local write silently
fails (CWD mismatch, permission error, JSON exception swallowed by the caller),
the agent loses ALL hooks and the install still reports success.

These tests lock down the post-install verification that prevents that class
of silent failure.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from macf.cli import _count_hook_events_in_settings, cmd_framework_install


# --- _count_hook_events_in_settings ----------------------------------------

def _write_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_count_returns_zero_for_missing_file(tmp_path):
    assert _count_hook_events_in_settings(tmp_path / "missing.json") == 0


def test_count_returns_zero_when_no_hooks_key(tmp_path):
    settings = tmp_path / "settings.json"
    _write_settings(settings, {"permissions": {}, "statusLine": {}})
    assert _count_hook_events_in_settings(settings) == 0


def test_count_returns_full_count_for_all_ten_events(tmp_path):
    settings = tmp_path / "settings.json"
    events = [
        "SessionStart", "UserPromptSubmit", "Stop", "SubagentStop",
        "PreToolUse", "PostToolUse", "SessionEnd", "PreCompact",
        "PermissionRequest", "Notification",
    ]
    _write_settings(settings, {"hooks": {e: [{"matcher": "", "hooks": []}] for e in events}})
    assert _count_hook_events_in_settings(settings) == 10


def test_count_returns_partial_count_for_partial_bindings(tmp_path):
    settings = tmp_path / "settings.json"
    _write_settings(settings, {"hooks": {"SessionStart": [], "Stop": []}})
    assert _count_hook_events_in_settings(settings) == 2


# --- cmd_framework_install post-install verification -----------------------

@pytest.fixture
def fake_framework_root(tmp_path, monkeypatch):
    """Give cmd_framework_install a minimal MACEFF root with a framework/ dir.

    find_maceff_root is @lru_cache'd, so we must clear the cache on teardown —
    otherwise later tests that rely on the real repo root will receive our
    tmp_path (which gets cleaned up) and fail with misleading errors.
    """
    from macf.utils.paths import find_maceff_root
    root = tmp_path / "MacEff"
    (root / "framework" / "commands").mkdir(parents=True)
    (root / "framework" / "skills").mkdir()
    monkeypatch.setenv("MACEFF_ROOT_DIR", str(root))
    monkeypatch.chdir(tmp_path)
    find_maceff_root.cache_clear()
    try:
        yield root
    finally:
        find_maceff_root.cache_clear()


def test_framework_install_bails_when_hook_install_returns_nonzero(fake_framework_root):
    """If cmd_hook_install signals failure, framework install must NOT continue."""
    real_exists = Path.exists

    def fake_exists(self):
        if str(self) == "/.dockerenv":
            return False
        return real_exists(self)

    with patch("macf.cli.cmd_hook_install", return_value=1), \
         patch.object(Path, "exists", fake_exists):
        args = argparse.Namespace()
        result = cmd_framework_install(args)
    assert result == 1


def test_framework_install_bails_when_settings_has_no_hooks(fake_framework_root, capsys):
    """If hook install returns 0 but settings file has no hooks, install must fail loudly."""
    real_exists = Path.exists
    def fake_exists(self):
        if str(self) == "/.dockerenv":
            return False
        return real_exists(self)

    # Simulate the silent-failure: hook_install returns 0 but never wrote the file
    with patch("macf.cli.cmd_hook_install", return_value=0), \
         patch.object(Path, "exists", fake_exists):
        args = argparse.Namespace()
        result = cmd_framework_install(args)

    out = capsys.readouterr().out
    assert result == 1
    assert "Hook installation reported success" in out
    assert "hook events bound" in out


def test_framework_install_reports_actual_count_on_success(fake_framework_root, capsys):
    """On success, the summary must reflect the ACTUAL hook count, not a hardcoded 10."""
    real_exists = Path.exists
    def fake_exists(self):
        if str(self) == "/.dockerenv":
            return False
        return real_exists(self)

    # Seed settings file with all 10 hooks as if hook_install wrote them
    settings_file = Path.cwd() / ".claude" / "settings.local.json"
    events = [
        "SessionStart", "UserPromptSubmit", "Stop", "SubagentStop",
        "PreToolUse", "PostToolUse", "SessionEnd", "PreCompact",
        "PermissionRequest", "Notification",
    ]
    _write_settings(settings_file, {"hooks": {e: [] for e in events}})

    with patch("macf.cli.cmd_hook_install", return_value=0), \
         patch.object(Path, "exists", fake_exists):
        args = argparse.Namespace()
        result = cmd_framework_install(args)

    out = capsys.readouterr().out
    assert result == 0
    assert "Hooks: 10" in out
    # Must not have hit the failure path
    assert "Hook installation reported success" not in out
