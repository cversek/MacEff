"""Tests for cversek/MacEff#96 Phase 1 — config-layer slot in get_agent_identity.

Adds a config-reading step between the MACEFF_AGENT_NAME env-var override
and the GECOS fallback. Per-project `.maceff/config.json` `agent_identity`
block now drives the agent's display name without needing a shell rc
override.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from macf.utils.identity import _get_config_identity_name, get_agent_identity


# ---------- _get_config_identity_name unit ----------

def _write_config(tmp_path: Path, identity_block: dict) -> Path:
    """Write a .maceff/config.json under tmp_path and return the agent_home dir."""
    home = tmp_path
    (home / ".maceff").mkdir(parents=True, exist_ok=True)
    (home / ".maceff" / "config.json").write_text(
        json.dumps({"agent_identity": identity_block})
    )
    return home


def test_config_identity_returns_calling_card_first(tmp_path):
    home = _write_config(tmp_path, {"calling_card": "Card", "moniker": "AgentMoniker"})
    with patch("macf.utils.paths.find_agent_home", return_value=home):
        assert _get_config_identity_name() == "Card"


def test_config_identity_falls_back_to_moniker(tmp_path):
    """calling_card missing → use moniker."""
    home = _write_config(tmp_path, {"moniker": "AgentMoniker"})
    with patch("macf.utils.paths.find_agent_home", return_value=home):
        assert _get_config_identity_name() == "AgentMoniker"


def test_config_identity_strips_whitespace(tmp_path):
    home = _write_config(tmp_path, {"calling_card": "  Card  "})
    with patch("macf.utils.paths.find_agent_home", return_value=home):
        assert _get_config_identity_name() == "Card"


def test_config_identity_returns_none_when_block_missing(tmp_path):
    """No agent_identity block → fall through (None)."""
    (tmp_path / ".maceff").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".maceff" / "config.json").write_text(json.dumps({}))
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        assert _get_config_identity_name() is None


def test_config_identity_returns_none_when_file_missing(tmp_path):
    """No config.json → fall through (None)."""
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        assert _get_config_identity_name() is None


def test_config_identity_returns_none_when_values_empty(tmp_path):
    """Empty strings → fall through (None)."""
    home = _write_config(tmp_path, {"calling_card": "", "moniker": "   "})
    with patch("macf.utils.paths.find_agent_home", return_value=home):
        assert _get_config_identity_name() is None


# ---------- get_agent_identity resolution chain ----------

def test_env_var_still_takes_precedence_over_config(tmp_path, monkeypatch):
    """MACEFF_AGENT_NAME overrides config — explicit one-off wins (global scope).

    In per-project UUID scope the env var now ranks below config and GECOS
    (scope coherence — see test_agent_identity.py); this test pins the
    surviving global-scope behavior.
    """
    home = _write_config(tmp_path, {"calling_card": "Card"})
    monkeypatch.setenv("MACEFF_AGENT_NAME", "ExplicitOverride")
    with patch("macf.utils.paths.find_agent_home", return_value=home), \
         patch("macf.utils.identity._resolve_uuid_prefix", return_value=("abcdef", "global")):
        assert get_agent_identity() == "ExplicitOverride@abcdef"


def test_config_wins_over_gecos_when_env_unset(tmp_path, monkeypatch):
    """Config layer is consulted between env var and GECOS — eliminates the
    pattern of baking a per-project display-name override into a shell rc file."""
    home = _write_config(tmp_path, {"calling_card": "Card"})
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    with patch("macf.utils.paths.find_agent_home", return_value=home), \
         patch("macf.utils.identity._get_gecos_name", return_value="GecosName"), \
         patch("macf.utils.identity._resolve_uuid_prefix", return_value=("abcdef", "global")):
        assert get_agent_identity() == "Card@abcdef"


def test_falls_through_to_gecos_when_no_config(tmp_path, monkeypatch):
    """Backward-compat: no config → existing GECOS path still works."""
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path), \
         patch("macf.utils.identity._get_gecos_name", return_value="GecosName"), \
         patch("macf.utils.identity._resolve_uuid_prefix", return_value=("abcdef", "global")):
        assert get_agent_identity() == "GecosName@abcdef"
