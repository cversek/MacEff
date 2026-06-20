"""Tests for the AUTO_MODE auth-token bootstrap + fail-closed validation.

Coverage for cversek/MacEff#115:

1. Installation gap — ``macf_tools agent init-auth-token`` is the sanctioned
   host bootstrap that generates + writes ``auto_mode_auth_token`` into
   ``<agent_home>/.maceff/settings.json`` (previously only docker start.py
   created it, so bare-metal hosts had no path to the token).

2. Validation gap — ``set_auto_mode`` now FAILS CLOSED: a missing settings
   file or empty token is rejected instead of skipped, so an arbitrary
   non-empty string can no longer activate AUTO_MODE.
"""
import argparse
import json

from macf.utils.cycles import set_auto_mode
from macf.cli import cmd_agent_init_auth_token


# --- fail-closed validation -------------------------------------------------

def test_auto_mode_fails_closed_without_token_file(tmp_path):
    """No settings.json → AUTO_MODE rejected (was: any string accepted)."""
    ok, msg = set_auto_mode(
        enabled=True, session_id="s", auth_token="anything", agent_home=tmp_path
    )
    assert ok is False
    assert "not configured" in msg


def test_auto_mode_fails_closed_with_empty_token_in_file(tmp_path):
    """settings.json present but no token configured → still rejected."""
    maceff = tmp_path / ".maceff"
    maceff.mkdir()
    (maceff / "settings.json").write_text(json.dumps({"other": "x"}))
    ok, msg = set_auto_mode(
        enabled=True, session_id="s", auth_token="anything", agent_home=tmp_path
    )
    assert ok is False
    assert "not configured" in msg


def test_auto_mode_accepts_matching_token(tmp_path):
    maceff = tmp_path / ".maceff"
    maceff.mkdir()
    (maceff / "settings.json").write_text(
        json.dumps({"auto_mode_auth_token": "secret123"})
    )
    ok, _ = set_auto_mode(
        enabled=True, session_id="s", auth_token="secret123", agent_home=tmp_path
    )
    assert ok is True


def test_auto_mode_rejects_mismatched_token(tmp_path):
    maceff = tmp_path / ".maceff"
    maceff.mkdir()
    (maceff / "settings.json").write_text(
        json.dumps({"auto_mode_auth_token": "secret123"})
    )
    ok, msg = set_auto_mode(
        enabled=True, session_id="s", auth_token="wrong", agent_home=tmp_path
    )
    assert ok is False
    assert "Invalid" in msg


def test_manual_mode_never_needs_token(tmp_path):
    """MANUAL_MODE can always be set without auth (no token file present)."""
    ok, _ = set_auto_mode(
        enabled=False, session_id="s", auth_token=None, agent_home=tmp_path
    )
    assert ok is True


# --- bootstrap command ------------------------------------------------------

def test_init_auth_token_writes_token(tmp_path, monkeypatch):
    monkeypatch.setattr("macf.cli.find_agent_home", lambda: tmp_path)
    rc = cmd_agent_init_auth_token(argparse.Namespace(force=False))
    assert rc == 0
    settings = json.loads((tmp_path / ".maceff" / "settings.json").read_text())
    # secrets.token_hex(16) → 32 hex chars
    assert len(settings["auto_mode_auth_token"]) == 32


def test_init_auth_token_refuses_overwrite_without_force(tmp_path, monkeypatch):
    monkeypatch.setattr("macf.cli.find_agent_home", lambda: tmp_path)
    maceff = tmp_path / ".maceff"
    maceff.mkdir()
    (maceff / "settings.json").write_text(
        json.dumps({"auto_mode_auth_token": "existing"})
    )
    rc = cmd_agent_init_auth_token(argparse.Namespace(force=False))
    assert rc == 1
    # token unchanged
    assert json.loads(
        (maceff / "settings.json").read_text()
    )["auto_mode_auth_token"] == "existing"


def test_init_auth_token_force_regenerates_and_preserves_keys(tmp_path, monkeypatch):
    monkeypatch.setattr("macf.cli.find_agent_home", lambda: tmp_path)
    maceff = tmp_path / ".maceff"
    maceff.mkdir()
    (maceff / "settings.json").write_text(
        json.dumps({"auto_mode_auth_token": "old", "other": "keep"})
    )
    rc = cmd_agent_init_auth_token(argparse.Namespace(force=True))
    assert rc == 0
    s = json.loads((maceff / "settings.json").read_text())
    assert s["auto_mode_auth_token"] != "old"
    assert s["other"] == "keep"  # existing keys preserved


def test_init_token_then_activate_roundtrip(tmp_path, monkeypatch):
    """Bootstrap writes a token that set_auto_mode then accepts (end-to-end)."""
    monkeypatch.setattr("macf.cli.find_agent_home", lambda: tmp_path)
    cmd_agent_init_auth_token(argparse.Namespace(force=False))
    token = json.loads(
        (tmp_path / ".maceff" / "settings.json").read_text()
    )["auto_mode_auth_token"]
    ok, _ = set_auto_mode(
        enabled=True, session_id="s", auth_token=token, agent_home=tmp_path
    )
    assert ok is True
