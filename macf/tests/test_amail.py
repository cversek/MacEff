"""Tests for amail: the broker, the contact restriction, and the message model.

The security property under test is stated in the amail policy:

    A fully compromised agent still cannot send to an address outside its contact
    list, because it has never held a credential that reaches the internet.

That claim is only worth anything if the check enforcing it has been observed
failing. Each guarantee below therefore has a negative control that breaks the
mechanism and proves the test notices.
"""
from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest

from macf.amail import (
    AuditLog, Broker, BrokerConfig, BrokerUnavailable, ContactBook,
    ContactListError, DeliveryError, Message, serve, store, submit,
)

DOMAIN = "example.test"


@pytest.fixture
def deployment(tmp_path):
    """Two local agents, a contact list permitting each to write to the other."""
    homes = {a: tmp_path / a for a in ("alpha", "beta")}
    for h in homes.values():
        h.mkdir(parents=True)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(json.dumps({
        "alpha": [f"beta@{DOMAIN}"],
        "beta": [f"alpha@{DOMAIN}"],
    }))
    cfg = BrokerConfig(
        domain=DOMAIN, agent_homes=homes, contacts_path=contacts,
        audit_path=tmp_path / "audit.jsonl", socket_path=tmp_path / "b.sock",
        credentials_path=tmp_path / "smarthost.cred",
    )
    return {"cfg": cfg, "broker": Broker(cfg), "homes": homes,
            "contacts": contacts, "tmp": tmp_path}


def msg(to=f"beta@{DOMAIN}", sender=f"alpha@{DOMAIN}", subject="s", body="b"):
    return Message(sender=sender, to=[to] if isinstance(to, str) else to,
                   subject=subject, body=body)


# ---------------------------------------------------------------------------
# The security property
# ---------------------------------------------------------------------------


class TestContactRestriction:
    def test_permitted_recipient_is_delivered(self, deployment):
        r = deployment["broker"].submit("alpha", msg())
        assert r["ok"] is True
        assert store.read_all(deployment["homes"]["beta"])[0].body == "b"

    def test_unlisted_recipient_is_refused(self, deployment):
        r = deployment["broker"].submit("alpha", msg(to="stranger@elsewhere.test"))
        assert r["ok"] is False
        assert "not in the contact list" in r["refused"][0]

    def test_refusal_delivers_nothing_anywhere(self, deployment):
        """Negative control on the refusal itself: a refused message must not
        appear in ANY mailbox, not merely fail to reach the stranger."""
        deployment["broker"].submit("alpha", msg(to="stranger@elsewhere.test"))
        for home in deployment["homes"].values():
            assert store.read_all(home) == []

    def test_partially_permitted_message_is_refused_entirely(self, deployment):
        """One permitted recipient and one not: refuse the whole message.

        Partial delivery would leave the caller to reconcile 'sent to some' — and
        callers get that wrong.
        """
        r = deployment["broker"].submit(
            "alpha", msg(to=[f"beta@{DOMAIN}", "stranger@elsewhere.test"]))
        assert r["ok"] is False
        assert store.read_all(deployment["homes"]["beta"]) == []

    def test_case_variation_does_not_evade_the_check(self, deployment):
        """A restriction sidestepped by capitalising a letter is not one."""
        r = deployment["broker"].submit("alpha", msg(to="STRANGER@ELSEWHERE.TEST"))
        assert r["ok"] is False

    def test_permitted_recipient_matches_case_insensitively(self, deployment):
        r = deployment["broker"].submit("alpha", msg(to=f"BETA@{DOMAIN.upper()}"))
        assert r["ok"] is True

    def test_sender_with_no_contacts_is_refused(self, deployment):
        """An agent absent from the contact list gets no implicit permission."""
        r = deployment["broker"].submit("gamma", msg(sender=f"gamma@{DOMAIN}"))
        assert r["ok"] is False

    def test_missing_contact_list_fails_closed(self, deployment, tmp_path):
        """An absent list is 'not configured', never 'no restriction'."""
        deployment["contacts"].unlink()
        with pytest.raises(ContactListError):
            ContactBook(deployment["contacts"]).contacts_for("alpha")

    def test_negative_control_removing_the_check_delivers_to_a_stranger(self, deployment, monkeypatch):
        """THE control that makes the tests above meaningful.

        Stub the enforcement to permit everything. The stranger's message is then
        only undeliverable because no transport exists — proving the earlier
        refusals came from the contact check and not from delivery failing anyway.
        """
        monkeypatch.setattr(Broker, "_check", lambda self, s, r: [])
        deployment["cfg"].agent_homes["stranger"] = deployment["tmp"] / "stranger"
        (deployment["tmp"] / "stranger").mkdir()
        monkeypatch.setattr(deployment["cfg"], "domain", "elsewhere.test")
        r = deployment["broker"].submit("alpha", msg(to="stranger@elsewhere.test"))
        assert r["ok"] is True, "with the check removed the message must go through"
        assert len(store.read_all(deployment["tmp"] / "stranger")) == 1


