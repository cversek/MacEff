"""MIS-0004's unit rows, on a real broker socket.

- R35 (broker_socket_MUST_carry_version): the socket carries a protocol version, and a superseded
  version is accepted for its declared window after each change, then refused by name.
"""
import datetime
import json
import os
import socket
import tempfile
import time
from pathlib import Path

import pytest
import yaml

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from macf.amail import Broker, BrokerConfig, serve, socket_protocol

DOMAIN = "mailhost.example"


@pytest.fixture
def sock(tmp_path):
    home = tmp_path / "home" / "alpha"
    home.mkdir(parents=True)
    contacts = tmp_path / "addressing.yaml"
    contacts.write_text(yaml.safe_dump({"domain": DOMAIN, "tier": "host", "supervision": "operator-at-terminal",
                                        "agents": {"alpha": {"contacts": [{"address": f"beta@{DOMAIN}", "direction": "both"}]}}}))
    contacts.chmod(0o644)
    with tempfile.TemporaryDirectory(prefix="amu", dir="/tmp") as sock_dir:
        cfg = BrokerConfig(domain=DOMAIN, agent_homes={"alpha": home}, contacts_path=contacts,
                           audit_path=tmp_path / "audit.jsonl", socket_path=Path(sock_dir) / "u.sock",
                           dispositions_dir=tmp_path / "dispositions",
                           inbound_handoff=tmp_path / "handoff", inbound_quarantine=tmp_path / "quarantine",
                           shared_uid_agents={os.getuid(): ("alpha",)}, tier="host",
                           supervision="operator-at-terminal")
        srv = serve(Broker(cfg))
        time.sleep(0.15)
        yield cfg.socket_path
        srv.shutdown()


def _ask(path, req):
    """One raw request, so the test chooses the version a client on another build would send."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(str(path))
    try:
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    return json.loads(buf)


def test_socket_version(sock, monkeypatch):
    """R35: each request carries `v` and each reply names the version that answered. A client from
    before the field (no `v`) is version 1. A version the broker doesn't speak is refused with the
    ones it does, and the operation isn't run. After a change, the superseded version is served
    through its declared last day, with a note, and refused the day after."""
    status = {"op": "status", "sender": "alpha"}
    current = _ask(sock, {"v": socket_protocol.VERSION, **status})
    assert current["ok"] is True and current["v"] == socket_protocol.VERSION and "deprecated" not in current
    assert _ask(sock, status)["ok"] is True, "a request with no version is read as version 1"

    unknown = _ask(sock, {"v": 99, **status})
    assert unknown["ok"] is False and unknown["v"] == socket_protocol.VERSION
    assert "deprecated" not in unknown, "a refusal's reason is its error, not a deprecation note"
    assert "does not speak version 99" in unknown["error"] and f"speaks version {socket_protocol.VERSION}" in unknown["error"]

    # A change: this build now speaks 2, and declares 1 accepted through a day.
    today = datetime.datetime.now(datetime.timezone.utc).date()
    monkeypatch.setattr(socket_protocol, "VERSION", 2)
    monkeypatch.setattr(socket_protocol, "SUPERSEDED", {1: (today + datetime.timedelta(days=1)).isoformat()})
    inside = _ask(sock, {"v": 1, **status})
    assert inside["ok"] is True and inside["v"] == 2
    assert "superseded by 2 and accepted through" in inside["deprecated"]
    assert _ask(sock, status)["ok"] is True, "an unversioned client is version 1, inside the window too"

    monkeypatch.setattr(socket_protocol, "SUPERSEDED", {1: today.isoformat()})
    last_day = _ask(sock, {"v": 1, **status})
    assert last_day["ok"] is True and "accepted through" in last_day["deprecated"], \
        "the declared last day is still inside the window"

    monkeypatch.setattr(socket_protocol, "SUPERSEDED", {1: (today - datetime.timedelta(days=1)).isoformat()})
    closed = _ask(sock, {"v": 1, **status})
    assert closed["ok"] is False and "is no longer" in closed["error"]
    unversioned = _ask(sock, status)
    assert unversioned["ok"] is False and "version 1 was accepted through" in unversioned["error"], \
        "a request with no v is version 1, so it is refused once version 1's window closes"
    assert "deprecated" not in closed, "a closed window's refusal carries no deprecation note"
    assert _ask(sock, {"v": 2, **status})["ok"] is True


def test_a_version_that_is_not_a_number_is_refused(sock):
    for bad in ("1", 1.0, True, [1]):
        reply = _ask(sock, {"v": bad, "op": "status", "sender": "alpha"})
        assert reply["ok"] is False and "not a whole number" in reply["error"], bad


def test_a_refused_version_runs_nothing(sock, tmp_path):
    """The version is checked before the operation: a submission in a version the broker doesn't
    speak gets no message id and leaves no disposition record."""
    from macf.amail.models import Message
    m = Message(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"], subject="v99", body="v99")
    reply = _ask(sock, {"v": 99, "sender": "alpha", "message": m.to_dict()})
    assert reply["ok"] is False and "does not speak version 99" in reply["error"]
    assert "message_id" not in reply
    records = tmp_path / "dispositions"
    assert not records.exists() or not any(records.iterdir()), "nothing was recorded for a refused request"


def test_the_client_sends_its_version(sock, monkeypatch):
    """The real client names its version: with the protocol at 2 and no older version accepted, a
    client that sent nothing would be read as version 1 and refused."""
    from macf.amail.client import status
    monkeypatch.setattr(socket_protocol, "VERSION", 2)
    monkeypatch.setattr(socket_protocol, "SUPERSEDED", {})
    reply = status(sock, sender="alpha")
    assert reply["ok"] is True and reply["v"] == 2
