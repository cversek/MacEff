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


# ---- phase 2: peer add ---------------------------------------------------------------------------

B_DOM = "beta.test"

BROKER_WITH_COMMENTS = """\
# operator's broker config, comments kept
addressing_path: {addressing}
peer_listen: {{host: 100.64.0.7, port: 8030}}   # tailnet only
rate_limit_per_agent: 30
"""


def _beta_card(tmp_path, key=None):
    """The card a peer broker at beta.test would send: one agent, sparrow."""
    return {"amail_peer_card": peer_setup.CARD_VERSION, "domain": B_DOM, "host": "100.64.0.9", "port": 8030,
            "agents": {"sparrow": {"card": "Sparrow_6a7b8c", "key": key, "account": "sparrow"}}}


def _alpha(tmp_path):
    path = _files(tmp_path)
    path.write_text(BROKER_WITH_COMMENTS.format(addressing=tmp_path / "addressing.yaml"))
    addressing = tmp_path / "addressing.yaml"
    addressing.write_text("# who exists here\n" + addressing.read_text())
    return path, addressing


def test_adding_a_peer_writes_the_link_and_contacts_and_keeps_every_other_line(tmp_path):
    """The link with its agents map, and a contact for each local agent named, and nothing else: the
    operator's comments and every line the change does not own read the same after."""
    broker, addressing = _alpha(tmp_path)
    before_b, before_a = broker.read_text(), addressing.read_text()
    plan = peer_setup.plan_add(broker, _beta_card(tmp_path), local_agents=["ira"])
    plan.write()
    after_b, after_a = broker.read_text(), addressing.read_text()
    for line in before_b.splitlines():
        assert line in after_b.splitlines()
    for line in before_a.splitlines():
        assert line in after_a.splitlines()
    from macf.amail.deploy_config import BrokerDeployConfig, load_declarative_config
    cfg = BrokerDeployConfig.model_validate(load_declarative_config(broker)).to_broker_config()
    assert cfg.peer_links[B_DOM].agents == {"sparrow": "Sparrow_6a7b8c"}
    assert (cfg.peer_links[B_DOM].host, cfg.peer_links[B_DOM].port) == ("100.64.0.9", 8030)
    contacts = yaml.safe_load(after_a)["agents"]
    assert {"address": f"sparrow@{B_DOM}", "direction": "both"} in contacts["ira"]["contacts"]
    assert not contacts["bez"]["contacts"], "only the agents named get the contact"


def test_adding_the_same_card_twice_changes_nothing(tmp_path):
    broker, addressing = _alpha(tmp_path)
    peer_setup.plan_add(broker, _beta_card(tmp_path), local_agents=["ira"]).write()
    texts = broker.read_text(), addressing.read_text()
    again = peer_setup.plan_add(broker, _beta_card(tmp_path), local_agents=["ira"])
    assert not again.changed
    assert (broker.read_text(), addressing.read_text()) == texts


def test_a_card_for_our_own_domain_or_a_shared_one_is_refused_before_anything_is_written(tmp_path):
    """The declaration's own rules, met through the loader on the candidate files: nothing is shown
    that the broker would refuse to start on."""
    broker, addressing = _alpha(tmp_path)
    before = broker.read_text(), addressing.read_text()
    own = {**_beta_card(tmp_path), "domain": A_DOM}
    with pytest.raises(peer_setup.CardError, match="own domain"):
        peer_setup.plan_add(broker, own, local_agents=["ira"])
    assert (broker.read_text(), addressing.read_text()) == before


def test_a_change_the_text_edit_cannot_make_exactly_is_refused_not_approximated(tmp_path):
    """peer_links written inline with entries can't be edited line by line without touching lines the
    change doesn't own, so the add is refused with the entry to write by hand."""
    broker, _ = _alpha(tmp_path)
    broker.write_text(broker.read_text() + "peer_links: {gamma.test: {host: 100.64.0.10, port: 8030}}\n")
    with pytest.raises(peer_setup.CardError, match="by hand"):
        peer_setup.plan_add(broker, _beta_card(tmp_path), local_agents=["ira"])


