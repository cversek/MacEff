"""The broker never opens an agent's home; it answers threading from its own ledger.

Two checks used to read a Maildir: a reply's parent must be a message the
sender can see (canonicalize, the sender's home), and an inbound message's
asserted parent or thread must be one the recipient has (accept_inbound, the
recipient's home). Under the identity model the broker cannot enter either,
and on the first deployment where that model held every --reply-to failed
with PermissionError on the sender's home and every peer-intake delivery
failed with PermissionError on the recipient's. Both facts are things the
broker itself did -- it delivered the parent, it accepted the thread -- so
they are written where the broker can read them: ledger/<agent>/<id>.json.

The tests below make the homes UNREADABLE (mode 000) before the check runs.
A test that merely does not read a home proves nothing about a broker that
would; a home the process cannot open proves the read is gone.
"""
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from conftest import _addressing

from macf.amail.broker import Broker, BrokerConfig, SharedHandoff, peer_intake
from macf.amail.client import ingest
from macf.amail.models import Message

DOMAIN = "agents.test"


@pytest.fixture
def two(tmp_path):
    """alpha and beta, each permitting the other; homes provisioned."""
    homes = {a: tmp_path / a for a in ("alpha", "beta")}
    for h in homes.values():
        (h / "Maildir").mkdir(parents=True)
    contacts = tmp_path / "addressing.yaml"
    contacts.write_text(_addressing({"alpha": [f"beta@{DOMAIN}"],
                                     "beta": [f"alpha@{DOMAIN}"]}, domain=DOMAIN))
    cfg = BrokerConfig(domain=DOMAIN, agent_homes=homes, contacts_path=contacts,
                       audit_path=tmp_path / "audit.jsonl",
                       dispositions_dir=tmp_path / "disp",
                       inbound_handoff=tmp_path / "handoff",
                       inbound_quarantine=tmp_path / "q")
    b = Broker(cfg)

    def pull(agent):
        ingest(homes[agent], tmp_path / "handoff" / agent, contacts, agent)
        from macf.amail import store
        return store.read_all(homes[agent])

    def seal():
        for h in homes.values():
            os.chmod(h, 0)

    def unseal():
        for h in homes.values():
            os.chmod(h, 0o700)

    yield {"b": b, "cfg": cfg, "homes": homes, "pull": pull, "seal": seal,
           "unseal": unseal, "tmp": tmp_path}
    unseal()


def _msg(sender, to, **kw):
    return Message(sender=sender, to=[to], subject=kw.pop("subject", "s"),
                   body=kw.pop("body", "b"), **kw)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can open a mode-000 home")
class TestReplyToNeverOpensTheSendersHome:
    def test_a_reply_to_a_received_message_works_with_the_home_sealed(self, two):
        b = two["b"]
        assert b.submit("alpha", _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}"))["ok"]
        first = two["pull"]("beta")[0]
        two["seal"]()
        reply = _msg(f"beta@{DOMAIN}", f"alpha@{DOMAIN}", parent=first.message_id,
                     thread_id=first.thread_id)
        r = b.submit("beta", reply)
        assert r["ok"], r
        assert r["thread_id"] == first.thread_id

    def test_a_reply_to_ones_own_message_works_too(self, two):
        b = two["b"]
        first = b.submit("alpha", _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}"))
        two["seal"]()
        follow = _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}", parent=first["message_id"],
                      thread_id=first["thread_id"])
        assert b.submit("alpha", follow)["ok"]

    def test_a_reply_to_a_message_the_sender_never_had_is_still_refused(self, two):
        from macf.amail.models import new_id
        b = two["b"]
        two["seal"]()
        r = b.submit("beta", _msg(f"beta@{DOMAIN}", f"alpha@{DOMAIN}", parent=new_id("msg")))
        assert r["ok"] is False and "cannot see" in " ".join(r["refused"])

    def test_the_sealed_home_would_have_failed_the_old_read(self, two):
        """Control on the instrument: sealing really does deny the process."""
        two["seal"]()
        with pytest.raises(PermissionError):
            list((two["homes"]["beta"] / "Maildir").iterdir())


@pytest.mark.skipif(os.geteuid() == 0, reason="root can open a mode-000 home")
class TestInboundThreadChecksNeverOpenTheRecipientsHome:
    def test_a_visible_parent_is_kept_and_an_unseen_one_dropped_with_the_home_sealed(self, two):
        from macf.amail.models import new_id
        b = two["b"]
        b.submit("alpha", _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}"))
        seen = two["pull"]("beta")[0]
        two["seal"]()
        good = _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}", parent=seen.message_id,
                    thread_id=seen.thread_id, body="good")
        assert b.accept_inbound(good, f"beta@{DOMAIN}")["decision"] == "delivered"
        bad = _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}", parent=new_id("msg"), body="bad")
        assert b.accept_inbound(bad, f"beta@{DOMAIN}")["decision"] == "delivered"
        two["unseal"]()
        got = {m.body: m for m in two["pull"]("beta")}
        # The asserted-but-unseen parent was dropped; the real one kept.
        assert got["good"].parent == seen.message_id
        assert got["bad"].parent is None

    def test_an_asserted_thread_the_recipient_is_in_is_not_joined(self, two):
        b = two["b"]
        b.submit("alpha", _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}"))
        existing = two["pull"]("beta")[0].thread_id
        two["seal"]()
        m = _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}", body="graft")
        m.thread_id, m.parent = existing, None
        b.accept_inbound(m, f"beta@{DOMAIN}")
        two["unseal"]()
        grafted = [x for x in two["pull"]("beta") if x.body == "graft"]
        assert grafted and grafted[0].thread_id != existing


