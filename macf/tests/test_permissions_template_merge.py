"""Regression tests for the permissions template merge (issue #53).

The `macf_tools framework install` path merges permissions from
`framework/templates/settings.permissions.json` into the agent's Claude
Code settings. Historically only the `ask` bucket was merged; the
`allow` bucket was silently ignored. The allowlist entry that neutralizes
the AUTO_MODE/CC name collision lives under `allow`, so this bucket must
be merged for the shipped allowlist to actually reach agent settings.

These tests lock down the behavior of `_update_settings_file` against the
real shipped template, as well as the template's content itself.
"""
import json
from pathlib import Path

import pytest

from macf.cli import _update_settings_file
from macf.utils.paths import find_maceff_root


@pytest.fixture(autouse=True)
def _clear_maceff_root_cache():
    """find_maceff_root is @lru_cache'd — earlier tests that override
    MACEFF_ROOT_DIR may leave a stale cache pointing at a tmp_path. Clear
    before and after so these tests see the real repo root."""
    find_maceff_root.cache_clear()
    yield
    find_maceff_root.cache_clear()


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def test_shipped_template_allowlists_mode_cli():
    """The shipped template must include the mode CLI allowlist — that is the
    mechanism that prevents CC's permission layer from denying AUTO_MODE
    activation as 'self-authorizing' (issue #53)."""
    root = find_maceff_root()
    template = root / "framework" / "templates" / "settings.permissions.json"
    data = _read(template)
    allow = (data.get("permissions") or {}).get("allow") or []
    assert "Bash(macf_tools mode:*)" in allow, (
        "shipped template must allowlist `Bash(macf_tools mode:*)` to neutralize "
        "CC's name-collision denial of the AUTO_MODE activation command"
    )


def test_update_settings_file_merges_allow_bucket(tmp_path, monkeypatch):
    """A fresh settings file should gain the shipped allowlist entries after
    _update_settings_file runs — not just the `ask` entries."""
    # Run from tmp_path so the _update_settings_file doesn't clobber anything real
    monkeypatch.chdir(tmp_path)
    settings_file = tmp_path / "settings.json"
    hooks_prefix = "python .claude/hooks"

    result = _update_settings_file(settings_file, hooks_prefix)
    assert result is True
    data = _read(settings_file)
    allow = (data.get("permissions") or {}).get("allow") or []
    assert "Bash(macf_tools mode:*)" in allow


def test_update_settings_file_preserves_existing_user_allow_entries(tmp_path, monkeypatch):
    """The merge must be additive: existing user entries in `allow` stay,
    template entries are added, no duplicates."""
    monkeypatch.chdir(tmp_path)
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "permissions": {
            "allow": ["Bash(ls:*)", "Bash(macf_tools mode:*)"]  # one user entry + one overlap
        }
    }))

    result = _update_settings_file(settings_file, "python .claude/hooks")
    assert result is True
    data = _read(settings_file)
    allow = data["permissions"]["allow"]
    assert "Bash(ls:*)" in allow, "user's existing entries must survive merge"
    # No duplicates
    assert allow.count("Bash(macf_tools mode:*)") == 1


def test_update_settings_file_merges_ask_bucket_regression(tmp_path, monkeypatch):
    """The ask bucket merge must still work — this is the behavior the old code
    had, and we must not regress it while extending to allow/deny."""
    monkeypatch.chdir(tmp_path)
    settings_file = tmp_path / "settings.json"
    _update_settings_file(settings_file, "python .claude/hooks")
    data = _read(settings_file)
    ask = (data.get("permissions") or {}).get("ask") or []
    assert "Bash(macf_tools task grant-update:*)" in ask
    assert "Bash(macf_tools task grant-delete:*)" in ask