def test_a_new_card_for_a_declared_peer_replaces_its_link(tmp_path):
    """A peer that moved or added an agent sends a new card; its one link is replaced, not doubled."""
    broker, _ = _alpha(tmp_path)
    peer_setup.plan_add(broker, _beta_card(tmp_path), local_agents=["ira"], note="beta's broker").write()
    moved = {**_beta_card(tmp_path), "host": "100.64.0.11"}
    peer_setup.plan_add(broker, moved, local_agents=["ira"]).write()
    links = yaml.safe_load(broker.read_text())["peer_links"]
    assert list(links) == [B_DOM] and links[B_DOM]["host"] == "100.64.0.11"
    assert links[B_DOM]["note"] == "beta's broker", "the operator's note survives a new card"
    assert broker.read_text().count(B_DOM) == 1, "one line for the peer, replaced in place"


def test_a_plan_refuses_to_write_over_a_file_that_changed_and_names_an_unknown_agent(tmp_path):
    broker, _ = _alpha(tmp_path)
    with pytest.raises(peer_setup.CardError, match="nobody"):
        peer_setup.plan_add(broker, _beta_card(tmp_path), local_agents=["nobody"])
    plan = peer_setup.plan_add(broker, _beta_card(tmp_path), local_agents=["ira"])
    broker.write_text(broker.read_text() + "# the operator edited it meanwhile\n")
    with pytest.raises(peer_setup.CardError, match="changed since"):
        plan.write()
    assert B_DOM not in broker.read_text()


def test_the_text_edit_refuses_an_inline_map_it_cannot_extend_one_line_at_a_time():
    with pytest.raises(peer_setup.CardError, match="by hand"):
        peer_setup.set_mapping_entry("peer_links: {gamma.test: {host: 100.64.0.10, port: 8030}}\n",
                                     "peer_links", B_DOM, {"host": "100.64.0.9", "port": 8030})


def test_an_edit_that_changes_more_than_its_one_entry_is_refused(tmp_path):
    """The second check on every edit: parsed, the new text is the old data with exactly the intended
    change made, or nothing is shown."""
    from pathlib import Path
    with pytest.raises(peer_setup.CardError, match="more than"):
        peer_setup._expect("a: 1\nb: 2\n", "a: 1\nb: 3\nc: 4\n", lambda d: d.__setitem__("c", 4), Path("x"))


def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _deployment_on_disk(tmp_path, name, domain, agent, card, port):
    """A whole host deployment as an operator writes it: broker config and addressing file, every
    store under tmp_path/<name>, the listener declared on loopback at *port*."""
    root = tmp_path / name
    (root / "handoff" / agent).mkdir(parents=True)
    (root / "home" / agent).mkdir(parents=True)
    addressing = root / "addressing.yaml"
    addressing.write_text(yaml.safe_dump({"domain": domain, "tier": "host", "supervision": "operator-at-terminal",
                                          "agents": {agent: {"uid": os.getuid(), "home": str(root / "home" / agent),
                                                             "shared_uid": True, "card": card, "contacts": []}}}))
    broker = root / "broker_config.yaml"
    broker.write_text(yaml.safe_dump({
        "addressing_path": str(addressing), "audit_path": str(root / "audit.jsonl"),
        "socket_path": str(root / "broker.sock"), "inbound_quarantine": str(root / "quarantine"),
        "inbound_handoff": str(root / "handoff"), "dispositions_dir": str(root / "dispositions"),
        "ledger_dir": str(root / "ledger"), "rate_limit_dir": None,
        "peer_listen": {"host": "127.0.0.1", "port": port}}))
    return broker