class TestTheLedgerItself:
    def test_every_hand_off_and_every_accepted_submission_is_recorded(self, two):
        b, tmp = two["b"], two["tmp"]
        r = b.submit("alpha", _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}"))
        sent = json.loads((tmp / "ledger" / "alpha" / f"{r['message_id']}.json").read_text())
        recv = json.loads((tmp / "ledger" / "beta" / f"{r['message_id']}.json").read_text())
        assert sent["direction"] == "sent" and recv["direction"] == "received"
        assert sent["thread_id"] == recv["thread_id"] == r["thread_id"]
        assert b.seen("beta", r["message_id"]) and b.seen("alpha", r["message_id"])
        assert b.seen("beta", "msg-0-000000000000") is None
        assert b.thread_seen("beta", r["thread_id"]) and not b.thread_seen("beta", "thr-0-0")

    def test_the_ledger_is_broker_owned_and_agent_readable(self, two):
        import stat
        b, tmp = two["b"], two["tmp"]
        r = b.submit("alpha", _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}"))
        f = tmp / "ledger" / "beta" / f"{r['message_id']}.json"
        assert stat.S_IMODE(f.stat().st_mode) == 0o644
        assert stat.S_IMODE(f.parent.stat().st_mode) == 0o755

    def test_a_first_record_is_never_rewritten(self, two):
        b = two["b"]
        m = _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}")
        f = b.record_seen("alpha", m, "sent", via="first")
        b.record_seen("alpha", m, "received", via="second")
        assert json.loads(f.read_text())["via"] == "first"

    def test_no_ledger_refuses_a_reply_rather_than_guessing(self, tmp_path, capsys):
        contacts = tmp_path / "a.yaml"
        contacts.write_text(_addressing({"alpha": [f"beta@{DOMAIN}"], "beta": [f"alpha@{DOMAIN}"]},
                                        domain=DOMAIN))
        cfg = BrokerConfig(domain=DOMAIN, contacts_path=contacts,
                           agent_homes={"alpha": tmp_path / "a", "beta": tmp_path / "b"})
        b = Broker(cfg)
        assert b._ledger_root() is None
        from macf.amail.models import new_id
        r = b.submit("alpha", _msg(f"alpha@{DOMAIN}", f"beta@{DOMAIN}", parent=new_id("msg")))
        assert r["ok"] is False and "cannot see" in " ".join(r["refused"])

    def test_the_deploy_config_carries_it(self, tmp_path):
        from macf.amail.deploy_config import BrokerDeployConfig
        addressing = tmp_path / "addressing.yaml"
        addressing.write_text(_addressing({"alpha": []}, domain=DOMAIN))
        cfg = BrokerDeployConfig.model_validate({"addressing_path": str(addressing)}).to_broker_config()
        assert cfg.ledger_dir == Path("/var/lib/amail_broker/ledger")
        cfg2 = BrokerDeployConfig.model_validate({"addressing_path": str(addressing),
                                                  "ledger_dir": "/srv/x"}).to_broker_config()
        assert cfg2.ledger_dir == Path("/srv/x")


@pytest.mark.skipif(os.geteuid() == 0, reason="root can open a mode-000 home")
class TestTheReverseDirectionOfRungOneS:
    def test_a_peer_intake_delivery_completes_with_the_recipients_home_sealed(self, tmp_path):
        """The failure measured on the second deployment: the receiving broker
        raised PermissionError on the recipient's Maildir for every swept pair,
        because every Message carries a thread_id and the thread check read the
        home. With the ledger it completes."""
        HOST, BOX = "host.local", "box.local"
        def deployment(name, domain, agents, peers):
            root = tmp_path / name; root.mkdir()
            addressing = root / "addressing.yaml"
            addressing.write_text(_addressing(agents, domain=domain))
            handoff = root / "handoff"; handoff.mkdir()
            for a in agents:
                (handoff / a).mkdir(mode=0o2770); (root / "home" / a / "Maildir").mkdir(parents=True)
            cfg = BrokerConfig(domain=domain, agent_homes={a: root / "home" / a for a in agents},
                               contacts_path=addressing, audit_path=root / "audit.jsonl",
                               dispositions_dir=root / "disp", inbound_quarantine=root / "q",
                               inbound_handoff=handoff,
                               shared_handoffs={d: SharedHandoff(handoff=p) for d, p in peers.items()})
            return Broker(cfg), root
        host, hroot = deployment("host", HOST, {"ira": [f"manny@{BOX}"]}, {BOX: tmp_path / "box" / "handoff"})
        box, broot = deployment("box", BOX, {"manny": [f"ira@{HOST}"]}, {HOST: tmp_path / "host" / "handoff"})
        peer_intake(hroot / "handoff", BOX).mkdir(parents=True, mode=0o2770)
        peer_intake(broot / "handoff", HOST).mkdir(parents=True, mode=0o2770)
        assert host.submit("ira", _msg(f"ira@{HOST}", f"manny@{BOX}"))["ok"]
        manny_home = broot / "home" / "manny"
        os.chmod(manny_home, 0)
        try:
            res = box.sweep_shared()
        finally:
            os.chmod(manny_home, 0o700)
        assert res and res[0]["accepted"] is True and res[0]["decision"] == "delivered", res
        assert list((broot / "handoff" / "manny").glob("*.amsg"))
