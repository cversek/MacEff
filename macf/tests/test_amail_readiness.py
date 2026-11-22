"""`amail status`'s setup pieces: each read from where the client and broker read it, each missing
piece with the command that supplies it."""
import os

import yaml

from macf.amail import readiness
from macf.amail.registry import Registry


def _host(tmp_path, *, peers=None):
    root = tmp_path / "amail-host"
    (root / "handoff").mkdir(parents=True)
    addressing = root / "addressing.yaml"
    addressing.write_text(yaml.safe_dump({"domain": "alpha.test", "tier": "host", "supervision": "operator-at-terminal",
                                          "agents": {"ira": {"uid": os.getuid(), "home": str(tmp_path / "ira"),
                                                             "shared_uid": True, "card": "Ira_0a1b2c",
                                                             "contacts": []}}}))
    cfg = root / "broker_config.yaml"
    raw = {"addressing_path": str(addressing), "inbound_handoff": str(root / "handoff"),
           "peer_listen": {"host": "100.64.0.7", "port": 8030}}
    if peers:
        raw["peer_links"] = peers
    cfg.write_text(yaml.safe_dump(raw))
    return cfg


def _registry(tmp_path, entries):
    reg = tmp_path / "registry.yaml"
    reg.write_text(yaml.safe_dump({"agents": entries}))
    os.chmod(reg, 0o644)
    return Registry(reg, root_uid=os.getuid())


def _by(found):
    return {p.name: p for p in found}


def test_an_agent_with_no_address_is_told_what_to_write():
    (only,) = readiness.pieces({"agent": "", "domain": ""})
    assert only.name == "address" and only.ok is False and "amail.json" in only.fix


def test_each_missing_piece_names_its_fix(tmp_path):
    cfg = {"agent": "ira", "domain": "alpha.test", "signing_key": str(tmp_path / "keys" / "none.pem"),
           "signing_required": False, "broker_config": str(_host(tmp_path))}
    found = _by(readiness.pieces(cfg, registry=_registry(tmp_path, {})))
    assert found["signing key"].ok is False and "keygen" in found["signing key"].fix
    assert found["signing declared"].ok is False and "signing_required" in found["signing declared"].fix
    assert found["broker supervision"].ok is False and found["broker supervision"].fix == "macf_tools amail broker-unit"
    assert "registry" not in found, "with no usable key there is nothing to declare yet"


def test_a_complete_setup_reads_ok_and_names_the_listener_as_a_crossing(tmp_path):
    from macf.amail.crypto import generate_keypair
    key = generate_keypair(tmp_path / "keys" / "ira.pem")
    cfg = {"agent": "ira", "domain": "alpha.test", "signing_key": str(tmp_path / "keys" / "ira.pem"),
           "signing_required": True,
           "broker_config": str(_host(tmp_path, peers={"beta.test": {"host": "100.64.0.9", "port": 8030,
                                                                     "agents": {"sparrow": "Sparrow_6a7b8c"}}}))}
    found = readiness.pieces(cfg, registry=_registry(tmp_path, {"Ira_0a1b2c": {"account": "ira", "keys": [key]}}),
                             daemon_installed=lambda card, home: True)
    assert all(p.ok is True for p in found), found
    assert "crossing" in _by(found)["listener"].detail


def test_a_key_not_in_the_registry_prints_the_declaration_to_run(tmp_path):
    from macf.amail.crypto import generate_keypair
    key = generate_keypair(tmp_path / "keys" / "ira.pem")
    cfg = {"agent": "ira", "domain": "alpha.test", "signing_key": str(tmp_path / "keys" / "ira.pem"),
           "signing_required": True, "broker_config": str(_host(tmp_path))}
    reg = _by(readiness.pieces(cfg, registry=_registry(tmp_path, {})))["registry"]
    assert reg.ok is False and f"registry declare --card Ira_0a1b2c --key {key}" in reg.fix


