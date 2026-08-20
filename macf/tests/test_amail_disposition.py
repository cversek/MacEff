

# --------------------------------------------- a bounce must carry its reason
#
# Measured on a real send: a 422 DEST_NOT_VERIFIED was recorded as `bounced`
# with an EMPTY detail, and the reason had to be recovered by sending the
# message a second time. A ledger that records the fate and discards the
# evidence has failed at the one job it has.

def test_a_transport_reason_reaches_the_ledger(tmp_path, monkeypatch):
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.models import Message
    from macf.amail import transport as T
    import json as _json

    class Rejecting:
        name = "rejecting"
        def send(self, message, credential, recipient=None):
            return T.TransportResult(
                T.BOUNCED,
                'rejected (422): {"status":"rejected","reason":"DEST_NOT_VERIFIED"}')

    cred = tmp_path / "cred"
    cred.write_text("CF_ACCESS_CLIENT_ID=x.access\nCF_ACCESS_CLIENT_SECRET=y\n")
    cred.chmod(0o600)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_json.dumps({"alpha": ["far@example.org"]}))
    (tmp_path / "alpha" / "Maildir").mkdir(parents=True)
    b = Broker(BrokerConfig(
        domain="agents.test", contacts_path=contacts, credentials_path=cred,
        dispositions_dir=tmp_path / "disp", inbound_handoff=tmp_path / "handoff",
        agent_homes={"alpha": tmp_path / "alpha"}, transport=Rejecting()))

    b.submit("alpha", Message(sender="alpha@agents.test", to=["far@example.org"],
                              subject="s", body="b"))

    recs = list((tmp_path / "disp").glob("*.json"))
    assert len(recs) == 1
    hist = _json.loads(recs[0].read_text())["recipients"]["far@example.org"]["history"]
    assert hist[-1]["state"] == "bounced"
    assert "DEST_NOT_VERIFIED" in hist[-1]["detail"], (
        "the ledger recorded a bounce with no reason; a bare `bounced` is a "
        "fact nobody can act on")


def test_the_trust_slot_is_not_used_for_a_transport_reason(tmp_path):
    """The detail used to ride in the classification slot, so one field meant a
    signature verdict on one rung and a rejection reason on another, and no
    reader of the audit log could tell which it was holding."""
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.models import Message
    from macf.amail import transport as T
    import json as _json

    class Accepting:
        name = "accepting"
        def send(self, message, credential, recipient=None):
            return T.TransportResult(T.ACCEPTED, "accepted for sending (202)")

    cred = tmp_path / "cred"
    cred.write_text("CF_ACCESS_CLIENT_ID=x.access\nCF_ACCESS_CLIENT_SECRET=y\n")
    cred.chmod(0o600)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_json.dumps({"alpha": ["far@example.org"]}))
    (tmp_path / "alpha" / "Maildir").mkdir(parents=True)
    b = Broker(BrokerConfig(
        domain="agents.test", contacts_path=contacts, credentials_path=cred,
        dispositions_dir=tmp_path / "disp", inbound_handoff=tmp_path / "handoff",
        agent_homes={"alpha": tmp_path / "alpha"}, transport=Accepting()))

    res = b.submit("alpha", Message(sender="alpha@agents.test",
                                    to=["far@example.org"], subject="s", body="b"))
    d = res["delivered"][0]
    assert d["state"] == "submitted"
    assert d["detail"] == "accepted for sending (202)"
    assert d["trust"] == "", "the transport reason leaked back into the trust slot"


# ------------------------------------- broker-side conservation (spec V19)

def _ledger(tmp_path, audit_lines, records):
    import json as _json
    a = tmp_path / "audit.jsonl"
    a.write_text("".join(_json.dumps(l) + "\n" for l in audit_lines))
    d = tmp_path / "disp"
    d.mkdir()
    for mid, recips in records.items():
        (d / f"{mid}.json").write_text(_json.dumps({
            "message_id": mid,
            "recipients": {r: {"history": [{"state": s, "detail": "", "at": "t"}]}
                           for r, s in recips.items()}}))
    return a, d


