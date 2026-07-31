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

from macf.cli import (
    _count_hook_events_in_settings,
    _hooks_to_install_list,
    cmd_framework_install,
)


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
    # Seed one real namespace in each tree. An empty tree is now an install
    # failure in its own right, so a fixture with empty dirs would make every
    # success-path test fail for a reason unrelated to what it is testing.
    ns = root / "framework" / "commands" / "maceff"
    ns.mkdir(parents=True)
    (ns / "sample.md").write_text("# sample command\n")
    skill = root / "framework" / "skills" / "maceff-sample"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# sample skill\n")
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
    """On success, the summary must reflect the ACTUAL hook count, derived from the canonical _hooks_to_install_list helper, not a hardcoded number."""
    real_exists = Path.exists
    def fake_exists(self):
        if str(self) == "/.dockerenv":
            return False
        return real_exists(self)

    expected_count = len(_hooks_to_install_list())

    # Seed the settings file with the canonical count of hook events as if
    # cmd_hook_install wrote them. Names don't matter to _count_hook_events_in_settings;
    # only the count of keys in the hooks dict.
    settings_file = Path.cwd() / ".claude" / "settings.local.json"
    events = [f"Event{i}" for i in range(expected_count)]
    _write_settings(settings_file, {"hooks": {e: [] for e in events}})

    with patch("macf.cli.cmd_hook_install", return_value=0), \
         patch.object(Path, "exists", fake_exists):
        args = argparse.Namespace()
        result = cmd_framework_install(args)

    out = capsys.readouterr().out
    assert result == 0
    assert f"Hooks: {expected_count}" in out
    # Must not have hit the failure path
    assert "Hook installation reported success" not in out


# --- silent no-op when source trees are absent or empty --------------------
#
# The install printed "📦 Installing commands..." and, when the source tree was
# missing, a quiet stdout line before exiting 0 with "✅ Framework installation
# complete!". On a container whose framework tree had never been deployed this
# reported success while installing nothing, and the gap only surfaced later as
# missing commands — a peer agent lost real diagnosis time to it.


def _seed_hooks_settings():
    """Write a settings file with the canonical hook count, so the hook stage
    passes and the test exercises the commands/skills stage."""
    settings_file = Path.cwd() / ".claude" / "settings.local.json"
    events = [f"Event{i}" for i in range(len(_hooks_to_install_list()))]
    _write_settings(settings_file, {"hooks": {e: [] for e in events}})


def _run_install(**namespace_kwargs):
    real_exists = Path.exists

    def fake_exists(self):
        if str(self) == "/.dockerenv":
            return False
        return real_exists(self)

    with patch("macf.cli.cmd_hook_install", return_value=0), \
         patch.object(Path, "exists", fake_exists):
        return cmd_framework_install(argparse.Namespace(**namespace_kwargs))


def test_install_fails_when_commands_source_is_absent(fake_framework_root, capsys):
    import shutil
    shutil.rmtree(fake_framework_root / "framework" / "commands")
    _seed_hooks_settings()

    result = _run_install()

    captured = capsys.readouterr()
    assert result == 1
    assert "no commands directory" in captured.err
    assert "INCOMPLETE" in captured.err
    assert "Framework installation complete" not in captured.out


def test_install_fails_when_skills_source_is_absent(fake_framework_root, capsys):
    import shutil
    shutil.rmtree(fake_framework_root / "framework" / "skills")
    _seed_hooks_settings()

    result = _run_install()

    captured = capsys.readouterr()
    assert result == 1
    assert "no skills directory" in captured.err
    assert "Framework installation complete" not in captured.out


def test_install_fails_when_source_exists_but_holds_no_namespaces(fake_framework_root, capsys):
    """Present-but-empty is the same failure wearing a directory.

    An existence check passes, the loop body never runs, and the summary is
    identical to a successful install.
    """
    import shutil
    shutil.rmtree(fake_framework_root / "framework" / "commands" / "maceff")
    shutil.rmtree(fake_framework_root / "framework" / "skills" / "maceff-sample")
    _seed_hooks_settings()

    result = _run_install()

    captured = capsys.readouterr()
    assert result == 1
    assert "no maceff*/ namespaces found" in captured.err
    assert "no maceff-*/ skills found" in captured.err


def test_install_names_every_missing_tree_not_just_the_first(fake_framework_root, capsys):
    import shutil
    shutil.rmtree(fake_framework_root / "framework" / "commands")
    shutil.rmtree(fake_framework_root / "framework" / "skills")
    _seed_hooks_settings()

    result = _run_install()

    err = capsys.readouterr().err
    assert result == 1
    assert "commands: source tree missing" in err
    assert "skills: source tree missing" in err


def test_install_succeeds_and_links_when_trees_are_populated(fake_framework_root, capsys):
    """Positive control: the failure path must not fire on a good tree."""
    _seed_hooks_settings()

    result = _run_install()

    captured = capsys.readouterr()
    assert result == 0, captured.err
    assert "Framework installation complete" in captured.out
    assert "INCOMPLETE" not in captured.err
    assert (Path.cwd() / ".claude" / "commands" / "maceff").is_symlink()
    assert (Path.cwd() / ".claude" / "skills" / "maceff-sample").is_symlink()


def test_hooks_only_does_not_fail_on_absent_command_trees(fake_framework_root, capsys):
    """--hooks-only returns before the commands/skills stage, and must keep
    doing so — installing hooks alone is a legitimate intent."""
    import shutil
    shutil.rmtree(fake_framework_root / "framework" / "commands")
    shutil.rmtree(fake_framework_root / "framework" / "skills")
    _seed_hooks_settings()

    result = _run_install(hooks_only=True)

    captured = capsys.readouterr()
    assert result == 0, captured.err
    assert "Hooks-only installation complete" in captured.out
