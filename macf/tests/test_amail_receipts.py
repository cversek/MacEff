"""MIS-0004's receipt rows, asked of a real broker over its socket.

- R24 (state_MUST_be_queryable_by_id): a sender that asks the broker for a message's state by its
  id gets the latest receipt state, per recipient and for the message.
"""
import os
import tempfile
import time
from pathlib import Path

import pytest
import yaml

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from macf.amail import Broker, BrokerConfig, serve
from macf.amail.client import message_state, submit
from macf.amail.models import Message

DOMAIN = "mailhost.example"


@pytest.fixture
def deployment(tmp_path):
    agents = ("alpha", "beta")
    homes = {a: tmp_path / "home" / a for a in agents}
    for h in homes.values():
        h.mkdir(parents=True)
    handoff = tmp_path / "handoff"
    for a in agents:
        (handoff / a).mkdir(parents=True, mode=0o2770)
    contacts = tmp_path / "addressing.yaml"
    contacts.write_text(yaml.safe_dump({"domain": DOMAIN, "tier": "host", "supervision": "operator-at-terminal",
                                        "agents": {"alpha": {"contacts": [{"address": f"beta@{DOMAIN}", "direction": "both"}]},
                                                   "beta": {"contacts": [{"address": f"alpha@{DOMAIN}", "direction": "both"}]}}}))
    contacts.chmod(0o644)
    with tempfile.TemporaryDirectory(prefix="amr", dir="/tmp") as sock_dir:
        cfg = BrokerConfig(domain=DOMAIN, agent_homes=homes, contacts_path=contacts,
                           audit_path=tmp_path / "audit.jsonl", socket_path=Path(sock_dir) / "r.sock",
                           dispositions_dir=tmp_path / "dispositions",
                           inbound_handoff=handoff, inbound_quarantine=tmp_path / "quarantine",
                           shared_uid_agents={os.getuid(): agents}, tier="host",
                           supervision="operator-at-terminal")
        broker = Broker(cfg)
        srv = serve(broker)
        time.sleep(0.15)
        yield broker
        srv.shutdown()


def test_state_by_id(deployment):
    """R24: the broker answers a sender's query by id with the latest receipt state. A later
    state replaces the earlier one in the answer, another agent's message reads as unknown, and an
    id the broker never mints is refused."""
    sock = deployment.config.socket_path
    sent = submit("alpha", Message(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"],
                                   subject="r24", body="where did it stop?"), sock)
    assert sent["ok"], sent
    mid = sent["message_id"]

    first = message_state(mid, sock, sender="alpha")
    assert first["ok"] and first["found"] and first["message_id"] == mid
    [(addr, entry)] = first["recipients"].items()
    assert addr == f"beta@{DOMAIN}"
    assert entry["state"] == first["state"] and entry["at"]

    deployment.record_disposition("alpha", mid, "bounced", "mailbox full", recipients=[addr])
    later = message_state(mid, sock, sender="alpha")
    assert later["recipients"][addr]["state"] == "bounced" and later["recipients"][addr]["detail"] == "mailbox full"
    assert later["state"] == "bounced", "the latest state is the answer, not the first"

    assert message_state(mid, sock, sender="beta") == {
        "ok": True, "message_id": mid, "found": False, "state": None, "recipients": {}, "v": 1}, \
        "another agent's message answers as an unknown id does"
    refused = message_state("../../etc/passwd", sock, sender="alpha")
    assert refused["ok"] is False and "not a message id" in refused["error"]


def test_amail_state_prints_each_recipients_latest_state(deployment, monkeypatch, capsys):
    """The agent's way to ask R24's question: `amail state <id>` prints the message's state and
    each recipient's, and says plainly when the broker holds no record for this agent."""
    import argparse
    from macf import cli

    sock = deployment.config.socket_path
    mid = submit("alpha", Message(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"],
                                  subject="cli", body="cli"), sock)["message_id"]
    deployment.record_disposition("alpha", mid, "bounced", "mailbox full", recipients=[f"beta@{DOMAIN}"])
    monkeypatch.setattr(cli, "_ensure_host_broker", lambda cfg: None)

    def run(agent, message_id):
        monkeypatch.setattr(cli, "_amail_config", lambda: {"socket": str(sock), "agent": agent})
        code = cli.cmd_amail_state(argparse.Namespace(message_id=message_id, json=False))
        return code, capsys.readouterr().out

    code, out = run("alpha", mid)
    assert code == 0
    assert out.splitlines()[0] == f"{mid}: bounced"
    assert f"beta@{DOMAIN}  bounced" in out and "mailbox full" in out
    code, out = run("beta", mid)
    assert code == 1 and "no record of" in out
