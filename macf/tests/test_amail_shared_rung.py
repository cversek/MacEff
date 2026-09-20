"""Rung 1s: two brokers that share a filesystem hand mail to each other.

The address never names the route; the DOMAIN is the locality. A broker maps
a peer's domain to a declared hand-off root reachable through this filesystem
(a bind mount, in life) and writes into the peer BROKER's intake there --
`<peer handoff>/_peers/<this domain>/` -- never into an agent's pickup box,
because the pickup box is the boundary between an agent and ITS OWN broker,
and only that broker holds the recipient's contact book and keys. The peer
broker sweeps its intake through `accept_inbound`: its contacts, its keys,
its quarantine, its audit, its hand-off. Ingest on the recipient side is
unchanged.

Every test here uses two real brokers over one tmp tree, because the property
is about two deployments agreeing, and a fixture that fakes one of them would
prove nothing about the seam.
"""
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from conftest import _addressing

from macf.amail.broker import (Broker, BrokerConfig, DeliveryError, SharedHandoff,
                               peer_intake)
from macf.amail.client import ingest
from macf.amail.models import Message

HOST, BOX = "host.local", "box.local"


def _deployment(tmp_path, name, domain, agents, peers):
    """One deployment under tmp_path/<name>: addressing, handoff root with a
    provisioned peer intake per declared peer, audit, dispositions, quarantine.

    `agents` is {agent: [contacts]}; `peers` is {peer_domain: peer_handoff_root}.
    """
    root = tmp_path / name
    root.mkdir()
    addressing = root / "addressing.yaml"
    addressing.write_text(_addressing(agents, domain=domain))
    handoff = root / "handoff"
    handoff.mkdir()
    for a in agents:
        (handoff / a).mkdir(mode=0o2770)
        (root / "home" / a).mkdir(parents=True)
    cfg = BrokerConfig(
        domain=domain,
        agent_homes={a: root / "home" / a for a in agents},
        contacts_path=addressing,
        audit_path=root / "audit.jsonl",
        dispositions_dir=root / "dispositions",
        inbound_quarantine=root / "quarantine",
        inbound_handoff=handoff,
        shared_handoffs={d: SharedHandoff(handoff=p) for d, p in peers.items()},
    )
    return Broker(cfg), root


def _pair(tmp_path, host_contacts=None, box_contacts=None):
    """Host deployment (agent ira) and container deployment (agent manny),
    each declaring the other's hand-off root. Each provisions the intake the
    OTHER will write into, as a real deployment would."""
    host_root = tmp_path / "host" / "handoff"
    box_root = tmp_path / "box" / "handoff"
    host, _ = _deployment(tmp_path, "host", HOST,
                          {"ira": host_contacts if host_contacts is not None
                                  else [f"manny@{BOX}"]},
                          {BOX: box_root})
    box, _ = _deployment(tmp_path, "box", BOX,
                         {"manny": box_contacts if box_contacts is not None
                                   else [f"ira@{HOST}"]},
                         {HOST: host_root})
    # Provisioned by the OWNER of each root, for the peer that will write there.
    peer_intake(host_root, BOX).mkdir(parents=True, mode=0o2770)
    peer_intake(box_root, HOST).mkdir(parents=True, mode=0o2770)
    return host, box


def _msg(sender, to, body="hello across the mount"):
    return Message(sender=sender, to=[to], subject="rung 1s", body=body)


class TestTheDomainIsTheLocality:
    def test_our_domain_is_local_a_declared_peer_is_shared_anything_else_is_relay(self, tmp_path):
        host, _ = _pair(tmp_path)
        assert host._rung(f"ira@{HOST}") == "local"
        assert host._rung(f"manny@{BOX}") == "shared"
        assert host._rung("someone@elsewhere.test") == "relay"

    def test_a_declared_peer_is_matched_case_insensitively(self, tmp_path):
        host, _ = _pair(tmp_path)
        route = host.config.shared_for(f"Manny@{BOX.upper()}")
        assert (route.domain, route.local) == (BOX, "manny")
        assert route.decl.handoff == tmp_path / "box" / "handoff"

    def test_our_own_domain_is_never_shared_even_if_declared(self, tmp_path):
        """Rung 1 is asked first; a misdeclaration of our own domain cannot
        divert our own agents' mail across a mount."""
        host, _ = _pair(tmp_path)
        host.config.shared_handoffs[HOST] = SharedHandoff(handoff=tmp_path / "wrong")
        assert host.config.shared_for(f"ira@{HOST}") is None
        assert host._rung(f"ira@{HOST}") == "local"


