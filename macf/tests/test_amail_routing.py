"""MIS-0004 R08 and R09: under one zone the domain no longer says which broker owns a mailbox.

R08: a broker chooses the rung from the declared map: its own agents are local, an agent a declared
peer lists is shared (rung 1s), and anything else is relay; the zone itself never decides.
R09: a broker reads only the intakes of peers its operator declares; with none declared, none.

Until MIS-0007's system daemon declares the map, a peer's agents are listed in the broker's own
deployment configuration (``SharedHandoff.agents``), a file no agent can write. Cards are made up.
"""
import json
from pathlib import Path

from conftest import _addressing

from macf.amail.broker import Broker, BrokerConfig, SharedHandoff, peer_intake
from macf.amail.models import Message

ZONE = "agents.example.org"
HOST, BOX = "host.local", "box.local"
IRA, MANNY = "IraTest@a1a1a1", "WrenTuba@3c9d1e"
IRA_Z, MANNY_Z = f"iratest_a1a1a1@{ZONE}", f"wrentuba_3c9d1e@{ZONE}"


def _deployment(tmp_path, name, domain, agent, card, contacts, peers):
    root = tmp_path / name
    root.mkdir()
    addressing = root / "addressing.yaml"
    addressing.write_text(_addressing({agent: contacts}, domain=domain))
    handoff = root / "handoff"
    (handoff / agent).mkdir(parents=True, mode=0o2770)
    (root / "home" / agent).mkdir(parents=True)
    cfg = BrokerConfig(domain=domain, zone=ZONE, agent_homes={agent: root / "home" / agent},
                       agent_cards={agent: card}, contacts_path=addressing,
                       audit_path=root / "audit.jsonl", dispositions_dir=root / "dispositions",
                       inbound_quarantine=root / "quarantine", inbound_handoff=handoff,
                       shared_handoffs=peers)
    return Broker(cfg)


def _pair(tmp_path, host_lists=(("manny", MANNY),)):
    host_root, box_root = tmp_path / "host" / "handoff", tmp_path / "box" / "handoff"
    host = _deployment(tmp_path, "host", HOST, "ira", IRA, [MANNY_Z],
                       {BOX: SharedHandoff(handoff=box_root, agents=dict(host_lists))})
    box = _deployment(tmp_path, "box", BOX, "manny", MANNY, [IRA_Z],
                      {HOST: SharedHandoff(handoff=host_root, agents={"ira": IRA})})
    peer_intake(host_root, BOX).mkdir(parents=True, mode=0o2770)
    peer_intake(box_root, HOST).mkdir(parents=True, mode=0o2770)
    return host, box


def test_rung_from_declared_map(tmp_path):
    host, _ = _pair(tmp_path)
    assert host._rung(IRA_Z) == "local"
    assert host._rung(MANNY_Z) == "shared"
    route = host.config.shared_for(MANNY_Z.upper())
    assert (route.domain, route.local) == (BOX, "manny"), "the peer's box name, not the zone local part"
    # Under the zone, an agent no declared peer lists is relay: the domain decides nothing.
    assert host._rung(f"stranger_ffffff@{ZONE}") == "relay"
    # The peer's own domain still routes as before.
    assert host._rung(f"manny@{BOX}") == "shared"


def test_an_unlisted_agent_of_a_declared_peer_is_not_shared(tmp_path):
    host, _ = _pair(tmp_path, host_lists=())
    assert host._rung(MANNY_Z) == "relay"


def test_zone_mail_crosses_the_mount_and_the_peer_delivers_it(tmp_path):
    host, box = _pair(tmp_path)
    r = host.submit("ira", Message(sender=IRA_Z, to=[MANNY_Z], subject="zone", body="hello"))
    assert r["ok"], r
    assert r["delivered"][0]["rung"] == "shared"
    pairs = sorted(peer_intake(box.config.inbound_handoff, HOST).glob("*.amsg"))
    assert len(pairs) == 1
    # The hand-off names the box as the peer files it (its own domain); the message keeps the zone address.
    assert json.loads(pairs[0].with_suffix(".json").read_text())["recipient"] == f"manny@{BOX}"
    results = box.sweep_shared()
    assert results and results[0]["accepted"] is True, results
    boxed = list((box.config.inbound_handoff / "manny").glob("*.amsg"))
    assert len(boxed) == 1 and MANNY_Z in boxed[0].read_text()


def test_only_declared_peers(tmp_path):
    """An intake directory for a peer nobody declared is never read; with none declared, none is."""
    host, box = _pair(tmp_path)
    stray = box.config.inbound_handoff / "_peers" / "stranger.local"
    stray.mkdir(parents=True)
    (stray / "x.amsg").write_text("From: a@b\n\nplanted\n")
    (stray / "x.json").write_text("{}")
    assert all(r.get("peer") != "stranger.local" for r in box.sweep_shared())
    assert (stray / "x.amsg").exists(), "an undeclared intake is left unread, not consumed"
    box.config.shared_handoffs.clear()
    assert box.sweep_shared() == []
    assert (stray / "x.amsg").exists()


def test_a_peer_may_only_speak_for_the_agents_it_is_declared_to_hold(tmp_path):
    """The receiving side's map decides whose zone mail a peer may carry: a sender the origin peer is
    not declared to hold is rejected, kept as evidence, and never reaches the box."""
    host, box = _pair(tmp_path)
    box.config.shared_handoffs[HOST].agents.clear()
    assert host.submit("ira", Message(sender=IRA_Z, to=[MANNY_Z], subject="z", body="b"))["ok"]
    results = box.sweep_shared()
    assert results and results[0]["accepted"] is False
    assert "declared" in results[0]["reason"]
    assert not list((box.config.inbound_handoff / "manny").glob("*.amsg"))
    assert list((peer_intake(box.config.inbound_handoff, HOST) / "rejected").glob("*.amsg"))


def test_the_deployment_file_declares_a_peers_agents_and_refuses_a_bad_card(tmp_path):
    import pytest
    from pydantic import ValidationError
    from macf.amail.deploy_config import SharedHandoffDecl
    decl = SharedHandoffDecl(handoff=tmp_path, agents={"manny": MANNY})
    assert decl.agents == {"manny": MANNY}
    with pytest.raises(ValidationError, match="not a calling card"):
        SharedHandoffDecl(handoff=tmp_path, agents={"manny": "WrenTuba"})
