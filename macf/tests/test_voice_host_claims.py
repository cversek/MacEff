"""Per-agent capture units on one host (a trial before the system daemon's shared unit): each claims its
keys and wake phrase in a host registry, so two agents never answer the same key or phrase (R26)."""
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from macf.voice.capture import claims
from macf.voice.capture.members import MembersRefused


def section(phrase=None, hold=None, toggle=None):
    return SimpleNamespace(wake_phrase=phrase, hold_key=hold, toggle_key=toggle, session_key=None, send_key=None)


def test_two_agents_with_different_keys_and_phrases_both_claim(tmp_path):
    registry = claims.HostClaims(tmp_path / "claims.json")
    registry.claim("Bez_bc8705", section("hey bez", hold="KEY_F9"), pid=os.getpid())
    registry.claim("Ira_ee9a78", section("hey ira", hold="KEY_F10"), pid=os.getpid())
    assert set(registry.live()) == {"Bez_bc8705", "Ira_ee9a78"}


def test_a_key_or_phrase_another_live_agent_holds_is_refused_naming_both(tmp_path):
    registry = claims.HostClaims(tmp_path / "claims.json")
    registry.claim("Bez_bc8705", section("hey bez", hold="KEY_F9"), pid=os.getpid())
    with pytest.raises(MembersRefused, match="KEY_F9"):
        registry.claim("Ira_ee9a78", section("hey ira", hold="KEY_F9"), pid=os.getpid())
    with pytest.raises(MembersRefused, match="hey bez"):
        registry.claim("Ira_ee9a78", section("Hey, Bez!", hold="KEY_F10"), pid=os.getpid())
    assert set(registry.live()) == {"Bez_bc8705"}  # a refused claim leaves nothing behind


def test_a_claim_whose_unit_has_died_is_released(tmp_path):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    registry = claims.HostClaims(tmp_path / "claims.json")
    registry.claim("Bez_bc8705", section(hold="KEY_F9"), pid=dead.pid)
    registry.claim("Ira_ee9a78", section(hold="KEY_F9"), pid=os.getpid())  # the dead unit's key is free
    assert set(registry.live()) == {"Ira_ee9a78"}


def test_an_agent_reclaiming_after_a_restart_replaces_its_own_claim(tmp_path):
    registry = claims.HostClaims(tmp_path / "claims.json")
    registry.claim("Bez_bc8705", section(hold="KEY_F9"), pid=os.getpid())
    registry.claim("Bez_bc8705", section(hold="KEY_F8"), pid=os.getpid())
    registry.claim("Ira_ee9a78", section(hold="KEY_F9"), pid=os.getpid())
    registry.release("Bez_bc8705")
    assert set(registry.live()) == {"Ira_ee9a78"}