class TestHostToContainer:
    def test_a_send_lands_in_the_peer_brokers_intake_not_the_agents_box(self, tmp_path):
        host, box = _pair(tmp_path)
        r = host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
        assert r["ok"], r
        assert r["delivered"][0]["rung"] == "shared"
        assert r["delivered"][0]["state"] == "delivered"
        intake = peer_intake(box.config.inbound_handoff, HOST)
        pairs = sorted(intake.glob("*.amsg"))
        assert len(pairs) == 1
        # Not in manny's pickup box: that write is manny's broker's to make.
        assert not list((box.config.inbound_handoff / "manny").glob("*.amsg"))
        meta = json.loads(pairs[0].with_suffix(".json").read_text())
        assert meta["rung"] == "shared"
        assert meta["origin_domain"] == HOST
        assert meta["recipient"] == f"manny@{BOX}"
        assert meta["authorization"]["outcome"] == "peer-intake"
        assert "broker_trust" not in meta, "no trust verdict is claimed across a deployment"

    def test_the_audit_names_the_rung(self, tmp_path):
        host, _ = _pair(tmp_path)
        host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
        recs = [json.loads(l) for l in (host.config.audit_path).read_text().splitlines()]
        allowed = [r for r in recs if r.get("decision") == "allowed"]
        assert allowed and allowed[-1]["rung"] == "shared"

    def test_the_peer_broker_sweeps_it_into_the_agents_box_and_the_agent_ingests(self, tmp_path):
        host, box = _pair(tmp_path)
        host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}", body="the body"))
        results = box.sweep_shared()
        assert len(results) == 1
        assert results[0]["accepted"] is True and results[0]["decision"] == "delivered"
        # Intake drained, pickup box filled -- by manny's OWN broker.
        assert not list(peer_intake(box.config.inbound_handoff, HOST).glob("*.amsg"))
        boxed = sorted((box.config.inbound_handoff / "manny").glob("*.amsg"))
        assert len(boxed) == 1
        meta = json.loads(boxed[0].with_suffix(".json").read_text())
        assert meta["rung"] == "local", "the recipient's broker wrote this, as rung 1"
        assert meta["authorization"]["outcome"] == "deliver-pull"
        # The audit on the receiving side records the route.
        recs = [json.loads(l) for l in box.config.audit_path.read_text().splitlines()]
        inbound = [r for r in recs if r.get("direction") == "inbound"]
        assert inbound and inbound[-1]["decision"] == "delivered"
        assert "shared hand-off from host.local" in (inbound[-1].get("reason") or "")
        # And the agent ingests as itself, unchanged.
        got = ingest(box.config.agent_homes["manny"], box.config.inbound_handoff / "manny",
                     box.config.contacts_path, "manny")
        assert got and got[0]["ingested"] is True
        from macf.amail import store
        msgs = store.read_all(box.config.agent_homes["manny"])
        assert len(msgs) == 1 and msgs[0].body == "the body"
        assert msgs[0].sender == f"ira@{HOST}"


class TestContainerToHost:
    def test_the_reverse_direction_is_the_same_mechanism(self, tmp_path):
        """The refusal the issue measured -- 'rung 1 (local) does not apply and
        remote delivery is not configured' -- is gone for a declared peer."""
        host, box = _pair(tmp_path)
        r = box.submit("manny", _msg(f"manny@{BOX}", f"ira@{HOST}"))
        assert r["ok"], r
        assert r["delivered"][0]["rung"] == "shared"
        assert host.sweep_shared()[0]["decision"] == "delivered"
        got = ingest(host.config.agent_homes["ira"], host.config.inbound_handoff / "ira",
                     host.config.contacts_path, "ira")
        assert got[0]["ingested"] is True

    def test_an_undeclared_domain_still_gets_the_no_transport_refusal(self, tmp_path):
        host, _ = _pair(tmp_path)
        # Permit the destination so the refusal is the transport's, not the gate's.
        host.config.contacts_path.write_text(
            _addressing({"ira": [f"manny@{BOX}", "peer@third.local"]}, domain=HOST))
        r = host.submit("ira", _msg(f"ira@{HOST}", "peer@third.local"))
        assert r["ok"] is False
        assert "rung 1s" in r["failures"][0]["error"]


