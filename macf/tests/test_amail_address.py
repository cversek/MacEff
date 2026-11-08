"""MIS-0004 R06: an agent's zone address comes from the calling card in its home's identity file."""
import json
import os
from pathlib import Path

import pytest

from macf.amail.broker import BrokerConfig
from macf.amail.zone import local_part_from_card, zone_address, zone_local_part
from macf.pd.names import IdentityError


def _home(tmp_path: Path, name: str, card: str, uuid: str) -> Path:
    home = tmp_path / name
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": card}}))
    (home / ".maceff_primary_agent.id").write_text(uuid + "\n")
    return home


def test_address_from_identity_file(tmp_path, monkeypatch):
    """The card and the id's first six characters, lower-cased; the environment is never read."""
    home = _home(tmp_path, "wren_t", "WrenTuba", "3c9d1eaa-0000")
    monkeypatch.setenv("MACEFF_AGENT_NAME", "wren")
    assert zone_local_part(home) == "wrentuba_3c9d1e"
    assert zone_address(home, "Agents.Example.Org") == "wrentuba_3c9d1e@agents.example.org"


def test_a_home_that_names_no_agent_has_no_address(tmp_path):
    with pytest.raises(IdentityError):
        zone_local_part(tmp_path / "nobody")


def test_the_broker_resolves_a_zone_address_to_its_local_agent(tmp_path):
    home = _home(tmp_path, "wren_t", "WrenTuba", "3c9d1eaa-0000")
    cfg = BrokerConfig(domain="aero.local", zone="agents.example.org", agent_homes={"wren": home})
    assert cfg.agent_for("WrenTuba_3c9d1e@agents.example.org") == "wren"
    assert cfg.agent_for("wren@aero.local") == "wren"
    # The account name is not the zone address, and another agent's card is not ours.
    assert cfg.agent_for("wren_t_3c9d1e@agents.example.org") is None
    assert cfg.agent_for("iramaceff_ee9a78@agents.example.org") is None


def test_without_a_zone_the_broker_answers_only_for_its_domain(tmp_path):
    home = _home(tmp_path, "wren_t", "WrenTuba", "3c9d1eaa-0000")
    cfg = BrokerConfig(domain="aero.local", agent_homes={"wren": home})
    assert cfg.agent_for("wrentuba_3c9d1e@agents.example.org") is None


def test_a_home_without_an_identity_never_matches_and_never_raises(tmp_path):
    cfg = BrokerConfig(domain="aero.local", zone="agents.example.org", agent_homes={"ghost": tmp_path / "ghost"})
    assert cfg.agent_for("ghost_000000@agents.example.org") is None


def test_the_deployment_file_carries_the_zone_to_the_broker(tmp_path):
    """The zone is deployment fact: it reaches the broker from the addressing file, and its absence
    leaves the broker answering for its own domain only."""
    import yaml
    from macf.amail.deploy_config import BrokerDeployConfig
    base = {"domain": "aero.local",
            "agents": {"wren": {"home": str(tmp_path / "wren_t"), "uid": 1002, "contacts": [], "card": "WrenTuba@3c9d1e", "zone_token": "0123456789ab"}}}
    for zone in ("agents.example.org", None):
        addr = tmp_path / "addressing.yaml"
        addr.write_text(yaml.safe_dump({**base, **({"zone": zone} if zone else {})}))
        cfg = BrokerDeployConfig.model_validate({
            "addressing_path": str(addr), "audit_path": str(tmp_path / "audit.jsonl"),
            "inbound_quarantine": str(tmp_path / "q"), "inbound_handoff": str(tmp_path / "h"),
        }).to_broker_config()
        assert cfg.zone == zone


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through chmod 000")
def test_a_closed_home_resolves_through_the_declared_card(tmp_path):
    """In a container the broker's account cannot read a seat's .maceff (R05). Without a declared
    card the seat's zone mail would be refused as not ours; with one, it resolves."""
    home = _home(tmp_path, "wren_t", "WrenTuba", "3c9d1eaa-0000")
    (home / ".maceff").chmod(0)
    try:
        bare = BrokerConfig(domain="aero.local", zone="agents.example.org", agent_homes={"wren": home})
        assert bare.agent_for("wrentuba_3c9d1e@agents.example.org") is None
        carded = BrokerConfig(domain="aero.local", zone="agents.example.org", agent_homes={"wren": home},
                              agent_cards={"wren": "WrenTuba@3c9d1e"})
        assert carded.agent_for("wrentuba_3c9d1e@agents.example.org") == "wren"
    finally:
        (home / ".maceff").chmod(0o700)


def test_a_malformed_card_is_not_a_card():
    assert local_part_from_card("WrenTuba@3c9d1e") == "wrentuba_3c9d1e"
    for bad in ("WrenTuba", "@3c9d1e", "WrenTuba@3c9d"):
        with pytest.raises(ValueError):
            local_part_from_card(bad)


def _deploy(tmp_path, agents, zone="agents.example.org"):
    import yaml
    from macf.amail.deploy_config import BrokerDeployConfig
    addr = tmp_path / "addressing.yaml"
    addr.write_text(yaml.safe_dump({"domain": "aero.local", "zone": zone, "agents": agents}))
    return BrokerDeployConfig.model_validate({
        "addressing_path": str(addr), "audit_path": str(tmp_path / "audit.jsonl"),
        "inbound_quarantine": str(tmp_path / "q"), "inbound_handoff": str(tmp_path / "h"),
    })


def test_a_zone_start_refuses_an_agent_with_no_usable_card(tmp_path):
    """Never skipped silently: the start names the agent and the fix."""
    from macf.amail.deploy_config import ConfigError
    agents = {"wren": {"home": str(tmp_path / "closed"), "uid": 1002, "contacts": [], "zone_token": "0123456789ab"}}
    with pytest.raises(ConfigError, match="wren"):
        _deploy(tmp_path, agents).to_broker_config()
    agents["wren"]["card"] = "WrenTuba"
    with pytest.raises(ConfigError, match="not a calling card"):
        _deploy(tmp_path, agents).to_broker_config()
    agents["wren"]["card"] = "WrenTuba@3c9d1e"
    cfg = _deploy(tmp_path, agents).to_broker_config()
    assert cfg.agent_cards == {"wren": "WrenTuba@3c9d1e"}
    assert cfg.agent_for("_".join(["wrentuba", "3c9d1e", "0123456789ab"]) + "@agents.example.org") == "wren"
