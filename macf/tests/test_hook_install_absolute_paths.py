"""Regression tests for cversek/MacEff#89 — hooks_install must write
absolute paths into settings (.local.json or global), so a bare `cd`
in agent Bash that shifts CWD doesn't break hook lookup and paralyze
every subsequent tool call.

The bug: previously local-mode wrote `python .claude/hooks/X.py` and
host-global wrote `python ~/.claude/hooks/X.py`. Both can fail
catastrophically: relative paths resolve against the shifted CWD, and
~ expansion is shell-dependent and not documented to fire in CC's
hook exec model.

The fix: write absolute paths in both modes so hook lookup is
CWD-independent and shell-expansion-independent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest


# --- Helpers ---------------------------------------------------------------

def _read_hook_commands(settings_path: Path) -> list[str]:
    """Read all hook command strings from a settings JSON file."""
    settings = json.loads(settings_path.read_text())
    commands: list[str] = []
    for hook_name, entries in settings.get("hooks", {}).items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command")
                if cmd:
                    commands.append(cmd)
    return commands


# --- Local-mode regression -------------------------------------------------

def test_local_install_writes_absolute_hook_paths(tmp_path, monkeypatch):
    """Local-mode install must write absolute paths to settings.local.json,
    so a bare `cd` in agent Bash doesn't break hook lookup.
    """
    from macf.cli import cmd_hook_install

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")
    # Force host (not container) by intercepting the /.dockerenv check.
    monkeypatch.setattr(
        "pathlib.Path.exists",
        lambda self: False if str(self) == "/.dockerenv" else Path.exists.__wrapped__(self) if hasattr(Path.exists, "__wrapped__") else Path(str(self)).is_file() or Path(str(self)).is_dir(),
    )

    args = argparse.Namespace(local_install=True, global_install=False)
    rc = cmd_hook_install(args)
    assert rc == 0, "Local install returned non-zero"

    settings_path = tmp_path / ".claude" / "settings.local.json"
    assert settings_path.exists(), "settings.local.json not written"

    commands = _read_hook_commands(settings_path)
    assert commands, "No hook commands found in settings"

    expected_hooks_dir = (tmp_path / ".claude" / "hooks").resolve()
    for cmd in commands:
        assert ".claude/hooks" not in cmd or str(expected_hooks_dir) in cmd, (
            f"Hook command should reference absolute hooks dir, got: {cmd}"
        )
        # Absolute path: starts with python <abs-path>
        # Allow either resolved tmp_path prefix or the canonicalized macOS
        # /private prefix (tmp_path on darwin can resolve via /private/var).
        assert (
            f"python {expected_hooks_dir}/" in cmd
            or f"python {expected_hooks_dir}\\" in cmd  # Windows safety
        ), f"Hook command not absolute: {cmd}"


def test_local_install_no_relative_dot_claude_path(tmp_path, monkeypatch):
    """The literal 'python .claude/hooks/' prefix must NEVER appear in
    settings — that's the exact failure mode from #89.
    """
    from macf.cli import cmd_hook_install

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")
    monkeypatch.setattr(
        "pathlib.Path.exists",
        lambda self: False if str(self) == "/.dockerenv" else Path(str(self)).is_file() or Path(str(self)).is_dir(),
    )

    args = argparse.Namespace(local_install=True, global_install=False)
    cmd_hook_install(args)

    settings_path = tmp_path / ".claude" / "settings.local.json"
    text = settings_path.read_text()
    # The exact buggy prefix
    assert "python .claude/hooks/" not in text, (
        "Settings still contains the relative prefix that #89 fixes"
    )


# --- Global host-mode regression -------------------------------------------

def test_global_host_install_writes_absolute_home_path(tmp_path, monkeypatch):
    """Host-global install must write the absolute home path, not ~,
    because shell-expansion is not guaranteed in CC's hook exec model.
    """
    from macf.cli import cmd_hook_install

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    monkeypatch.setattr(
        "pathlib.Path.exists",
        lambda self: False if str(self) == "/.dockerenv" else Path(str(self)).is_file() or Path(str(self)).is_dir(),
    )

    args = argparse.Namespace(local_install=False, global_install=True)
    rc = cmd_hook_install(args)
    assert rc == 0

    settings_path = fake_home / ".claude" / "settings.json"
    assert settings_path.exists()

    text = settings_path.read_text()
    assert "python ~/.claude/hooks/" not in text, (
        "Host-global install still uses ~ (shell-expansion-dependent)"
    )
    commands = _read_hook_commands(settings_path)
    for cmd in commands:
        assert f"python {fake_home}/.claude/hooks/" in cmd, (
            f"Host-global hook command not absolute-home: {cmd}"
        )