def test_a_peer_with_mail_waiting_or_refused_or_no_agents_points_at_the_check(tmp_path):
    cfg_path = _host(tmp_path, peers={"beta.test": {"host": "100.64.0.9", "port": 8030}})
    out = tmp_path / "amail-host" / "handoff" / "_outbox" / "beta.test"
    (out / "refused").mkdir(parents=True)
    (out / "1-a.amsg").write_text("x")
    (out / "refused" / "1-b.amsg").write_text("x")
    cfg = {"agent": "ira", "domain": "alpha.test", "broker_config": str(cfg_path)}
    peer = _by(readiness.pieces(cfg))["peer beta.test"]
    assert peer.ok is False and "1 waiting, 1 refused" in peer.detail and "no agents declared" in peer.detail
    assert peer.fix == "macf_tools amail peer check beta.test"


def _held(box, name, sender, refused=None):
    import json
    box.mkdir(parents=True, exist_ok=True)
    (box / f"{name}.amsg").write_text("x")
    side = {"message_id": f"msg-{name}", "sender": sender, "recipient": "sparrow@beta.test",
            "handed_off_at": "2026-11-21T00:00:00+00:00"}
    if refused:
        side["refused"] = {"reason": refused, "at": "2026-11-21T00:01:00+00:00"}
    (box / f"{name}.json").write_text(json.dumps(side))


def test_the_outbox_shows_this_agents_waiting_and_refused_mail_with_the_peers_reason(tmp_path):
    """Waiting mail with its age, refused mail with the reason the peer gave, and by default only the
    asking agent's own: the outbox is the broker's, and holds every agent's mail."""
    cfg = _host(tmp_path, peers={"beta.test": {"host": "100.64.0.9", "port": 8030}})
    out = tmp_path / "amail-host" / "handoff" / "_outbox" / "beta.test"
    _held(out, "1-a", "ira@alpha.test")
    _held(out, "1-b", "bez@alpha.test")
    _held(out / "refused", "1-c", "ira@alpha.test", refused="the peer's contact list refuses it")
    mine = readiness.outbox(cfg, sender="ira@alpha.test")
    assert [(h.message_id, h.state) for h in mine] == [("msg-1-a", "waiting"), ("msg-1-c", "refused")]
    assert mine[1].reason == "the peer's contact list refuses it" and mine[0].age_s > 0
    assert len(readiness.outbox(cfg)) == 3


def test_a_message_a_real_peer_refused_shows_in_the_outbox_with_its_reason(tmp_path, monkeypatch):
    """Built from a real flush against a listener that refuses: the broker sets the pair aside with
    the peer's reason, and the outbox view reads it back."""
    import socket
    import threading

    from macf.amail.broker import Broker
    from macf.amail.deploy_config import BrokerDeployConfig, load_declarative_config
    from macf.amail.models import Message
    from macf.amail.peer_link import read_request_line
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]

    def refuse():
        for _ in range(2):
            try:
                conn, _a = srv.accept()
            except OSError:
                return  # noqa: MACEFF003 - the test closes the listening socket to end this thread
            with conn:
                read_request_line(conn)
                conn.sendall(b'{"v": 1, "ok": false, "refused": true, "reason": "no such mailbox"}\n')
    t = threading.Thread(target=refuse, daemon=True)
    t.start()
    cfg = _host(tmp_path, peers={"beta.test": {"host": "127.0.0.1", "port": port}})
    raw = yaml.safe_load(cfg.read_text())
    raw["dispositions_dir"] = str(tmp_path / "disp")
    raw["audit_path"] = str(tmp_path / "audit.jsonl")
    addressing = yaml.safe_load((tmp_path / "amail-host" / "addressing.yaml").read_text())
    addressing["agents"]["ira"]["contacts"] = [{"address": "sparrow@beta.test", "direction": "both"}]
    (tmp_path / "amail-host" / "addressing.yaml").write_text(yaml.safe_dump(addressing))
    cfg.write_text(yaml.safe_dump(raw))
    broker = Broker(BrokerDeployConfig.model_validate(load_declarative_config(cfg)).to_broker_config())
    (tmp_path / "ira").mkdir(exist_ok=True)
    out = tmp_path / "amail-host" / "handoff" / "_outbox" / "beta.test"
    _held(out, "1-x", "ira@alpha.test")
    broker.flush_outbox()
    srv.close()
    (h,) = readiness.outbox(cfg, sender="ira@alpha.test")
    assert h.state == "refused" and "no such mailbox" in h.reason
