"""MIS-0004's hand-off rows, on real brokers over one tmp tree.

- R14 (intake_name_MUST_be_unique): no send overwrites another, whatever its
  recipients or timing.
- R15 (message_id_MUST_be_one_from_acceptance): the id the accepting broker
  mints is the id the recipient reads, across a shared hand-off too.
- R38 (broker_MUST_write_one_copy_per_recipient): one file per recipient,
  never one file hard-linked into several boxes.

The shared hand-off tests use two brokers, because R15's failure lived in the
seam between them: the receiving broker minted a second id.
"""
import json
import os

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from conftest import _addressing

from macf.amail import store
from macf.amail.broker import _ID_RE, Broker, BrokerConfig, SharedHandoff, peer_intake
from macf.amail.client import ingest
from macf.amail.models import Message

HOST, BOX = "host.local", "box.local"


def _broker(root, domain, agents, peers=None):
    """A deployment under *root*: addressing, a 2770 box per agent, audit,
    dispositions and quarantine. *peers* maps a peer domain to its hand-off root."""
    root.mkdir(parents=True)
    addressing = root / "addressing.yaml"
    addressing.write_text(_addressing(agents, domain=domain))
    handoff = root / "handoff"
    handoff.mkdir()
    for a in agents:
        (handoff / a).mkdir(mode=0o2770)
        (root / "home" / a).mkdir(parents=True)
    return Broker(BrokerConfig(
        domain=domain,
        agent_homes={a: root / "home" / a for a in agents},
        contacts_path=addressing,
        audit_path=root / "audit.jsonl",
        dispositions_dir=root / "dispositions",
        inbound_quarantine=root / "quarantine",
        inbound_handoff=handoff,
        shared_handoffs={d: SharedHandoff(handoff=p) for d, p in (peers or {}).items()},
    ))


@pytest.fixture
def local(tmp_path):
    """One deployment whose three agents may all write to each other."""
    agents = {"ira": [f"manny@{HOST}", f"rusty@{HOST}"],
              "manny": [f"ira@{HOST}"], "rusty": [f"ira@{HOST}"]}
    return _broker(tmp_path / "host", HOST, agents)


@pytest.fixture
def host(tmp_path):
    """The sending deployment, declaring the box deployment as a shared peer.
    It provisions the intake the box broker will write into, as an owner does."""
    broker = _broker(tmp_path / "host", HOST, {"ira": [f"manny@{BOX}"]},
                     {BOX: tmp_path / "box" / "handoff"})
    peer_intake(broker.config.inbound_handoff, BOX).mkdir(parents=True, mode=0o2770)
    return broker


@pytest.fixture
def box(tmp_path, host):
    """The receiving deployment. It provisions the intake the host writes into."""
    broker = _broker(tmp_path / "box", BOX, {"manny": [f"ira@{HOST}"]},
                     {HOST: host.config.inbound_handoff})
    peer_intake(broker.config.inbound_handoff, HOST).mkdir(parents=True, mode=0o2770)
    return broker


def _msg(sender, *to, body="hand-off"):
    return Message(sender=sender, to=list(to), subject="hand-off", body=body)


def _box_pairs(broker, agent):
    return sorted((broker.config.inbound_handoff / agent).glob("*.amsg"))


def _ingest(broker, agent):
    return ingest(broker.config.agent_homes[agent], broker.config.inbound_handoff / agent,
                  broker.config.contacts_path, agent)


# ---------------------------------------------------------------- R15

def test_one_id_end_to_end(host, box):
    """The id the host broker minted at acceptance is the id in the box's
    sidecar, the id the recipient ingests, and the id the sender was told."""
    r = host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
    assert r["ok"], r
    minted = r["message_id"]
    assert _ID_RE.match(minted)
    swept = box.sweep_shared()
    assert [s["decision"] for s in swept] == ["delivered"]
    [pair] = _box_pairs(box, "manny")
    assert json.loads(pair.with_suffix(".json").read_text())["message_id"] == minted
    got = _ingest(box, "manny")
    assert got and got[0]["ingested"] is True
    [read] = store.read_all(box.config.agent_homes["manny"])
    assert read.message_id == minted


