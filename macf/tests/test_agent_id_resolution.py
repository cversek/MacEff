"""An agent id that doesn't resolve falls back to the home's calling card, and when nothing resolves it is said (#1036)."""
import json

import pytest

from macf import config as cfg
from macf.config import ConsciousnessConfig


@pytest.fixture
def conf(monkeypatch):
    """A config with no container and no project, so only the env, the moniker and the home's card can answer."""
    monkeypatch.setattr(cfg, "_unresolved_said", False)
    monkeypatch.delenv("MACEFF_USER", raising=False)
    monkeypatch.delenv("USER", raising=False)
    c = ConsciousnessConfig()
    monkeypatch.setattr(c, "_is_container", lambda: False)
    monkeypatch.setattr(c, "_is_host", lambda: False)
    return c


def _home(tmp_path, monkeypatch, named=True):
    home = tmp_path / "home"
    (home / ".maceff").mkdir(parents=True)
    if named:
        (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Resident"}}))
        (home / ".maceff_primary_agent.id").write_text("abc123def4567890\n")
    monkeypatch.setattr("macf.utils.paths.find_agent_home", lambda *a, **k: home)
    return home


def test_with_no_user_and_no_moniker_the_id_is_the_calling_card_of_the_home(conf, tmp_path, monkeypatch, capsys):
    _home(tmp_path, monkeypatch)
    assert conf.agent_id == "Resident_abc123"
    assert capsys.readouterr().err == ""


def test_when_nothing_resolves_the_fallback_is_said_once_with_the_process_and_the_variables(conf, tmp_path, monkeypatch, capsys):
    _home(tmp_path, monkeypatch, named=False)
    assert conf.agent_id == "unknown_agent"
    said = capsys.readouterr().err
    assert "did not resolve" in said and "unknown_agent" in said
    assert "MACEFF_USER unset" in said and "USER unset" in said and "process " in said
    assert conf.agent_id == "unknown_agent"
    assert capsys.readouterr().err == "", "said once per process, not on every lookup"


def test_a_container_user_still_wins_over_the_card(conf, tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(conf, "_is_container", lambda: True)
    monkeypatch.setenv("MACEFF_USER", "pa_first")
    assert conf.agent_id == "pa_first"


def test_a_moniker_in_the_project_config_still_wins_over_the_card(conf, tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / ".maceff").mkdir(parents=True)
    (root / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"moniker": "FromProject"}}))
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(conf, "_is_host", lambda: True)
    monkeypatch.setattr(conf, "_find_project_root", lambda: root)
    assert conf.agent_id == "FromProject"


def test_the_shared_fallback_says_why_it_was_used(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cfg, "_unresolved_said", False)
    monkeypatch.delenv("MACEFF_USER", raising=False)
    monkeypatch.delenv("USER", raising=False)
    assert cfg.unresolved_agent_id("the config couldn't load: OSError") == "unknown_agent"
    assert "the config couldn't load" in capsys.readouterr().err