def _audited(mid, recips, ts="2026-01-01T00:00:00+00:00"):
    return {"decision": "allowed", "direction": "outbound", "sender": "alpha",
            "recipients": recips, "message_id": mid, "ts": ts}


def test_a_balanced_ledger_balances_and_declares_its_window(tmp_path):
    """KNOWN-ANSWER GREEN FIRST, and the window is part of the answer:
    "balanced" over an undeclared window is a true statement that misinforms,
    which is the same defect as a green suite with no denominator."""
    from macf.amail.broker import reconcile_outbound
    a, d = _ledger(tmp_path, [_audited("m1", ["x@e.org"])],
                   {"m1": {"x@e.org": "submitted"}})
    r = reconcile_outbound(a, d, since="2025-01-01T00:00:00+00:00")
    assert r["ok"]
    assert r["audited_pairs"] == 1 and r["in_flight"] == 1
    assert r["window"]["since"] == "2025-01-01T00:00:00+00:00"


def test_a_missing_record_goes_red_naming_the_pair(tmp_path):
    """The direction the agent-side check also covers, kept here because a
    ledger that only catches the other direction is half a ledger."""
    from macf.amail.broker import reconcile_outbound
    a, d = _ledger(tmp_path, [_audited("m1", ["x@e.org", "y@e.org"])],
                   {"m1": {"x@e.org": "delivered"}})
    r = reconcile_outbound(a, d)
    assert not r["ok"]
    assert r["missing_record"] == ["m1/y@e.org"]


def test_an_orphan_record_goes_red(tmp_path):
    """THE DIRECTION NOTHING COULD SEE BEFORE THIS EXISTED.

    The agent-side reconciliation walks SENT COPIES and looks up a disposition
    per copy, so a record matching no copy at all passes it completely --
    measured on the live deployment by planting one and watching the check stay
    green. This walks the store and finds it.
    """
    from macf.amail.broker import reconcile_outbound
    a, d = _ledger(tmp_path, [_audited("m1", ["x@e.org"])],
                   {"m1": {"x@e.org": "delivered"},
                    "m-forged": {"z@e.org": "delivered"}})
    r = reconcile_outbound(a, d)
    assert not r["ok"]
    assert r["orphan_record"] == ["m-forged/z@e.org"]


def test_abandoned_is_terminal_and_not_a_discrepancy(tmp_path):
    """Where no positive terminal disposition is observable, every correctly
    submitted message ages to `abandoned`. A checker that flags it reports a
    shortfall for correct behaviour, and the response to that is somebody
    widening the tolerance until the alarm stops complaining."""
    from macf.amail.broker import reconcile_outbound
    a, d = _ledger(tmp_path, [_audited("m1", ["x@e.org"])],
                   {"m1": {"x@e.org": "abandoned"}})
    r = reconcile_outbound(a, d)
    assert r["ok"], "abandoned was treated as a discrepancy"
    assert r["abandoned"] == 1 and r["terminal"] == 1


def test_an_unreadable_record_is_not_an_absent_one(tmp_path):
    """Refuses to guess. Treating corruption as absence would let a shortfall
    look like corruption, and corruption look like a shortfall."""
    from macf.amail.broker import reconcile_outbound
    a, d = _ledger(tmp_path, [_audited("m1", ["x@e.org"])],
                   {"m1": {"x@e.org": "delivered"}})
    (d / "damaged.json").write_text("{ not json")
    r = reconcile_outbound(a, d)
    assert not r["ok"]
    assert any("damaged.json" in u for u in r["unreadable"])


def test_only_one_side_configured_is_not_a_check(tmp_path):
    from macf.amail.broker import reconcile_outbound
    assert not reconcile_outbound(None, tmp_path)["ok"]
    assert not reconcile_outbound(tmp_path / "a", None)["ok"]