def test_two_brokers_set_up_from_each_others_cards_exchange_mail_both_ways(tmp_path):
    """The whole setup with nothing typed by hand: each broker's card, added on the other, and the
    brokers built from the resulting files by the loader they run on, pass a message each way."""
    from macf.amail.broker import Broker
    from macf.amail.deploy_config import BrokerDeployConfig, load_declarative_config
    from macf.amail.models import Message
    from macf.amail.peer_link import PeerListener
    a_port, b_port = _free_port(), _free_port()
    alpha_cfg = _deployment_on_disk(tmp_path, "alpha", A_DOM, "ira", "Ira_0a1b2c", a_port)
    beta_cfg = _deployment_on_disk(tmp_path, "beta", B_DOM, "sparrow", "Sparrow_6a7b8c", b_port)
    alpha_card = peer_setup.build_card(alpha_cfg, agents=["ira"])
    beta_card = peer_setup.build_card(beta_cfg, agents=["sparrow"])
    peer_setup.plan_add(alpha_cfg, beta_card, local_agents=["ira"]).write()
    peer_setup.plan_add(beta_cfg, alpha_card, local_agents=["sparrow"]).write()

    def _broker(path):
        return Broker(BrokerDeployConfig.model_validate(load_declarative_config(path)).to_broker_config())
    alpha, beta = _broker(alpha_cfg), _broker(beta_cfg)
    on_alpha = PeerListener(alpha, host="127.0.0.1", port=a_port).start()
    on_beta = PeerListener(beta, host="127.0.0.1", port=b_port).start()
    try:
        assert alpha.submit("ira", Message(sender=f"ira@{A_DOM}", to=[f"sparrow@{B_DOM}"], subject="s",
                                           body="from alpha"))["ok"]
        assert beta.submit("sparrow", Message(sender=f"sparrow@{B_DOM}", to=[f"ira@{A_DOM}"], subject="s",
                                              body="from beta"))["ok"]
        beta.sweep_shared()
        alpha.sweep_shared()
        assert len(list((tmp_path / "beta" / "handoff" / "sparrow").glob("*.amsg"))) == 1
        assert len(list((tmp_path / "alpha" / "handoff" / "ira").glob("*.amsg"))) == 1
    finally:
        on_alpha.stop()
        on_beta.stop()


# ---- phase 3: peer check -------------------------------------------------------------------------------

class _Linked:
    """Two brokers set up from each other's cards on disk, each holding the other's key in its own
    registry, both listening. Rebuild a side after editing its files with ``rebuild``."""

    def __init__(self, tmp_path, *, alpha_knows_beta=True, beta_knows_alpha=True):
        from macf.amail.crypto import generate_keypair
        self.tmp = tmp_path
        self.a_port, self.b_port = _free_port(), _free_port()
        self.alpha_cfg = _deployment_on_disk(tmp_path, "alpha", A_DOM, "ira", "Ira_0a1b2c", self.a_port)
        self.beta_cfg = _deployment_on_disk(tmp_path, "beta", B_DOM, "sparrow", "Sparrow_6a7b8c", self.b_port)
        keys = tmp_path / "keys"
        self.ira_key = generate_keypair(keys / "ira")
        self.sparrow_key = generate_keypair(keys / "sparrow")
        self.alpha_reg = _registry(tmp_path / "alpha", {"Sparrow_6a7b8c": {"account": "sparrow",
                                                                           "keys": [self.sparrow_key]}}
                                   if alpha_knows_beta else {})
        self.beta_reg = _registry(tmp_path / "beta", {"Ira_0a1b2c": {"account": "ira", "keys": [self.ira_key]}}
                                  if beta_knows_alpha else {})
        peer_setup.plan_add(self.alpha_cfg, peer_setup.build_card(self.beta_cfg, agents=["sparrow"]),
                            local_agents=["ira"]).write()
        peer_setup.plan_add(self.beta_cfg, peer_setup.build_card(self.alpha_cfg, agents=["ira"]),
                            local_agents=["sparrow"]).write()
        self.alpha = self.beta = self.on_beta = None
        self.rebuild()

    def _broker(self, path, reg):
        from macf.amail.broker import Broker
        from macf.amail.deploy_config import BrokerDeployConfig, load_declarative_config
        b = Broker(BrokerDeployConfig.model_validate(load_declarative_config(path)).to_broker_config())
        b.registry = reg
        return b

    def rebuild(self):
        from macf.amail.peer_link import PeerListener
        if self.on_beta:
            self.on_beta.stop()
        self.alpha = self._broker(self.alpha_cfg, self.alpha_reg)
        self.beta = self._broker(self.beta_cfg, self.beta_reg)
        self.on_beta = PeerListener(self.beta, host="127.0.0.1", port=self.b_port).start()

    def check(self, **kw):
        return {s.name: s for s in peer_setup.check_peer(self.alpha_cfg, B_DOM, registry=self.alpha_reg, **kw)}

    def send(self):
        from macf.amail.crypto import load_private_key, sign
        from macf.amail.models import Message
        m = Message(sender=f"ira@{A_DOM}", to=[f"sparrow@{B_DOM}"], subject="amail peer check", body="test")
        m.signature = sign(m, load_private_key(self.tmp / "keys" / "ira"))
        return self.alpha.submit("ira", m)

    def drop_agents(self, path):
        raw = yaml.safe_load(path.read_text())
        for link in raw["peer_links"].values():
            link.pop("agents", None)
        path.write_text(yaml.safe_dump(raw))


