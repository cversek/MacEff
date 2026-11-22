"""amail peer setup: the card a broker hands its peers, built from the operator's own files.

Every test here writes the broker config and the addressing file to disk and goes through the
loader the broker itself uses. The rung-2 tests that built their objects directly passed while a
loader could drop the agents map; a card built from objects would repeat that.
"""
import json
import os

import pytest
import yaml

from macf.amail import peer_setup
from macf.amail.registry import Registry

A_DOM = "alpha.test"


def _files(tmp_path, *, listen=True, agents=None):
    """An operator's broker config and addressing file on disk, as a host deployment writes them."""
    agents = agents if agents is not None else {
        "ira": {"uid": os.getuid(), "home": str(tmp_path / "ira"), "shared_uid": True, "card": "Ira_0a1b2c",
                "contacts": []},
        "bez": {"uid": os.getuid(), "home": str(tmp_path / "bez"), "shared_uid": True, "card": "Bez_3d4e5f",
                "contacts": []},
    }
    addressing = tmp_path / "addressing.yaml"
    addressing.write_text(yaml.safe_dump({"domain": A_DOM, "tier": "host",
                                          "supervision": "operator-at-terminal", "agents": agents}))
    broker = {"addressing_path": str(addressing)}
    if listen:
        broker["peer_listen"] = {"host": "100.64.0.7", "port": 8030}
    path = tmp_path / "broker_config.yaml"
    path.write_text(yaml.safe_dump(broker))
    return path


def _registry(tmp_path, entries):
    reg = tmp_path / "registry.yaml"
    reg.write_text(yaml.safe_dump({"agents": entries}))
    os.chmod(reg, 0o644)
    return Registry(reg, root_uid=os.getuid())


def _key(tmp_path, name):
    from macf.amail.crypto import generate_keypair
    return generate_keypair(tmp_path / name)


def test_the_card_carries_what_a_peer_needs_read_from_the_operators_files(tmp_path):
    """Domain, the declared listener, each named agent's card, its registry key and the account that
    holds it: everything the peer's operator writes, and nothing a peer could not be given."""
    ira_key = _key(tmp_path, "ira_key")
    card = peer_setup.build_card(_files(tmp_path), agents=["ira"],
                                 registry=_registry(tmp_path, {"Ira_0a1b2c": {"account": "ira", "keys": [ira_key]}}))
    assert card["amail_peer_card"] == peer_setup.CARD_VERSION
    assert (card["domain"], card["host"], card["port"]) == (A_DOM, "100.64.0.7", 8030)
    assert card["agents"] == {"ira": {"card": "Ira_0a1b2c", "key": ira_key, "account": "ira"}}
    assert "PRIVATE" not in peer_setup.render_card(card)


def test_an_agent_the_registry_lacks_falls_back_to_its_own_key_and_says_so(tmp_path):
    """The agent's own key file is the next source for its own card; an agent with neither is still on
    the card, with no key, and the card says its mail will read unverified until one is declared."""
    own = _key(tmp_path, "own_key")
    card = peer_setup.build_card(_files(tmp_path), agents=["ira", "bez"], registry=_registry(tmp_path, {}),
                                 own_agent="ira", own_key=tmp_path / "own_key")
    assert card["agents"]["ira"]["key"] == own
    assert card["agents"]["bez"]["key"] is None
    assert any("bez" in n and "unverified" in n for n in card["notes"])


def test_a_broker_with_no_declared_listener_has_no_card(tmp_path):
    """A peer cannot reach a broker that listens nowhere, so the card is refused and the reason names
    the declaration that is missing."""
    with pytest.raises(peer_setup.CardError, match="peer_listen"):
        peer_setup.build_card(_files(tmp_path, listen=False), agents=["ira"], registry=_registry(tmp_path, {}))


def test_an_agent_not_in_the_addressing_file_is_refused(tmp_path):
    with pytest.raises(peer_setup.CardError, match="nobody"):
        peer_setup.build_card(_files(tmp_path), agents=["nobody"], registry=_registry(tmp_path, {}))


def test_a_card_reads_back_as_written_and_a_bad_one_is_refused_by_the_declarations_own_rules(tmp_path):
    """The card is the interchange format `peer add` reads: it round-trips, and a card naming a public
    address or a non-card is refused with the same rules the operator's declaration enforces."""
    card = peer_setup.build_card(_files(tmp_path), agents=["ira"], registry=_registry(tmp_path, {}))
    assert peer_setup.parse_card(peer_setup.render_card(card)) == card
    for bad in ({**card, "host": "8.8.8.8"}, {**card, "agents": {"ira": {"card": "not a card"}}},
                {**card, "amail_peer_card": 99}, {**card, "secret": "x"},
                {**card, "agents": {"ira": {"card": "Ira_0a1b2c", "key": "ed25519:not-a-key"}}}):
        with pytest.raises(peer_setup.CardError):
            peer_setup.parse_card(json.dumps(bad))


def test_the_operators_steps_are_printed_never_run(tmp_path):
    """The registry is root's to write: the card's description prints the declare line for each keyed
    agent, with its account, and the peer link entry, for the peer's operator to run."""
    ira_key = _key(tmp_path, "ira_key")
    card = peer_setup.build_card(_files(tmp_path), agents=["ira"],
                                 registry=_registry(tmp_path, {"Ira_0a1b2c": {"account": "ira", "keys": [ira_key]}}))
    text = "\n".join(peer_setup.describe(card))
    assert f"amail registry declare --card Ira_0a1b2c --key {ira_key} --account ira" in text
    assert f"amail peer add" in text