class TestAuthorizationIsUnchanged:
    def test_a_recipient_not_in_the_senders_contacts_is_refused_before_any_rung(self, tmp_path):
        host, box = _pair(tmp_path, host_contacts=[])
        r = host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
        assert r["ok"] is False and r["refused"]
        assert not list(peer_intake(box.config.inbound_handoff, HOST).glob("*")), \
            "a refused send must leave nothing in the peer's intake"

    def test_the_recipients_own_book_decides_acceptance_on_its_side(self, tmp_path):
        """ira may write to manny (host book) but manny's book does not list
        ira. The host broker cannot know that and hands off anyway; manny's
        broker refuses at the sweep, quarantines on ITS side, and nothing
        reaches manny's pickup box."""
        host, box = _pair(tmp_path, box_contacts=[])
        assert host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))["ok"]
        res = box.sweep_shared()
        assert res[0]["accepted"] is True and res[0]["decision"] == "quarantined"
        assert not list((box.config.inbound_handoff / "manny").glob("*.amsg"))
        assert list(Path(box.config.inbound_quarantine).rglob("*")), "refused mail is retained"

    def test_a_revocation_on_the_receiving_side_outranks_the_hand_off(self, tmp_path):
        host, box = _pair(tmp_path, box_contacts=[
            {"address": f"ira@{HOST}", "direction": "neither"}])
        assert host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))["ok"]
        res = box.sweep_shared()
        assert res[0]["decision"] == "quarantined"
        assert "REVOKED" in res[0]["reason"]


class TestTheIntakeIsVerifiedNotTrusted:
    def test_a_peer_may_only_speak_for_its_own_domain(self, tmp_path):
        host, box = _pair(tmp_path)
        # A pair in host.local's intake claiming a sender under another domain.
        host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
        intake = peer_intake(box.config.inbound_handoff, HOST)
        amsg = next(intake.glob("*.amsg"))
        m = Message.deserialize(amsg.read_text())
        m.sender = "ira@other.local"
        payload = m.serialize().encode()
        amsg.write_bytes(payload)
        import hashlib
        meta = json.loads(amsg.with_suffix(".json").read_text())
        meta["raw_sha256"] = hashlib.sha256(payload).hexdigest()
        amsg.with_suffix(".json").write_text(json.dumps(meta))
        res = box.sweep_shared()
        assert res[0]["accepted"] is False
        assert "only speak for its own domain" in res[0]["reason"]
        assert list((intake / "rejected").glob("*.amsg")), "rejected pairs are kept as evidence"
        assert not list((box.config.inbound_handoff / "manny").glob("*.amsg"))

    def test_a_tampered_payload_is_rejected_on_the_hash(self, tmp_path):
        host, box = _pair(tmp_path)
        host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
        amsg = next(peer_intake(box.config.inbound_handoff, HOST).glob("*.amsg"))
        amsg.write_bytes(amsg.read_bytes() + b"\n-- appended after hand-off")
        res = box.sweep_shared()
        assert res[0]["accepted"] is False and "hash mismatch" in res[0]["reason"]

    def test_an_intake_for_an_undeclared_domain_is_left_unread(self, tmp_path, capsys):
        host, box = _pair(tmp_path)
        stray = peer_intake(box.config.inbound_handoff, "nobody.local")
        stray.mkdir(parents=True)
        (stray / "1-msg.amsg").write_text("x")
        (stray / "1-msg.json").write_text("{}")
        assert box.sweep_shared() == []
        assert (stray / "1-msg.amsg").exists()
        assert "not declared" in capsys.readouterr().err

    def test_sweeping_with_no_peers_or_no_intake_is_a_quiet_noop(self, tmp_path):
        alone, _ = _deployment(tmp_path, "alone", "alone.local", {"a": []}, {})
        assert alone.sweep_shared() == []


class TestTheIntakeIsProvisionedAndVerified:
    def test_an_absent_intake_refuses_and_writes_nothing(self, tmp_path):
        host, box = _pair(tmp_path)
        intake = peer_intake(box.config.inbound_handoff, HOST)
        intake.rmdir()
        r = host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
        assert r["ok"] is False
        assert "no peer intake" in r["failures"][0]["error"]
        assert not intake.exists(), "the sender's broker must not create it across the mount"

    def test_a_declared_gid_that_disagrees_with_the_mount_refuses(self, tmp_path):
        host, box = _pair(tmp_path)
        actual = os.stat(peer_intake(box.config.inbound_handoff, HOST)).st_gid
        host.config.shared_handoffs[BOX] = SharedHandoff(
            handoff=box.config.inbound_handoff, gid=actual + 1)
        r = host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))
        assert r["ok"] is False
        err = r["failures"][0]["error"]
        assert f"gid {actual}" in err and f"declares gid {actual + 1}" in err
        assert not list(peer_intake(box.config.inbound_handoff, HOST).glob("*"))

    def test_a_declared_gid_that_agrees_delivers(self, tmp_path):
        host, box = _pair(tmp_path)
        actual = os.stat(peer_intake(box.config.inbound_handoff, HOST)).st_gid
        host.config.shared_handoffs[BOX] = SharedHandoff(
            handoff=box.config.inbound_handoff, gid=actual, uid=os.getuid())
        assert host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))["ok"]