def test_one_id_end_to_end_on_one_broker(local):
    """The same property without a shared hand-off: one broker accepts and hands off."""
    r = local.submit("ira", _msg(f"ira@{HOST}", f"manny@{HOST}"))
    assert r["ok"], r
    [pair] = _box_pairs(local, "manny")
    assert json.loads(pair.with_suffix(".json").read_text())["message_id"] == r["message_id"]
    _ingest(local, "manny")
    [read] = store.read_all(local.config.agent_homes["manny"])
    assert read.message_id == r["message_id"]


def test_a_peer_pair_accepted_twice_is_dropped_the_second_time(host, box, tmp_path):
    """An intake pair that comes back (its unlink failed, or the peer resent
    it) is the same message, not a second one: dropped, and audited as such."""
    r = host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
    intake = peer_intake(box.config.inbound_handoff, HOST)
    kept = {p.name: p.read_bytes() for p in intake.iterdir() if p.is_file()}
    assert box.sweep_shared()[0]["decision"] == "delivered"
    for name, data in kept.items():
        (intake / name).write_bytes(data)
    again = box.sweep_shared()
    assert [a["decision"] for a in again] == ["duplicate-dropped"]
    assert len(_box_pairs(box, "manny")) == 1
    assert not list(intake.glob("*.amsg")), "the duplicate leaves the intake"
    recs = [json.loads(l) for l in box.config.audit_path.read_text().splitlines()]
    dropped = [x for x in recs if x.get("decision") == "duplicate-dropped"]
    assert dropped and dropped[-1]["message_id"] == r["message_id"]


def test_an_id_that_is_not_a_broker_id_is_minted_fresh(host, box):
    """The control: only a well-formed broker id is kept. Anything else is a
    sender's claim, which could shadow a real message, so it is minted anew."""
    host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
    intake = peer_intake(box.config.inbound_handoff, HOST)
    [amsg] = intake.glob("*.amsg")
    sidecar = amsg.with_suffix(".json")
    message = Message.deserialize(amsg.read_text())
    message.message_id = "chosen-by-the-peer"
    payload = message.serialize().encode("utf-8")
    amsg.write_bytes(payload)
    meta = json.loads(sidecar.read_text())
    import hashlib
    meta["raw_sha256"] = hashlib.sha256(payload).hexdigest()
    sidecar.write_text(json.dumps(meta))
    assert box.sweep_shared()[0]["decision"] == "delivered"
    [pair] = _box_pairs(box, "manny")
    kept = json.loads(pair.with_suffix(".json").read_text())["message_id"]
    assert kept != "chosen-by-the-peer" and _ID_RE.match(kept)


def test_a_kept_id_never_overwrites_quarantined_evidence(tmp_path, host):
    """Quarantine names its files by id and second. A peer that sends the same
    id twice to a recipient who doesn't list it must leave two copies."""
    box = _broker(tmp_path / "box", BOX, {"manny": []}, {HOST: host.config.inbound_handoff})
    intake = peer_intake(box.config.inbound_handoff, HOST)
    intake.mkdir(parents=True, mode=0o2770)
    host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
    kept = {p.name: p.read_bytes() for p in intake.iterdir() if p.is_file()}
    assert box.sweep_shared()[0]["decision"] == "quarantined"
    for name, data in kept.items():
        (intake / name).write_bytes(data)
    assert box.sweep_shared()[0]["decision"] == "quarantined"
    assert len(list(box.config.inbound_quarantine.rglob("*.amsg"))) == 2
    recs = [json.loads(l) for l in box.config.audit_path.read_text().splitlines()]
    assert all("peer id msg-" in (x.get("reason") or "")
               for x in recs if x.get("decision") == "quarantined")


EVIL = "evil.local"