class TestCredentialCustody:
    def test_credential_is_not_readable_by_others(self, deployment):
        """The property the whole design rests on, checked against the filesystem."""
        cred = deployment["cfg"].credentials_path
        cred.write_text("smarthost-secret")
        cred.chmod(0o600)
        assert deployment["broker"].credential_readable_by_others() is False

    @pytest.mark.parametrize("mode,label", [(0o640, "group"), (0o604, "other"), (0o644, "both")])
    def test_negative_control_loosened_permissions_are_detected(self, deployment, mode, label):
        """Negative control: widen the mode and the check must notice.

        Without this, credential_readable_by_others could return False
        unconditionally and the guarantee above would be vacuous.
        """
        cred = deployment["cfg"].credentials_path
        cred.write_text("smarthost-secret")
        cred.chmod(mode)
        assert deployment["broker"].credential_readable_by_others() is True, (
            f"{label}-readable credential was not detected")

    def test_absent_credential_is_not_reported_as_exposed(self, deployment):
        """A missing file is not a leak; only a present, readable one is."""
        assert deployment["broker"].credential_readable_by_others() is False


class TestEnforcementLocation:
    def test_client_module_performs_no_contact_check(self):
        """Enforcement must not live in agent-side code.

        A check in the client is advisory — the agent controls that file. This
        asserts the client never consults a contact list, so the guarantee cannot
        quietly migrate to where an agent could remove it.
        """
        import inspect
        from macf.amail import client
        src = inspect.getsource(client)
        assert "ContactBook" not in src
        assert "permits" not in src

    def test_client_has_no_fallback_transport(self, tmp_path):
        """With the broker down, sending must fail — not find another way out."""
        with pytest.raises(BrokerUnavailable):
            submit("alpha", msg(), tmp_path / "nonexistent.sock")


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class TestAudit:
    def test_allowed_send_is_recorded(self, deployment):
        deployment["broker"].submit("alpha", msg())
        recs = list(deployment["broker"].audit.records())
        assert [r["decision"] for r in recs] == ["allowed"]
        assert recs[0]["rung"] == "local"

    def test_refusal_is_recorded_with_a_reason(self, deployment):
        """A log holding only successes cannot distinguish 'nothing was refused'
        from 'refusal logging is broken'."""
        deployment["broker"].submit("alpha", msg(to="stranger@elsewhere.test"))
        refusals = deployment["broker"].audit.refusals()
        assert len(refusals) == 1
        assert "not in the contact list" in refusals[0]["reason"]

    def test_log_is_append_only_across_decisions(self, deployment):
        b = deployment["broker"]
        b.submit("alpha", msg())
        b.submit("alpha", msg(to="stranger@elsewhere.test"))
        b.submit("alpha", msg())
        assert [r["decision"] for r in b.audit.records()] == ["allowed", "refused", "allowed"]

    def test_records_survive_a_malformed_line(self, deployment):
        """One corrupt line must not make the whole log unreadable."""
        b = deployment["broker"]
        b.submit("alpha", msg())
        with open(b.audit.path, "a") as f:
            f.write("{not json\n")
        b.submit("alpha", msg())
        assert len(list(b.audit.records())) == 2


# ---------------------------------------------------------------------------
# Contact list semantics
# ---------------------------------------------------------------------------


