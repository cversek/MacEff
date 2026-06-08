"""Tests for the unified config layer's resolve_setting helper.

Coverage for cversek/MacEff#96 Phases 2-4 — the env → .maceff/config.json
→ default resolution chain that lets per-project config replace shell-rc
env-var workarounds for deployment-wide settings.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from macf.config import resolve_setting, _load_maceff_config, _dotted_lookup


def _write_config(home: Path, payload: dict) -> None:
    (home / ".maceff").mkdir(parents=True, exist_ok=True)
    (home / ".maceff" / "config.json").write_text(json.dumps(payload))


# ---- _dotted_lookup -------------------------------------------------------

def test_dotted_lookup_finds_nested_key():
    cfg = {"context": {"window": 1_000_000}}
    assert _dotted_lookup(cfg, "context.window") == 1_000_000


def test_dotted_lookup_returns_none_for_missing_segment():
    cfg = {"context": {"window": 1_000_000}}
    assert _dotted_lookup(cfg, "context.low_context_cl") is None
    assert _dotted_lookup(cfg, "session.user_idle_timeout_mins") is None


def test_dotted_lookup_returns_none_for_non_dict_intermediate():
    cfg = {"context": "not a dict"}
    assert _dotted_lookup(cfg, "context.window") is None


# ---- resolve_setting layer precedence -----------------------------------

def test_env_overrides_config(monkeypatch, tmp_path):
    monkeypatch.setenv("MACF_CONTEXT_WINDOW", "500000")
    _write_config(tmp_path, {"context": {"window": 1_000_000}})
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        value, source = resolve_setting(
            "MACF_CONTEXT_WINDOW", "context.window", 200_000, coerce=int,
        )
    assert (value, source) == (500_000, "env")


def test_config_used_when_env_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("MACF_CONTEXT_WINDOW", raising=False)
    _write_config(tmp_path, {"context": {"window": 1_000_000}})
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        value, source = resolve_setting(
            "MACF_CONTEXT_WINDOW", "context.window", 200_000, coerce=int,
        )
    assert (value, source) == (1_000_000, "config")


def test_default_used_when_neither_env_nor_config(monkeypatch, tmp_path):
    monkeypatch.delenv("MACF_CONTEXT_WINDOW", raising=False)
    # tmp_path is empty — no .maceff/config.json
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        value, source = resolve_setting(
            "MACF_CONTEXT_WINDOW", "context.window", 200_000, coerce=int,
        )
    assert (value, source) == (200_000, "default")


def test_explicit_null_in_config_falls_through_to_default(monkeypatch, tmp_path):
    """An explicit `null` in JSON means "absent" — falls to default."""
    monkeypatch.delenv("MACF_CONTEXT_WINDOW", raising=False)
    _write_config(tmp_path, {"context": {"window": None}})
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        value, source = resolve_setting(
            "MACF_CONTEXT_WINDOW", "context.window", 200_000, coerce=int,
        )
    assert (value, source) == (200_000, "default")


# ---- coerce behavior ----------------------------------------------------

def test_coerce_applied_to_env_string(monkeypatch, tmp_path):
    monkeypatch.setenv("MACF_LOW_CONTEXT_CL", "8")
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        value, source = resolve_setting(
            "MACF_LOW_CONTEXT_CL", "context.low_context_cl", 5, coerce=int,
        )
    assert (value, source) == (8, "env")
    assert isinstance(value, int)


def test_env_coerce_failure_falls_through_with_warning(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("MACF_LOW_CONTEXT_CL", "not_an_int")
    _write_config(tmp_path, {"context": {"low_context_cl": 7}})
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        value, source = resolve_setting(
            "MACF_LOW_CONTEXT_CL", "context.low_context_cl", 5, coerce=int,
        )
    assert (value, source) == (7, "config")
    captured = capsys.readouterr()
    assert "failed coercion" in captured.err


def test_no_coerce_passes_value_through(monkeypatch, tmp_path):
    monkeypatch.setenv("MACEFF_AGENT_NAME", "MyAgent")
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        value, source = resolve_setting(
            "MACEFF_AGENT_NAME", "agent_identity.calling_card", None,
        )
    assert (value, source) == ("MyAgent", "env")


# ---- _load_maceff_config ------------------------------------------------

def test_load_returns_empty_when_file_absent(tmp_path):
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        assert _load_maceff_config() == {}


def test_load_returns_empty_on_malformed_json_with_warning(tmp_path, capsys):
    (tmp_path / ".maceff").mkdir()
    (tmp_path / ".maceff" / "config.json").write_text("{ not valid JSON")
    with patch("macf.utils.paths.find_agent_home", return_value=tmp_path):
        result = _load_maceff_config()
    assert result == {}
    captured = capsys.readouterr()
    assert "load failed" in captured.err
