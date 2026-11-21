"""Rung 2: two brokers on a private network hand mail to each other over a socket.

The sender's broker connects to the receiver's listener and sends the message; the
receiver, not the sender, writes it into the receiver's own peer intake and answers
only then, and its contact list decides what reaches an agent (MIS-0004 R56 to R64).
Each test uses two real brokers on loopback, because the property is two deployments
agreeing across a seam, and a fixture that faked one end would prove nothing about it.
"""
import json
import socket
import time
from pathlib import Path

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from conftest import _addressing

from macf.amail import peer_link
from macf.amail.broker import Broker, BrokerConfig, PeerLink, peer_intake
from macf.amail.models import Message
from macf.amail.peer_link import PeerListener, RequestTooLarge, read_request_line

A_DOM, B_DOM = "alpha.example", "beta.example"
LOOP = "127.0.0.1"


def _deployment(tmp_path, name, domain, agents, peers):
    """One deployment under tmp_path/<name>. *peers* is {peer_domain: PeerLink}."""
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
        peer_links=dict(peers),
    )
    return Broker(cfg)


@pytest.fixture
def pair(tmp_path):
    """Alpha (agent ira) and beta (agent sparrow), each declaring the other as a peer link.
    Beta's listener is running; alpha's link points at it, and beta's declares alpha's host."""
    beta = _deployment(tmp_path, "beta", B_DOM, {"sparrow": [f"ira@{A_DOM}"]}, {A_DOM: PeerLink(host=LOOP, port=1)})
    listener = PeerListener(beta, host=LOOP, port=0).start()
    alpha = _deployment(tmp_path, "alpha", A_DOM, {"ira": [f"sparrow@{B_DOM}"]},
                        {B_DOM: PeerLink(host=LOOP, port=listener.port)})
    yield alpha, beta, listener
    listener.stop()


def _msg(sender, to, body="hello across the tailnet"):
    return Message(sender=sender, to=[to], subject="rung 2", body=body)


def _sparrow_box(beta):
    return sorted((beta.config.inbound_handoff / "sparrow").glob("*.amsg"))


def test_the_receiver_takes_custody_at_its_own_listener(pair):
    """R56: the sender writes nothing in the receiver's tree; the receiver's own listener
    puts the pair in its own peer intake, and its sweep delivers through the usual path."""
    alpha, beta, _ = pair
    result = alpha.submit("ira", _msg(f"ira@{A_DOM}", f"sparrow@{B_DOM}"))
    assert result["ok"], result
    assert (result["delivered"][0]["rung"], result["delivered"][0]["state"]) == ("peer", "delivered")
    assert not _sparrow_box(beta), "nothing reaches the agent's box before the receiver's own judgement"
    swept = beta.sweep_shared()
    assert [r["accepted"] for r in swept] == [True]
    assert len(_sparrow_box(beta)) == 1


def test_only_a_declared_link_is_used(pair):
    """R57: a domain with no declared link is not a peer, and a listener with no declared peer
    accepts none."""
    alpha, beta, listener = pair
    assert alpha._rung(f"x@{B_DOM}") == "peer"
    assert alpha._rung("someone@undeclared.example") == "relay"
    lonely = PeerListener(_bare(beta), host=LOOP, port=0)
    with pytest.raises(ValueError, match="declares no peer"):
        lonely.start()


def _bare(broker):
    broker.config.peer_links = {}
    return broker


def test_the_listener_binds_only_the_declared_address(pair):
    """R58: never every interface, and the bound address is the declared one."""
    _, beta, listener = pair
    assert listener.address == (LOOP, listener.port)
    for every in ("0.0.0.0", "::", ""):
        with pytest.raises(ValueError, match="every interface"):
            PeerListener(beta, host=every, port=0)


def test_a_stranger_is_closed_unread(pair, monkeypatch):
    """R59: a connection from an address no declared peer holds gets a closed socket, and the
    request is never read."""
    _, beta, listener = pair
    beta.config.peer_links = {A_DOM: PeerLink(host="10.9.9.9", port=1)}     # loopback is now a stranger
    read = []
    monkeypatch.setattr(peer_link, "read_request_line", lambda *a, **k: read.append(1) or b"")
    with socket.create_connection((LOOP, listener.port), timeout=5) as s:
        try:
            s.sendall(b'{"v": 1, "op": "hand_off"}\n')
        except OSError:
            pass
        s.settimeout(5)
        try:
            got = s.recv(4096)
        except ConnectionResetError:     # a socket closed with unread input is reset, not ended
            got = b""
        assert got == b""
    assert read == []


