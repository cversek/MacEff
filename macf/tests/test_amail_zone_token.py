"""MIS-0004 R06 revised, and the token's handling: a zone address the public card doesn't give away.

The local part is ``name_shortid_token``. The token is a random value declared per agent at
provisioning, never derived from the identity, so an exposed one is rotated: it goes on the
deployment's revoked list and is refused at once. Every token and card here is made up, and the
addresses are assembled from their parts so no fixture line carries a whole token address.
"""
import pytest
import yaml

from macf.amail.broker import BrokerConfig, SharedHandoff
from macf.amail.deploy_config import BrokerDeployConfig, ConfigError
from macf.amail.zone import local_part_from_card

ZONE = "agents.example.org"
CARD, OTHER = "WrenTuba_3c9d1e", "IraTest_a1a1a1"
TOKEN, NEW, PEER_TOKEN = "0123456789ab", "fedcba987654", "aaaabbbbcccc"
SEP = "_"


def addr(card, token):
    name, short = card.lower().split("_")
    return SEP.join([name, short, token]) + "@" + ZONE


def test_the_local_part_carries_the_token_and_the_card_alone_is_not_an_address():
    assert local_part_from_card(CARD, TOKEN) == SEP.join(["wrentuba", "3c9d1e", TOKEN])
    cfg = BrokerConfig(domain="box.local", zone=ZONE, agent_homes={"wren": "/nonexistent"},
                       agent_cards={"wren": CARD}, agent_zone_tokens={"wren": TOKEN})
    assert cfg.agent_for(addr(CARD, TOKEN)) == "wren"
    assert cfg.agent_for("wrentuba_3c9d1e@" + ZONE) is None, "the public card alone must not reach the agent"
    assert cfg.zone_address_for("wren") == addr(CARD, TOKEN)


@pytest.mark.parametrize("bad", ["", "0123456789a", "0123456789AB", "0123456789ag", "g" * 12])
def test_a_token_is_twelve_or_more_lowercase_hex(bad):
    with pytest.raises(ValueError):
        local_part_from_card(CARD, bad)


def test_a_revoked_token_is_refused_at_once():
    cfg = BrokerConfig(domain="box.local", zone=ZONE, agent_homes={"wren": "/nonexistent"},
                       agent_cards={"wren": CARD}, agent_zone_tokens={"wren": NEW},
                       revoked_zone_tokens={TOKEN})
    assert cfg.agent_for(addr(CARD, TOKEN)) is None, "the old address is dead the moment it is revoked"
    assert cfg.agent_for(addr(CARD, NEW)) == "wren"


def test_a_peer_routes_by_card_and_token_and_never_by_a_revoked_one():
    peer = SharedHandoff(handoff="/x", agents={"ira": (OTHER, PEER_TOKEN)})
    cfg = BrokerConfig(domain="box.local", zone=ZONE, shared_handoffs={"host.local": peer})
    route = cfg.shared_for(addr(OTHER, PEER_TOKEN))
    assert (route.domain, route.local) == ("host.local", "ira")
    assert cfg.shared_for("iratest_a1a1a1@" + ZONE) is None
    cfg.revoked_zone_tokens = {PEER_TOKEN}
    assert cfg.shared_for(addr(OTHER, PEER_TOKEN)) is None


def _start(tmp_path, agent, revoked=(), peers=None):
    a = tmp_path / "addressing.yaml"
    a.write_text(yaml.safe_dump({"domain": "box.local", "zone": ZONE, "revoked_zone_tokens": list(revoked),
                                 "agents": {"wren": {"home": str(tmp_path / "w"), "uid": 1002, "contacts": [], **agent}}}))
    return BrokerDeployConfig.model_validate({
        "addressing_path": str(a), "audit_path": str(tmp_path / "a.jsonl"),
        "inbound_quarantine": str(tmp_path / "q"), "inbound_handoff": str(tmp_path / "h"),
        "shared_handoffs": peers or {}}).to_broker_config()


