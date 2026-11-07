"""MIS-0004 R06: an agent's zone address comes from the calling card in its home's identity file."""
import json
from pathlib import Path

import pytest

from macf.amail.broker import BrokerConfig
from macf.amail.zone import zone_address, zone_local_part


def _home(tmp_path: Path, name: str, card: str, uuid: str) -> Path:
    home = tmp_path / name
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": card}}))
    (home / ".maceff_primary_agent.id").write_text(uuid + "\n")
    return home


def test_address_from_identity_file(tmp_path, monkeypatch):
    """The card and the id's first six characters, lower-cased; the environment is never read."""
    home = _home(tmp_path, "rusty_t", "RustyTrombone", "15b944aa-0000")
    monkeypatch.setenv("MACEFF_AGENT_NAME", "rusty")
    assert zone_local_part(home) == "rustytrombone_15b944"
    assert zone_address(home, "Agents.Example.Org") == "rustytrombone_15b944@agents.example.org"


def test_a_home_that_names_no_agent_has_no_address(tmp_path):
    with pytest.raises(Exception):
        zone_local_part(tmp_path / "nobody")


def test_the_broker_resolves_a_zone_address_to_its_local_agent(tmp_path):
    home = _home(tmp_path, "rusty_t", "RustyTrombone", "15b944aa-0000")
    cfg = BrokerConfig(domain="aero.local", zone="agents.example.org", agent_homes={"rusty": home})
    assert cfg.agent_for("RustyTrombone_15b944@agents.example.org") == "rusty"
    assert cfg.agent_for("rusty@aero.local") == "rusty"
    # The account name is not the zone address, and another agent's card is not ours.
    assert cfg.agent_for("rusty_t_15b944@agents.example.org") is None
    assert cfg.agent_for("iramaceff_ee9a78@agents.example.org") is None


def test_without_a_zone_the_broker_answers_only_for_its_domain(tmp_path):
    home = _home(tmp_path, "rusty_t", "RustyTrombone", "15b944aa-0000")
    cfg = BrokerConfig(domain="aero.local", agent_homes={"rusty": home})
    assert cfg.agent_for("rustytrombone_15b944@agents.example.org") is None


def test_a_home_without_an_identity_never_matches_and_never_raises(tmp_path):
    cfg = BrokerConfig(domain="aero.local", zone="agents.example.org", agent_homes={"ghost": tmp_path / "ghost"})
    assert cfg.agent_for("ghost_000000@agents.example.org") is None


def test_the_deployment_file_carries_the_zone_to_the_broker(tmp_path):
    """The zone is deployment fact: it reaches the broker from the addressing file, and its absence
    leaves the broker answering for its own domain only."""
    import yaml
    from macf.amail.deploy_config import BrokerDeployConfig
    base = {"domain": "aero.local",
            "agents": {"rusty": {"home": str(tmp_path / "rusty_t"), "uid": 1002, "contacts": []}}}
    for zone in ("agents.example.org", None):
        addr = tmp_path / "addressing.yaml"
        addr.write_text(yaml.safe_dump({**base, **({"zone": zone} if zone else {})}))
        cfg = BrokerDeployConfig.model_validate({
            "addressing_path": str(addr), "audit_path": str(tmp_path / "audit.jsonl"),
            "inbound_quarantine": str(tmp_path / "q"), "inbound_handoff": str(tmp_path / "h"),
        }).to_broker_config()
        assert cfg.zone == zone