def test_no_acknowledgement_before_the_write_is_durable(pair, monkeypatch):
    """R60: the reply follows the write. A write that fails is answered as a failure, and the
    sender keeps its copy."""
    alpha, beta, _ = pair
    monkeypatch.setattr(beta, "_write_pair", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    result = alpha.submit("ira", _msg(f"ira@{A_DOM}", f"sparrow@{B_DOM}"))
    assert result["delivered"][0]["state"] == "deferred", result
    assert not list(peer_intake(beta.config.inbound_handoff, A_DOM).glob("*.amsg"))
    assert len(list((alpha.config.inbound_handoff / "_outbox" / B_DOM).glob("*.amsg"))) == 1


def test_an_unacknowledged_send_is_kept_and_retried(tmp_path):
    """R61: with the peer down the copy stays in the outbox; when it is up, the retry delivers
    it, and a repeat of an id the receiver holds is dropped, not delivered twice."""
    beta = _deployment(tmp_path, "beta", B_DOM, {"sparrow": [f"ira@{A_DOM}"]}, {A_DOM: PeerLink(host=LOOP, port=1)})
    down = socket.socket()
    down.bind((LOOP, 0))
    dead_port = down.getsockname()[1]
    down.close()
    alpha = _deployment(tmp_path, "alpha", A_DOM, {"ira": [f"sparrow@{B_DOM}"]},
                        {B_DOM: PeerLink(host=LOOP, port=dead_port)})
    result = alpha.submit("ira", _msg(f"ira@{A_DOM}", f"sparrow@{B_DOM}"))
    assert result["delivered"][0]["state"] == "deferred"
    outbox = alpha.config.inbound_handoff / "_outbox" / B_DOM
    assert len(list(outbox.glob("*.amsg"))) == 1
    listener = PeerListener(beta, host=LOOP, port=0).start()
    try:
        alpha.config.peer_links[B_DOM] = PeerLink(host=LOOP, port=listener.port)
        kept = {p.name: (p.read_bytes(), p.with_suffix(".json").read_bytes()) for p in outbox.glob("*")}
        assert [r["state"] for r in alpha.flush_outbox()] == ["delivered"]
        assert not list(outbox.glob("*.amsg"))
        beta.sweep_shared()
        assert len(_sparrow_box(beta)) == 1
        for name, (payload, sidecar) in kept.items():          # the ack was lost: the same pair comes again
            (outbox / name).write_bytes(payload if name.endswith(".amsg") else sidecar)
        alpha.flush_outbox()
        beta.sweep_shared()
        assert len(_sparrow_box(beta)) == 1, "a repeat of a held id is dropped"
    finally:
        listener.stop()


def test_a_request_is_read_only_up_to_its_bound(pair, monkeypatch):
    """R62: an endless line is cut off at the bound and refused by name, whatever the sender does."""
    _, _, listener = pair
    monkeypatch.setattr(peer_link, "MAX_REQUEST_BYTES", 10_000)
    sent = 0
    with socket.create_connection((LOOP, listener.port), timeout=5) as s:
        s.settimeout(5)
        try:
            while sent < 32_000_000:
                s.sendall(b"A" * 4096)
                sent += 4096
        except OSError:
            pass
        reply = b""
        try:
            reply = s.recv(4096)
        except OSError:
            pass
    assert sent < 32_000_000, "the listener stopped reading at its bound"
    assert not reply or b"10000" in reply or b"too large" in reply.lower()


def test_a_long_request_line_is_read_in_linear_time():
    class Stream:
        def __init__(self, total):
            self.left = total

        def recv(self, n):
            if self.left <= 0:
                return b"\n"
            self.left -= n
            return b"A" * n

    start = time.monotonic()
    assert len(read_request_line(Stream(40 * 1024 * 1024), limit=64 * 1024 * 1024)) > 40 * 1024 * 1024
    assert time.monotonic() - start < 5
    with pytest.raises(RequestTooLarge):
        read_request_line(Stream(2_000_000), limit=1_000_000)


def test_peer_mail_must_be_signed(pair):
    """R63: peer mail is judged as a local sender's is: from a listed correspondent with no signature
    it is delivered as unverified, never as attested."""
    alpha, beta, _ = pair
    alpha.submit("ira", _msg(f"ira@{A_DOM}", f"sparrow@{B_DOM}"))
    beta.sweep_shared()
    (amsg,) = _sparrow_box(beta)
    meta = json.loads(amsg.with_suffix(".json").read_text())
    assert meta.get("broker_trust") != "attested" and meta.get("rung") == "local"


def test_peer_mail_follows_the_contact_list(tmp_path):
    """R64: a sender the recipient does not list is quarantined, not delivered."""
    beta = _deployment(tmp_path, "beta", B_DOM, {"sparrow": [f"someone-else@{A_DOM}"]},
                       {A_DOM: PeerLink(host=LOOP, port=1)})
    listener = PeerListener(beta, host=LOOP, port=0).start()
    try:
        alpha = _deployment(tmp_path, "alpha", A_DOM, {"ira": [f"sparrow@{B_DOM}"]},
                            {B_DOM: PeerLink(host=LOOP, port=listener.port)})
        alpha.submit("ira", _msg(f"ira@{A_DOM}", f"sparrow@{B_DOM}"))
        beta.sweep_shared()
        assert not _sparrow_box(beta)
        assert list(Path(beta.config.inbound_quarantine).rglob("*")), "the refusal is kept as evidence"
    finally:
        listener.stop()


def test_the_operators_declaration_refuses_a_name_an_every_interface_bind_and_a_double_claim(tmp_path):
    """The declaration is where R57 and R58 are made true before a socket exists: a peer is an
    address, the listener is one address, and a domain is reached by one rung."""
    from pydantic import ValidationError

    from macf.amail.deploy_config import PeerLinkDecl, PeerListenDecl
    with pytest.raises(ValidationError, match="not an IP address"):
        PeerLinkDecl(host="peer.example", port=8025)
    with pytest.raises(ValidationError, match="every interface"):
        PeerListenDecl(host="0.0.0.0", port=8025)
    with pytest.raises(ValidationError):
        PeerLinkDecl(host="100.64.0.7", port=70000)
    assert PeerLinkDecl(host="100.64.0.7", port=8025).host == "100.64.0.7"


def test_a_peer_link_to_our_own_domain_or_one_already_shared_is_refused(tmp_path):
    from macf.amail.deploy_config import BrokerDeployConfig, ConfigError
    addressing = tmp_path / "addressing.yaml"
    addressing.write_text(_addressing({"ira": []}, domain=A_DOM))
    base = {"addressing_path": str(addressing), "peer_links": {A_DOM: {"host": "100.64.0.7", "port": 8025}}}
    with pytest.raises(ConfigError, match="own domain"):
        BrokerDeployConfig.model_validate(base).to_broker_config()
    both = {"addressing_path": str(addressing),
            "shared_handoffs": {B_DOM: {"handoff": str(tmp_path)}},
            "peer_links": {B_DOM: {"host": "100.64.0.7", "port": 8025}}}
    with pytest.raises(ConfigError, match="both shared_handoffs and peer_links"):
        BrokerDeployConfig.model_validate(both).to_broker_config()


def test_a_slow_sender_is_cut_off_at_its_deadline(pair, monkeypatch):
    """R65: a peer that dribbles one byte at a time never ends its request, and holds a slot until
    the deadline cuts it off; the operator's ruling was an idle timeout, which a total deadline includes."""
    _, _, listener = pair
    monkeypatch.setattr(peer_link, "REQUEST_DEADLINE_S", 1.0)
    started = time.monotonic()
    cut_off = None
    with socket.create_connection((LOOP, listener.port), timeout=10) as s:
        s.settimeout(0.2)
        while time.monotonic() - started < 8:
            try:
                s.sendall(b"A")
            except OSError:
                cut_off = time.monotonic() - started
                break
            try:
                if s.recv(4096) == b"":
                    cut_off = time.monotonic() - started
                    break
            except socket.timeout:
                pass
            except OSError:
                cut_off = time.monotonic() - started
                break
            time.sleep(0.3)
    assert cut_off is not None and cut_off < 5, "the listener ended a connection that never finished its request"


def test_two_brokers_exchange_a_message_both_ways(tmp_path):
    beta = _deployment(tmp_path, "beta", B_DOM, {"sparrow": [f"ira@{A_DOM}"]}, {A_DOM: PeerLink(host=LOOP, port=1)})
    alpha = _deployment(tmp_path, "alpha", A_DOM, {"ira": [f"sparrow@{B_DOM}"]}, {B_DOM: PeerLink(host=LOOP, port=1)})
    on_beta, on_alpha = PeerListener(beta, host=LOOP, port=0).start(), PeerListener(alpha, host=LOOP, port=0).start()
    try:
        alpha.config.peer_links[B_DOM] = PeerLink(host=LOOP, port=on_beta.port)
        beta.config.peer_links[A_DOM] = PeerLink(host=LOOP, port=on_alpha.port)
        assert alpha.submit("ira", _msg(f"ira@{A_DOM}", f"sparrow@{B_DOM}"))["ok"]
        assert beta.submit("sparrow", _msg(f"sparrow@{B_DOM}", f"ira@{A_DOM}"))["ok"]
        beta.sweep_shared()
        alpha.sweep_shared()
        assert len(_sparrow_box(beta)) == 1
        assert len(sorted((alpha.config.inbound_handoff / "ira").glob("*.amsg"))) == 1
    finally:
        on_beta.stop()
        on_alpha.stop()


def test_a_half_written_pair_is_finished_not_stuck(pair):
    """THM's review of #1095: a take interrupted between the sidecar and the message left a sidecar
    alone in the intake, and every retry then failed for good. A sidecar with the same hash and no
    message is finished, and acknowledged."""
    alpha, beta, _ = pair
    msg = _msg(f"ira@{A_DOM}", f"sparrow@{B_DOM}")
    seen = []
    real = beta.take_over_link

    def spy(domain, stem, sidecar, payload):
        if not seen:                               # plant the half pair before the first take
            seen.append(stem)
            intake = peer_intake(beta.config.inbound_handoff, domain)
            intake.mkdir(parents=True, mode=0o700, exist_ok=True)
            (intake / f"{stem}.json").write_text(json.dumps(sidecar))
        return real(domain, stem, sidecar, payload)

    beta.take_over_link = spy
    result = alpha.submit("ira", msg)
    assert result["delivered"][0]["state"] == "delivered", result
    beta.sweep_shared()
    assert len(_sparrow_box(beta)) == 1


def test_a_stale_sidecar_with_other_bytes_is_replaced(pair):
    alpha, beta, _ = pair
    real = beta.take_over_link
    planted = []

    def spy(domain, stem, sidecar, payload):
        if not planted:
            planted.append(1)
            intake = peer_intake(beta.config.inbound_handoff, domain)
            intake.mkdir(parents=True, mode=0o700, exist_ok=True)
            (intake / f"{stem}.json").write_text(json.dumps({**sidecar, "raw_sha256": "0" * 64}))
        return real(domain, stem, sidecar, payload)

    beta.take_over_link = spy
    assert alpha.submit("ira", _msg(f"ira@{A_DOM}", f"sparrow@{B_DOM}"))["delivered"][0]["state"] == "delivered"


def test_a_public_address_is_refused_for_a_peer_or_a_listener():
    from pydantic import ValidationError

    from macf.amail.deploy_config import PeerLinkDecl, PeerListenDecl
    for bad in ("8.8.8.8", "93.184.216.34"):
        with pytest.raises(ValidationError, match="private"):
            PeerLinkDecl(host=bad, port=8030)
        with pytest.raises(ValidationError, match="private"):
            PeerListenDecl(host=bad, port=8030)
    for good in ("100.105.225.84", "10.0.0.5", "192.168.1.9", "127.0.0.1"):
        assert PeerLinkDecl(host=good, port=8030).host == good
        assert PeerListenDecl(host=good, port=8030).host == good


def test_the_deadline_check_itself_ends_a_dribbling_read(monkeypatch):
    """The slow-sender test passes through the socket's own timeout as well; this one drives the
    deadline check alone, with a clock that moves half a second per read."""
    ticks = iter(range(1000))
    monkeypatch.setattr(peer_link.time, "monotonic", lambda: next(ticks) * 0.5)

    class Dribble:
        def recv(self, n):
            return b"A"

    with pytest.raises(peer_link.RequestTimedOut):
        read_request_line(Dribble(), limit=10_000, deadline_s=1.0)
