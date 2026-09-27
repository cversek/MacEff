"""A message this agent sent is known by two ids, and both must find it.

The sent copy is written BEFORE submission, so it carries the id the agent
generated; the broker then mints the id every other record uses (the
recipient's copy, the broker's ledger, the disposition); and the copy is never
rewritten. Three rules, each with its reason written beside the code, and the
copy's submission record is where the two ids meet.

What was missing was the lookup. `amail send` printed the broker's id and
`amail read` could not open the agent's own message by it (sent copies were
never searched, by either id), and a follow-up named by the copy's id was
refused by the broker, whose ledger knows the message only by the id it
minted. These tests drive the real CLI entry points with the broker object in
place of the socket.
"""
import argparse
import json

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from conftest import _addressing

DOMAIN = "agents.test"


@pytest.fixture
def sender(tmp_path, monkeypatch):
    """alpha, with peer as a contact, submitting to a real broker object."""
    from macf import cli
    from macf.amail import client
    from macf.amail.broker import Broker, BrokerConfig

    home = tmp_path / "home"
    peer_home = tmp_path / "peer"
    for h in (home, peer_home):
        (h / "Maildir").mkdir(parents=True)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_addressing({"alpha": [f"peer@{DOMAIN}"]}))
    broker = Broker(BrokerConfig(domain=DOMAIN, dispositions_dir=tmp_path / "disp",
                                 contacts_path=contacts,
                                 inbound_handoff=tmp_path / "handoff",
                                 agent_homes={"alpha": home, "peer": peer_home}))
    submitted = []

    def submit(agent, message, socket_path, timeout=10.0):
        result = broker.submit(agent, message)
        submitted.append((message, result))
        return result

    monkeypatch.setattr(cli, "_amail_config", lambda: {
        "agent": "alpha", "domain": DOMAIN, "home": str(home),
        "socket": str(tmp_path / "sock"), "signing_key": None})
    monkeypatch.setattr(client, "submit", submit)
    return {"cli": cli, "home": home, "submitted": submitted}


def _send(cli, body="first", reply_to=None):
    return cli.cmd_amail_send(argparse.Namespace(
        to=[f"peer@{DOMAIN}"], subject="s", body=body, body_file=None,
        reply_to=reply_to, json=False))


def _ids(home):
    """(the copy's own id, the broker's id) for the one message sent so far."""
    from macf.amail import store
    entry = store.read_sent_with_state(home)[0]
    return entry["message"].message_id, entry["sidecar"]["broker_message_id"]


def test_read_opens_ones_own_message_by_the_id_send_reported(sender, capsys):
    cli, home = sender["cli"], sender["home"]
    assert _send(cli, body="words I sent") == 0
    local, minted = _ids(home)
    assert minted and local != minted, "precondition: the broker minted its own id"
    capsys.readouterr()

    assert cli.cmd_amail_read(argparse.Namespace(message_id=minted, json=False)) == 0
    out = capsys.readouterr().out
    assert "words I sent" in out
    assert minted in out, "the broker's id is the one the recipient and the ledger use"


def test_read_by_the_copys_own_id_gives_the_copy_unchanged_and_its_record(sender, capsys):
    cli, home = sender["cli"], sender["home"]
    assert _send(cli) == 0
    local, minted = _ids(home)
    capsys.readouterr()

    assert cli.cmd_amail_read(argparse.Namespace(message_id=local, json=True)) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["message_id"] == local, "the copy is shown as written, never rewritten"
    assert doc["submission"]["broker_message_id"] == minted
    assert doc["submission"]["state"] == "submitted"


@pytest.mark.parametrize("named_by", ["local", "broker"])
def test_a_follow_up_to_ones_own_message_names_the_brokers_id(sender, named_by):
    cli, home = sender["cli"], sender["home"]
    assert _send(cli, body="first") == 0
    local, minted = _ids(home)
    thread = sender["submitted"][0][1]["thread_id"]

    assert _send(cli, body="and another thing",
                 reply_to=local if named_by == "local" else minted) == 0
    reply, result = sender["submitted"][-1]
    assert result["ok"], result
    assert reply.parent == minted
    assert result["thread_id"] == thread


def test_a_copy_the_broker_never_accepted_keeps_its_own_id(sender, capsys):
    """Only an id the broker actually minted is substituted. A copy composed and
    never submitted has none, so the follow-up names the copy's own id and the
    broker refuses it: nothing here invents a thread the broker never saw."""
    from macf.amail import client, store
    from macf.amail.models import Message
    cli, home = sender["cli"], sender["home"]
    draft = Message(sender=f"alpha@{DOMAIN}", to=[f"peer@{DOMAIN}"],
                    subject="s", body="never sent")
    name = store.deliver_sent(home, draft).name
    store.write_sent_sidecar(home, name, {"state": client.COMPOSED,
                                          "local_message_id": draft.message_id,
                                          "broker_message_id": None})

    assert _send(cli, body="follow-up", reply_to=draft.message_id) == 1
    reply, result = sender["submitted"][-1]
    assert reply.parent == draft.message_id
    assert result["ok"] is False and "cannot see" in " ".join(result["refused"])