def test_a_zone_start_refuses_a_missing_malformed_or_revoked_token(tmp_path):
    with pytest.raises(ConfigError, match="zone_token"):
        _start(tmp_path, {"card": CARD})
    with pytest.raises(ConfigError, match="zone_token"):
        _start(tmp_path, {"card": CARD, "zone_token": "0123456789AB"})
    with pytest.raises(ConfigError, match="revoked"):
        _start(tmp_path, {"card": CARD, "zone_token": TOKEN}, revoked=[TOKEN])
    cfg = _start(tmp_path, {"card": CARD, "zone_token": NEW}, revoked=[TOKEN])
    assert cfg.agent_for(addr(CARD, NEW)) == "wren" and cfg.agent_for(addr(CARD, TOKEN)) is None


def test_a_peer_declaration_needs_the_token_and_double_claims_count_the_full_address(tmp_path):
    with pytest.raises(ConfigError, match="zone_token"):
        _start(tmp_path, {"card": CARD, "zone_token": NEW},
               peers={"host.local": {"handoff": str(tmp_path / "p"), "agents": {"ira": {"card": OTHER}}}})
    # The same card with a different token is a different address, so it is no double claim ...
    _start(tmp_path, {"card": CARD, "zone_token": NEW},
           peers={"host.local": {"handoff": str(tmp_path / "p"), "agents": {"w2": {"card": CARD, "zone_token": PEER_TOKEN}}}})
    # ... and the same full address twice is.
    with pytest.raises(ConfigError, match="claimed more than once"):
        _start(tmp_path, {"card": CARD, "zone_token": NEW},
               peers={"host.local": {"handoff": str(tmp_path / "p"), "agents": {"w2": {"card": CARD, "zone_token": NEW}}}})


def test_an_address_is_redacted_to_its_card_part():
    """MIS-0004 R49: what a log or a reason may say about a zone address."""
    from macf.amail.zone import redact_address
    assert redact_address("someone_0a1b2c_" + TOKEN + "@zone.example") == "someone_0a1b2c_<token>@zone.example"
    assert redact_address("someone_0a1b2c@zone.example") == "someone_0a1b2c@zone.example"
    assert redact_address("nobody@elsewhere.example") == "nobody@elsewhere.example"
    assert redact_address("") == ""


def test_a_sender_resolves_to_a_card_only_at_its_own_domain():
    """MIS-0004 R44: the card a signature is judged by comes from the domain the address belongs
    to. A stranger elsewhere who picks one of our cards, or a zone-shaped local part, is outside
    mail and stays unverified, not judged against our agent's keys."""
    from macf.amail.zone import card_for_address
    ours = {"domain": "here.example", "zone": "zone.example", "agent_cards": {"alice": "Alice_0a1b2c"},
            "peers": {"peer.example": {"bob": "Bob_3d4e5f", "carol": ("Carol_6a7b8c", TOKEN)}}}
    resolve = lambda address: card_for_address(address, **ours)   # noqa: E731
    # Our own domain: a declared name, or a card-shaped local part.
    assert resolve("alice@here.example") == "Alice_0a1b2c"
    assert resolve("dave_9e8f7a@here.example") == "dave_9e8f7a"
    # The zone: a zone address with its token removed, and nothing else.
    assert resolve(f"alice_0a1b2c_{TOKEN}@zone.example") == "alice_0a1b2c"
    assert resolve("alice_0a1b2c@zone.example") is None
    # A declared peer: its box map, tokened or not, or a card-shaped local part.
    assert resolve("bob@peer.example") == "Bob_3d4e5f"
    assert resolve("carol@peer.example") == "Carol_6a7b8c"
    assert resolve("erin_1a2b3c@peer.example") == "erin_1a2b3c"
    # Anywhere else: nothing, however card-shaped (the host-side maintainer's probes on #937).
    assert resolve("Alice_0a1b2c@elsewhere.example") is None
    assert resolve(f"alice_0a1b2c_{TOKEN}@elsewhere.example") is None
    assert resolve("alice@elsewhere.example") is None
    assert resolve("beta@peer.example") is None
    assert resolve("not an address") is None