class TestContactListSemantics:
    def test_changes_take_effect_without_restart(self, deployment):
        """Success criterion: no rebuild, and here not even a process restart."""
        b = deployment["broker"]
        assert b.submit("alpha", msg(to="late@example.test"))["ok"] is False
        deployment["cfg"].agent_homes["late"] = deployment["tmp"] / "late"
        (deployment["tmp"] / "late").mkdir()
        deployment["contacts"].write_text(json.dumps({
            "alpha": [f"beta@{DOMAIN}", f"late@{DOMAIN}"], "beta": [f"alpha@{DOMAIN}"]}))
        assert b.submit("alpha", msg(to=f"late@{DOMAIN}"))["ok"] is True

    @pytest.mark.parametrize("key", ["host", "transport", "via", "tailnet", "relay"])
    def test_entries_encoding_a_route_are_rejected(self, tmp_path, key):
        """A contact names a correspondent, never a route. Reachability is runtime
        state; in config it guarantees drift on every topology change."""
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"alpha": [{"address": "x@y.test", key: "somewhere"}]}))
        with pytest.raises(ContactListError, match="records reachability"):
            ContactBook(p).contacts_for("alpha")

    def test_plain_object_entry_without_route_is_accepted(self, tmp_path):
        """Negative control for the rule above: the same shape minus the route key."""
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"alpha": [{"address": "x@y.test", "note": "a peer"}]}))
        assert ContactBook(p).contacts_for("alpha") == ["x@y.test"]


# ---------------------------------------------------------------------------
# Message model
# ---------------------------------------------------------------------------