@pytest.fixture
def linked(tmp_path):
    pair = _Linked(tmp_path)
    yield pair
    pair.on_beta.stop()


def test_a_healthy_link_passes_every_station_and_its_test_message_reads_attested(linked):
    stations = linked.check(send=linked.send)
    assert {n: s.ok for n, s in stations.items()} == {
        "config": True, "our agents map": True, "our registry": True, "listener": True, "address": True,
        "build": True, "their agents map": True, "their registry": True, "test message": True}, stations
    linked.beta.sweep_shared()
    (amsg,) = (linked.tmp / "beta" / "handoff" / "sparrow").glob("*.amsg")
    assert json.loads(amsg.with_suffix(".json").read_text())["broker_trust"] == "attested"


def test_a_peer_that_is_down_fails_at_its_listener_and_nothing_past_it_runs(linked):
    linked.on_beta.stop()
    stations = linked.check()
    assert stations["listener"].ok is False and "their agents map" not in stations
    assert "peer_listen" in stations["listener"].fix


def test_a_peer_that_does_not_declare_this_host_fails_at_the_address(linked):
    """The listener closes an undeclared address unread (R59); the check names that, not an outage."""
    raw = yaml.safe_load(linked.beta_cfg.read_text())
    raw["peer_links"] = {"gamma.test": {"host": "127.0.0.2", "port": 8030}}
    linked.beta_cfg.write_text(yaml.safe_dump(raw))
    linked.rebuild()
    stations = linked.check()
    assert stations["address"].ok is False and "peer card" in stations["address"].fix


def test_a_missing_agents_map_on_either_side_is_named_where_it_is(linked):
    """The defect the first live run found by hand: a link that declares no agents, so nothing can
    read attested. Missing on the peer's side and on this side, each fails its own station."""
    linked.drop_agents(linked.beta_cfg)
    linked.rebuild()
    assert linked.check()["their agents map"].ok is False
    linked.drop_agents(linked.alpha_cfg)
    assert linked.check()["our agents map"].ok is False


def test_a_key_missing_from_either_registry_is_named_where_it_is(tmp_path):
    pair = _Linked(tmp_path, alpha_knows_beta=False, beta_knows_alpha=False)
    try:
        stations = pair.check()
        assert stations["our registry"].ok is False and stations["their registry"].ok is False
        assert "registry" in stations["their registry"].fix
    finally:
        pair.on_beta.stop()


def test_a_peer_on_an_older_build_is_reported_not_failed(linked, monkeypatch):
    from macf.amail import peer_link
    monkeypatch.setattr(peer_link, "OPS", ("hand_off",))
    stations = linked.check()
    assert stations["build"].ok is None and "older build" in stations["build"].detail
    assert "their agents map" not in stations


def test_a_test_message_the_peer_cannot_store_fails_with_the_peers_reason(linked, monkeypatch):
    """The class the half-written pair belonged to: the peer is reachable and declared, and still
    cannot store the message. The last station fails and carries the peer's reason."""
    def cannot(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(linked.beta, "take_over_link", cannot)
    stations = linked.check(send=linked.send)
    assert stations["test message"].ok is False and "could not store" in stations["test message"].detail