def _repoint_pair(amsg, new_id):
    """Rewrite an intake pair's message id, keeping its sidecar hash true."""
    import hashlib
    message = Message.deserialize(amsg.read_text())
    message.message_id = new_id
    payload = message.serialize().encode("utf-8")
    amsg.write_bytes(payload)
    side = amsg.with_suffix(".json")
    meta = json.loads(side.read_text())
    meta["raw_sha256"] = hashlib.sha256(payload).hexdigest()
    side.write_text(json.dumps(meta))


def test_a_peer_cannot_claim_another_domains_id_first(tmp_path, host):
    """A second declared peer that learned the host's id (say, from a message
    copied to it) delivers its own message under that id first. The genuine
    message must still arrive: a held id is a duplicate only for the route and
    sender that first brought it. Anything else is a collision, minted fresh."""
    box = _broker(tmp_path / "box", BOX, {"manny": [f"ira@{HOST}", f"mallory@{EVIL}"]},
                  {HOST: host.config.inbound_handoff,
                   EVIL: tmp_path / "evil" / "handoff"})
    peer_intake(box.config.inbound_handoff, HOST).mkdir(parents=True, mode=0o2770)
    peer_intake(box.config.inbound_handoff, EVIL).mkdir(parents=True, mode=0o2770)
    evil = _broker(tmp_path / "evil", EVIL, {"mallory": [f"manny@{BOX}"]},
                   {BOX: box.config.inbound_handoff})
    genuine = host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}", body="genuine"))
    target = genuine["message_id"]
    host_intake = peer_intake(box.config.inbound_handoff, HOST)
    held_back = tmp_path / "held_back"
    held_back.mkdir()
    for p in list(host_intake.iterdir()):
        p.rename(held_back / p.name)
    evil.submit("mallory", _msg(f"mallory@{EVIL}", f"manny@{BOX}", body="impostor"))
    [evil_amsg] = peer_intake(box.config.inbound_handoff, EVIL).glob("*.amsg")
    _repoint_pair(evil_amsg, target)
    assert [s["decision"] for s in box.sweep_shared()] == ["delivered"]
    for p in list(held_back.iterdir()):
        p.rename(host_intake / p.name)
    assert [s["decision"] for s in box.sweep_shared()] == ["delivered"], \
        "the genuine message is delivered, not dropped as the impostor's duplicate"
    bodies = sorted(Message.deserialize(p.read_text()).body for p in _box_pairs(box, "manny"))
    assert bodies == ["genuine", "impostor"]
    recs = [json.loads(l) for l in box.config.audit_path.read_text().splitlines()]
    assert any("id-collision" in (x.get("detail") or "") for x in recs)


# ---------------------------------------------------------------- R14

def test_intake_names_unique(local, monkeypatch):
    """Same second, several recipients, several messages: every pair lands."""
    monkeypatch.setattr("macf.amail.broker.time.time", lambda: 1_800_000_000.0)
    first = local.submit("ira", _msg(f"ira@{HOST}", f"manny@{HOST}", f"rusty@{HOST}", body="one"))
    second = local.submit("ira", _msg(f"ira@{HOST}", f"manny@{HOST}", body="two"))
    assert first["ok"] and second["ok"], (first, second)
    manny = _box_pairs(local, "manny")
    assert len(manny) == 2 and len({p.name for p in manny}) == 2
    assert len(_box_pairs(local, "rusty")) == 1
    bodies = sorted(Message.deserialize(p.read_text()).body for p in manny)
    assert bodies == ["one", "two"], "neither send overwrote the other"


# ---------------------------------------------------------------- R38

def test_one_copy_per_recipient(local):
    """One file per recipient, each with one link: a fan-out by hard link would
    let one recipient's ingest change what another reads."""
    r = local.submit("ira", _msg(f"ira@{HOST}", f"manny@{HOST}", f"rusty@{HOST}"))
    assert r["ok"], r
    [m] = _box_pairs(local, "manny")
    [s] = _box_pairs(local, "rusty")
    sm, ss = os.stat(m), os.stat(s)
    assert (sm.st_dev, sm.st_ino) != (ss.st_dev, ss.st_ino)
    assert sm.st_nlink == 1 and ss.st_nlink == 1