class TestMessageModel:
    def test_ids_need_no_coordination_and_do_not_collide(self):
        ids = {Message(sender="a", to=["b"], subject="", body="").message_id
               for _ in range(500)}
        assert len(ids) == 500

    def test_opener_mints_the_thread_and_a_reply_joins_it(self):
        a = msg()
        r = a.reply(sender=f"beta@{DOMAIN}", body="ack")
        assert r.thread_id == a.thread_id
        assert r.parent == a.message_id

    def test_ordering_is_derived_not_counted(self):
        """No sequence numbers anywhere — the field must not exist, so no future
        code can start depending on one."""
        assert not hasattr(Message(sender="a", to=["b"], subject="", body=""), "sequence")
        assert "seq" not in Message.__dataclass_fields__

    def test_sort_key_breaks_ties_deterministically(self):
        """Two messages in the same second must still order identically for every
        reader, or two participants render a thread differently."""
        a = Message(sender="a", to=["b"], subject="", body="", date="2026-01-01T00:00:00+00:00")
        b = Message(sender="a", to=["b"], subject="", body="", date="2026-01-01T00:00:00+00:00")
        assert sorted([a, b], key=lambda m: m.sort_key()) == sorted([b, a], key=lambda m: m.sort_key())

    def test_serialize_round_trips(self):
        a = msg(subject="ünïcode ✉", body="line one\nline two")
        b = Message.deserialize(a.serialize())
        for f in ("message_id", "thread_id", "sender", "to", "subject", "body", "date"):
            assert getattr(b, f) == getattr(a, f), f

    def test_serialized_form_carries_no_transport_headers(self):
        """Transport headers belong to the journey, not the message."""
        raw = msg().serialize()
        for h in ("Received:", "DKIM-Signature:", "Return-Path:", "X-Spam"):
            assert h not in raw


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class TestStore:
    def test_delivery_lands_in_new_not_tmp(self, tmp_path):
        """tmp/->new/ rename is the point of Maildir: a reader scanning new/ never
        sees a half-written file."""
        p = store.deliver(tmp_path, msg())
        assert p.parent.name == "new"
        assert list((tmp_path / "Maildir" / "tmp").iterdir()) == []

    def test_mailbox_is_owner_only(self, tmp_path):
        store.deliver(tmp_path, msg())
        mode = (tmp_path / "Maildir").stat().st_mode
        assert not (mode & (stat.S_IRGRP | stat.S_IROTH))

    def test_unreadable_message_does_not_break_the_mailbox(self, tmp_path):
        store.deliver(tmp_path, msg(subject="good"))
        (tmp_path / "Maildir" / "new" / "garbage").write_bytes(b"\xff\xfe not a message")
        assert [m.subject for m in store.read_all(tmp_path)] == ["good"]

    def test_rapid_deliveries_do_not_overwrite_each_other(self, tmp_path):
        """Regression: Maildir names are second-granular, so without a counter two
        deliveries in the same second produce the same filename — and since
        delivery ends in a rename, the second silently OVERWRITES the first. Mail
        vanished with no error anywhere.

        This was found only incidentally by a thread test, which means nothing was
        guarding the property. A broker delivering a thread writes several messages
        in well under a second, so it is the common case, not a rare race.
        """
        for i in range(50):
            store.deliver(tmp_path, msg(subject=f"m{i}"))
        assert len(store.read_all(tmp_path)) == 50
        assert len({m.subject for m in store.read_all(tmp_path)}) == 50

    def test_concurrent_deliveries_do_not_collide(self, tmp_path):
        """The broker serves agents on threads; two threads taking the same
        counter value would reintroduce the collision the lock exists to prevent."""
        import threading as _t
        errs = []

        def worker(n):
            try:
                for i in range(20):
                    store.deliver(tmp_path, msg(subject=f"t{n}-{i}"))
            except Exception as e:  # noqa: BLE001
                errs.append(e)

        threads = [_t.Thread(target=worker, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errs
        assert len(store.read_all(tmp_path)) == 100

    def test_thread_filter_returns_only_that_thread(self, tmp_path):
        a = msg(subject="one")
        store.deliver(tmp_path, a)
        store.deliver(tmp_path, msg(subject="unrelated"))
        store.deliver(tmp_path, a.reply(sender=f"beta@{DOMAIN}", body="ack"))
        assert len(store.thread(tmp_path, a.thread_id)) == 2


# ---------------------------------------------------------------------------
# Inbound
# ---------------------------------------------------------------------------


class TestInbound:
    def test_listed_sender_is_delivered(self, deployment):
        m = Message(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"], subject="hi", body="x")
        r = deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert r["decision"] == "delivered"
        assert len(store.read_all(deployment["homes"]["beta"])) == 1

    def test_unlisted_sender_is_quarantined_not_rejected(self, deployment):
        """Retained, not bounced: rejecting reveals which addresses exist, and
        forwarded mail legitimately arrives from an unexpected sender."""
        m = Message(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"],
                    subject="?", body="x")
        r = deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert r["decision"] == "quarantined"
        assert store.read_all(deployment["homes"]["beta"]) == []
        q = deployment["homes"]["beta"] / "Maildir" / "quarantine"
        assert len(list(q.iterdir())) == 1

    def test_quarantine_records_the_reason(self, deployment):
        m = Message(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"], subject="?", body="x")
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        q = next((deployment["homes"]["beta"] / "Maildir" / "quarantine").iterdir())
        assert "X-Amail-Quarantine-Reason:" in q.read_text()

    def test_inbound_decisions_are_audited(self, deployment):
        m = Message(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"], subject="?", body="x")
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        rec = [r for r in deployment["broker"].audit.records() if r["direction"] == "inbound"]
        assert rec[0]["decision"] == "quarantined"


# ---------------------------------------------------------------------------
# Delivery honesty
# ---------------------------------------------------------------------------


class TestDeliveryHonesty:
    def test_undeliverable_recipient_is_never_reported_as_sent(self, deployment, monkeypatch):
        """Rung 3 is not implemented. It must raise, not silently succeed — a
        transport that reports delivery it did not perform is the failure this
        whole subsystem exists to avoid."""
        monkeypatch.setattr(Broker, "_check", lambda self, s, r: [])
        r = deployment["broker"].submit("alpha", msg(to="someone@remote.test"))
        assert r["ok"] is False
        assert "no transport" in r["failures"][0]["error"]

    def test_delivery_failure_is_audited_as_an_error(self, deployment, monkeypatch):
        monkeypatch.setattr(Broker, "_check", lambda self, s, r: [])
        deployment["broker"].submit("alpha", msg(to="someone@remote.test"))
        assert any(r["decision"] == "error" for r in deployment["broker"].audit.records())


# ---------------------------------------------------------------------------
# Socket path — the production path
# ---------------------------------------------------------------------------


class TestOverTheSocket:
    @pytest.fixture
    def running(self, deployment):
        srv = serve(deployment["broker"])
        time.sleep(0.15)
        yield deployment
        srv.shutdown()

    def test_agent_to_agent_without_a_human_relay(self, running):
        """The headline criterion, exercised over the real socket."""
        r = submit("alpha", msg(body="no human touched this"), running["cfg"].socket_path)
        assert r["ok"] is True
        assert store.read_all(running["homes"]["beta"])[0].body == "no human touched this"

    def test_refusal_travels_back_to_the_agent(self, running):
        """An agent that cannot tell a message was refused learns to believe mail
        was delivered."""
        r = submit("alpha", msg(to="stranger@elsewhere.test"), running["cfg"].socket_path)
        assert r["ok"] is False and r["refused"]

    def test_malformed_request_does_not_kill_the_broker(self, running):
        """One bad request must not stop the broker serving every other agent."""
        import socket as s_
        c = s_.socket(s_.AF_UNIX, s_.SOCK_STREAM)
        c.connect(str(running["cfg"].socket_path))
        c.sendall(b"{ not json\n")
        c.recv(4096)
        c.close()
        assert submit("alpha", msg(), running["cfg"].socket_path)["ok"] is True