class TestTheDeploymentDeclaresIt:
    def test_shared_handoffs_parse_and_reach_the_broker_config(self, tmp_path):
        import yaml
        from macf.amail.deploy_config import BrokerDeployConfig
        addressing = tmp_path / "addressing.yaml"
        addressing.write_text(_addressing({"ira": [f"manny@{BOX}"]}, domain=HOST))
        cfg = BrokerDeployConfig.model_validate({
            "addressing_path": str(addressing),
            "shared_handoffs": {BOX: {"handoff": "/srv/box/handoff", "gid": 1005,
                                      "note": "the container, mounted at /srv/box"}},
            "shared_sweep_seconds": 2,
        }).to_broker_config()
        assert cfg.shared_handoffs[BOX] == SharedHandoff(
            handoff=Path("/srv/box/handoff"), gid=1005, uid=None,
            note="the container, mounted at /srv/box")
        assert cfg.shared_sweep_seconds == 2

    def test_declaring_our_own_domain_is_refused(self, tmp_path):
        from macf.amail.deploy_config import BrokerDeployConfig, ConfigError
        addressing = tmp_path / "addressing.yaml"
        addressing.write_text(_addressing({"ira": []}, domain=HOST))
        with pytest.raises(ConfigError, match="own domain"):
            BrokerDeployConfig.model_validate({
                "addressing_path": str(addressing),
                "shared_handoffs": {HOST.upper(): {"handoff": "/x"}},
            }).to_broker_config()

    def test_an_unknown_key_in_a_declaration_is_refused(self, tmp_path):
        from pydantic import ValidationError
        from macf.amail.deploy_config import BrokerDeployConfig
        with pytest.raises(ValidationError):
            BrokerDeployConfig.model_validate({
                "addressing_path": "/x",
                "shared_handoffs": {BOX: {"handoff": "/x", "host": "10.0.0.1"}},
            })


class TestTheHostSideClient:
    def test_autostart_does_nothing_unless_declared(self, tmp_path, monkeypatch):
        """Off by default: a broker the agent's client launches is a process the
        agent controls, so it is opted into per deployment, never implied."""
        from macf.cli import _ensure_host_broker
        cfg = {"socket": str(tmp_path / "no.sock"), "autostart": False,
               "broker_config": str(tmp_path / "broker.yaml")}
        assert _ensure_host_broker(cfg) == ""
        cfg["autostart"] = True
        cfg["broker_config"] = ""
        assert _ensure_host_broker(cfg) == ""
        assert not (tmp_path / "no.sock").exists()

    def test_status_names_an_agent_launched_broker_for_what_it_is(self, tmp_path, monkeypatch, capsys):
        import argparse
        from macf import cli
        monkeypatch.setattr(cli, "_amail_config", lambda: {
            "agent": "ira", "domain": HOST, "socket": str(tmp_path / "b.sock"),
            "handoff": str(tmp_path / "h"), "home": "", "contacts": "",
            "autostart": True, "broker_config": "",   # declared but unlaunchable here
            "signing_key": ""})
        cli.cmd_amail_status(argparse.Namespace(json=True))
        out = json.loads(capsys.readouterr().out)
        assert out["broker_kind"] == "deployment", \
            "autostart without a broker_config is not an agent-launched broker"
        monkeypatch.setattr(cli, "_ensure_host_broker", lambda cfg: "")
        monkeypatch.setattr(cli, "_amail_config", lambda: {
            "agent": "ira", "domain": HOST, "socket": str(tmp_path / "b.sock"),
            "handoff": str(tmp_path / "h"), "home": "", "contacts": "",
            "autostart": True, "broker_config": str(tmp_path / "broker.yaml"),
            "signing_key": ""})
        cli.cmd_amail_status(argparse.Namespace(json=True))
        out = json.loads(capsys.readouterr().out)
        assert out["broker_kind"].startswith("agent-launched")
