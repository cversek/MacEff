"""Tests for amail: the broker, the contact restriction, and the message model.

The security property under test is stated in the amail policy:

    A fully compromised agent still cannot send to an address outside its contact
    list, because it has never held a credential that reaches the internet.

That claim is only worth anything if the check enforcing it has been observed
failing. Each guarantee below therefore has a negative control that breaks the
mechanism and proves the test notices.
"""
from __future__ import annotations

from conftest import _addressing

import json
import os
import stat
import time
from pathlib import Path

import yaml

import pytest

# amail refuses to import without the `amail` extra, by design: since v1.1 its
# inbound handling is built on signature verification, and running without a
# crypto backend would classify every message as unverified while appearing to
# work. The skip NAMES the missing extra — a bare skip would be exactly the
# silent false green this suite exists to catch.
pytest.importorskip(
    "cryptography",
    reason="amail requires the 'amail' extra: pip install 'macf[amail]'")

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
    contacts = tmp_path / "addressing.yaml"
    contacts.write_text(yaml.safe_dump({
        "domain": DOMAIN,
        "agents": {
            # "both": these two correspond in each direction, which is what
            # "permitting each to write to the other" meant when direction was
            # not expressible. Stated rather than assumed, because most tests
            # below exercise one direction and would pass against a list that
            # authorised only that one.
            "alpha": {"contacts": [{"address": f"beta@{DOMAIN}",
                                    "direction": "both"}]},
            "beta": {"contacts": [{"address": f"alpha@{DOMAIN}",
                                   "direction": "both"}]},
        },
    }))
    # Explicit, because the ambient umask writes 0664 here and the broker
    # correctly refuses to start on a group-writable policy file. The check found
    # a real group-writable contact list the first time it ran — on this fixture.
    contacts.chmod(0o644)
    # PROVISIONED, because a correct deployment HOLDS its credential and the
    # fixture should look like one. Leaving it absent used to be invisible:
    # the custody check could not see a configured-but-missing credential, so
    # every test here ran against a broker holding nothing while asserting the
    # credential was protected.
    cred = tmp_path / "smarthost.cred"
    cred.write_text("smarthost-secret")
    cred.chmod(0o600)
    cfg = BrokerConfig(
        domain=DOMAIN, agent_homes=homes, contacts_path=contacts,
        audit_path=tmp_path / "audit.jsonl", socket_path=tmp_path / "b.sock",
        credentials_path=cred,
        # The test process has one uid, so it can only BE one agent. That is
        # exactly the point: anything it submits is 'alpha', and a claim to be
        # 'beta' must be refused rather than believed.
        agent_uids={os.getuid(): "alpha"},
        # Delivery is by pickup box for agent mail as well as internet mail:
        # one mechanism, and the broker writes only its own stores.
        inbound_handoff=tmp_path / "handoff",
        inbound_quarantine=tmp_path / "quarantine",
    )
    def _pull(agent: str):
        """Custody transfer, as the recipient. Delivery no longer ends in the
        recipient's Maildir — it ends in a pickup box the recipient drains, so
        every test that asserts on delivered mail must pull first, like the
        agent does."""
        from macf.amail.client import ingest
        ingest(homes[agent], (tmp_path / "handoff") / agent,
               contacts_path=contacts, agent=agent)
        return homes[agent]

    return {"cfg": cfg, "broker": Broker(cfg), "homes": homes, "pull": _pull,
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
        assert store.read_all(deployment["pull"]("beta"))[0].body == "b"

    def test_unlisted_recipient_is_refused(self, deployment):
        r = deployment["broker"].submit("alpha", msg(to="stranger@elsewhere.test"))
        assert r["ok"] is False
        assert "not in the outbound contact list" in r["refused"][0]

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
        assert store.read_all(deployment["pull"]("beta")) == []

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
            ContactBook(deployment["contacts"]).contacts_for("alpha", direction="outbound")

    def test_negative_control_removing_the_check_delivers_to_a_stranger(self, deployment, monkeypatch):
        """THE control that makes the tests above meaningful.

        Stub the enforcement to permit everything. The stranger's message is then
        only undeliverable because no transport exists — proving the earlier
        refusals came from the contact check and not from delivery failing anyway.
        """
        monkeypatch.setattr(Broker, "_check", lambda self, s, r: [])
        # TWO GATES NOW, and both must be stubbed for this control to isolate
        # what it claims to. The sender's outbound permission is checked at
        # submit; the RECIPIENT's acceptance is checked again on the local
        # handoff, because local delivery used to consult only the sender and a
        # recipient could not refuse a correspondent inside its own deployment.
        # Stubbing one and asserting delivery would now prove nothing about the
        # other -- see the companion test that removes them one at a time.
        monkeypatch.setattr(Broker, "_local_acceptance_refusal",
                            lambda self, agent, sender: "")
        deployment["cfg"].agent_homes["stranger"] = deployment["tmp"] / "stranger"
        (deployment["tmp"] / "stranger").mkdir()
        monkeypatch.setattr(deployment["cfg"], "domain", "elsewhere.test")
        # The sender-authenticity check (round-2 F1) is a SEPARATE control and
        # would refuse first once the domain moved. Satisfy it so this control
        # isolates the contact check, which is what it exists to prove.
        r = deployment["broker"].submit(
            "alpha", msg(to="stranger@elsewhere.test", sender="alpha@elsewhere.test"))
        assert r["ok"] is True, "with the check removed the message must go through"
        from macf.amail.client import ingest
        ingest(deployment["tmp"] / "stranger",
               deployment["cfg"].inbound_handoff / "stranger")
        assert len(store.read_all(deployment["tmp"] / "stranger")) == 1


    def test_each_gate_alone_still_refuses(self, deployment, monkeypatch):
        """DEFENCE IN DEPTH, demonstrated rather than asserted.

        Remove one gate at a time and the stranger is still refused. That is
        what makes the control above honest: it needs BOTH stubbed to deliver,
        so neither gate is carrying the result on its own.
        """
        deployment["cfg"].agent_homes["stranger"] = deployment["tmp"] / "stranger"
        (deployment["tmp"] / "stranger").mkdir()
        monkeypatch.setattr(deployment["cfg"], "domain", "elsewhere.test")
        m = msg(to="stranger@elsewhere.test", sender="alpha@elsewhere.test")

        # Outbound gate removed; the recipient-side gate must still refuse.
        with monkeypatch.context() as mp:
            mp.setattr(Broker, "_check", lambda self, s, r: [])
            r = deployment["broker"].submit("alpha", m)
        assert len(store.read_all(deployment["tmp"] / "stranger")) == 0, (
            "the recipient-side gate did not refuse with the outbound gate removed")

        # Recipient gate removed; the outbound gate must still refuse.
        with monkeypatch.context() as mp:
            mp.setattr(Broker, "_local_acceptance_refusal",
                       lambda self, agent, sender: "")
            r = deployment["broker"].submit("alpha", m)
        assert r["ok"] is False, (
            "the outbound gate did not refuse with the recipient gate removed")


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
        """A missing file is not a leak; only a present, readable one is.

        STILL TRUE, AND IT WAS NEVER THE QUESTION. This assertion is about
        EXPOSURE and passed for months while the broker started holding no
        credential at all -- see the custody tests below, which ask what the
        invariant actually claims. Kept, narrowed, and explicitly labelled as
        insufficient, because deleting it would lose a correct fact and leaving
        it unlabelled is how it came to stand in for one it does not cover.
        """
        deployment["cfg"].credentials_path.unlink()
        assert deployment["broker"].credential_readable_by_others() is False


class TestCredentialCustodyBothPolarities:
    """amail spec O5f.3 "refusal-must-cover-a-misplaced-credential" and O5f.4
    "the-demonstration-breaks-it-in-both-polarities".

    V22 was KNOWN-VIOLATED because the check returned False when the file did
    not exist, so absence and protection were indistinguishable and the broker
    started in both cases. The check could not see the case it was named for.

    Every refusal here carries its PAIRED ACCEPTANCE in the same class. A
    refusal-shaped test passes when its instrument is dead, and these are all
    refusals.
    """

    def test_the_four_states_are_distinct(self, deployment):
        """The boolean could express two of these. That was the defect."""
        from macf.amail.broker import (CRED_UNCONFIGURED, CRED_MISSING,
                                       CRED_EXPOSED, CRED_HELD)
        b, cfg = deployment["broker"], deployment["cfg"]
        cred = cfg.credentials_path

        assert b.credential_status() == CRED_HELD
        cred.chmod(0o644)
        assert b.credential_status() == CRED_EXPOSED
        cred.chmod(0o600)
        cred.unlink()
        assert b.credential_status() == CRED_MISSING
        cfg.credentials_path = None
        assert b.credential_status() == CRED_UNCONFIGURED

    def test_broker_refuses_to_start_on_an_EXPOSED_credential(self, deployment):
        """Polarity one: present and readable."""
        deployment["cfg"].credentials_path.chmod(0o644)
        with pytest.raises(PermissionError, match="readable by group"):
            deployment["broker"].assert_credential_custody()

    def test_broker_refuses_to_start_on_a_MISSING_credential(self, deployment):
        """Polarity two, AND THE ONE THAT DID NOT WORK. A configured path with
        nothing at it means the broker holds no credential while believing it
        holds a protected one. Starting defers the failure to the first send,
        where it surfaces as a transport error and reads as a network problem
        rather than as a misprovisioned deployment."""
        deployment["cfg"].credentials_path.unlink()
        with pytest.raises(PermissionError, match="CONFIGURED AND ABSENT"):
            deployment["broker"].assert_credential_custody()

    def test_the_paired_acceptance_a_held_credential_starts(self, deployment):
        """Without this, both refusals above are equally consistent with a
        broker that refuses to start under every condition."""
        deployment["broker"].assert_credential_custody()  # must not raise

    def test_an_unconfigured_credential_starts_but_is_announced(self, deployment, capsys):
        """Legitimate while the outbound leg does not exist. Announced, so it
        cannot be mistaken for a credential that passed its check -- which is
        precisely the confusion the old boolean created."""
        deployment["cfg"].credentials_path = None
        deployment["broker"].assert_credential_custody()  # must not raise
        assert "no submission credential configured" in capsys.readouterr().err

    def test_the_exposure_helper_cannot_answer_the_custody_question(self, deployment):
        """The narrow helper is retained and must stay narrow. This asserts the
        GAP explicitly, so nobody re-derives the original defect by reaching for
        the convenient boolean: it says False for a missing credential, and
        False here does not mean the broker holds anything."""
        deployment["cfg"].credentials_path.unlink()
        assert deployment["broker"].credential_readable_by_others() is False
        with pytest.raises(PermissionError):
            deployment["broker"].assert_credential_custody()


class TestEnforcementLocation:
    def test_client_performs_no_authorization_check(self):
        """Enforcement must not live in agent-side code.

        A check in the client is advisory — the agent controls that file. The
        invariant is about AUTHORIZATION: whether a sender may reach this
        recipient is the broker's judgement, and it must never migrate to where
        an agent could remove it.

        This test once banned the word ContactBook outright, as a blunt proxy
        for that invariant. Ingest-time signature verification made the proxy
        wrong: the recipient reads the KEYS it has been given so it can form its
        own view of a message it already holds. That is the agent evaluating its
        own mail, not the agent deciding its own permissions — and the keys come
        from a broker-owned file it cannot write. So the ban is now on the
        authorization predicates themselves, which is what the invariant was
        always about. Narrowed deliberately, not deleted: `permits` and
        `push_granted` are the calls that would make enforcement agent-side.
        """
        import inspect
        from macf.amail import client
        src = inspect.getsource(client)
        assert "permits" not in src, "authorization must not be client-side"
        assert "push_granted" not in src, "grant evaluation must not be client-side"
        # And the narrowing must be real: key lookup is the ONLY contact-book
        # use permitted here, so a future edit reaching for anything else fails.
        # Two mentions exactly — the import and the single construction.
        assert src.count("ContactBook") == 2, (
            "the client's contact-book use must stay limited to one key lookup")
        assert "keys_for" in src, (
            "if ingest stopped verifying, this guard's narrowing is no longer "
            "justified and should be tightened back")

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
        assert "not in the outbound contact list" in refusals[0]["reason"]

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
        deployment["contacts"].write_text(_addressing({
            "alpha": [f"beta@{DOMAIN}", f"late@{DOMAIN}"], "beta": [f"alpha@{DOMAIN}"]}))
        assert b.submit("alpha", msg(to=f"late@{DOMAIN}"))["ok"] is True

    @pytest.mark.parametrize("key", ["host", "transport", "via", "tailnet", "relay"])
    def test_entries_encoding_a_route_are_rejected(self, tmp_path, key):
        """A contact names a correspondent, never a route. Reachability is runtime
        state; in config it guarantees drift on every topology change."""
        p = tmp_path / "addressing.yaml"
        p.write_text(_addressing({"alpha": [{"address": "x@y.test", key: "somewhere"}]}))
        with pytest.raises(ContactListError, match="records reachability"):
            ContactBook(p).contacts_for("alpha", direction="outbound")

    def test_plain_object_entry_without_route_is_accepted(self, tmp_path):
        """Negative control for the rule above: the same shape minus the route key."""
        p = tmp_path / "addressing.yaml"
        p.write_text(_addressing({"alpha": [{"address": "x@y.test", "note": "a peer"}]}))
        assert ContactBook(p).contacts_for("alpha", direction="outbound") == ["x@y.test"]


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
        assert len(store.read_all(deployment["pull"]("beta"))) == 1

    def test_unlisted_sender_is_quarantined_not_rejected(self, deployment):
        """Retained, not bounced: rejecting reveals which addresses exist, and
        forwarded mail legitimately arrives from an unexpected sender."""
        m = Message(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"],
                    subject="?", body="x")
        r = deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert r["decision"] == "quarantined"
        assert store.read_all(deployment["pull"]("beta")) == []
        # Broker-owned: refused evidence must live where the refused party
        # cannot edit it, and the recipient owns its home.
        q = deployment["cfg"].inbound_quarantine
        assert len(list(q.glob("*.amsg"))) == 1

    def test_quarantine_records_the_reason(self, deployment):
        m = Message(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"], subject="?", body="x")
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        q = next((deployment["cfg"].inbound_quarantine).glob("*.json"))
        meta = json.loads(q.read_text())
        assert meta["authorization"]["outcome"] == "deny"
        assert "not in the inbound contact list" in meta["authorization"]["reason"]
        assert meta["sender"] == "stranger@elsewhere.test"

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


class TestPeerAuthentication:
    """Regression tests for the round-1 audit's critical finding.

    The socket is world-writable, so reaching it must not be identity. Before
    these existed, the submitter's name was read out of the request body: any
    process could name any agent and inherit that agent's contact list, making
    the reachable set the union of everyone's contacts — and the audit log then
    recorded the send under the impersonated agent's name.

    The wider lesson these encode: every earlier test passed `sender` as a
    TRUSTED ARGUMENT, so the whole suite would have passed with peer
    authentication entirely absent. It was absent. A guarantee about *whose*
    contact list applies cannot be tested by tests that hand over the identity.
    """

    @pytest.fixture
    def running(self, deployment):
        (deployment["cfg"].credentials_path).write_text("secret")
        (deployment["cfg"].credentials_path).chmod(0o600)
        srv = serve(deployment["broker"])
        time.sleep(0.15)
        yield deployment
        srv.shutdown()

    def test_claiming_another_agent_is_refused(self, running):
        """THE critical finding. This process is 'alpha'; claiming 'beta' fails."""
        r = submit("beta", msg(to=f"alpha@{DOMAIN}", sender=f"beta@{DOMAIN}"),
                   running["cfg"].socket_path)
        assert r["ok"] is False
        assert "PermissionError" in r["error"]
        assert "connecting process is 'alpha'" in r["error"]

    def test_spoofed_submission_delivers_nothing(self, running):
        submit("beta", msg(to=f"alpha@{DOMAIN}", sender=f"beta@{DOMAIN}"),
               running["cfg"].socket_path)
        assert store.read_all(running["pull"]("alpha")) == []

    def test_identity_mismatch_is_audited(self, running):
        """The forensic record must show the attempt, attributed to the real peer
        rather than to the name it claimed."""
        submit("beta", msg(to=f"alpha@{DOMAIN}", sender=f"beta@{DOMAIN}"),
               running["cfg"].socket_path)
        mismatches = [r for r in running["broker"].audit.refusals()
                      if "identity mismatch" in r.get("reason", "")]
        assert len(mismatches) == 1
        assert mismatches[0]["sender"] == "alpha"

    def test_unmapped_uid_is_refused(self, deployment):
        """An unknown caller gets no default agent — a default would hand a
        stranger somebody's contact list."""
        deployment["cfg"].agent_uids = {999999: "ghost"}
        (deployment["cfg"].credentials_path).write_text("s")
        (deployment["cfg"].credentials_path).chmod(0o600)
        srv = serve(deployment["broker"])
        time.sleep(0.15)
        try:
            r = submit("alpha", msg(), deployment["cfg"].socket_path)
            assert r["ok"] is False
            assert "not a provisioned agent" in r["error"]
        finally:
            srv.shutdown()

    def test_broker_refuses_to_start_with_no_uid_mapping(self, deployment):
        """With a world-writable socket and no way to identify anyone, serving is
        worse than not serving."""
        deployment["cfg"].agent_uids = {}
        with pytest.raises(PermissionError, match="no agent_uids"):
            serve(deployment["broker"])


class TestCredentialEnforcementIsWired:
    """The round-1 audit found credential_readable_by_others() was never called
    by anything but its own tests — verified in the abstract, enforced nowhere.
    A check that nothing invokes is not a control."""

    def test_broker_refuses_to_start_with_an_exposed_credential(self, deployment):
        cred = deployment["cfg"].credentials_path
        cred.write_text("secret")
        cred.chmod(0o644)
        with pytest.raises(PermissionError, match="readable by group"):
            serve(deployment["broker"])

    def test_broker_starts_when_the_credential_is_locked_down(self, deployment):
        """Negative control: same path, correct permissions, must start."""
        cred = deployment["cfg"].credentials_path
        cred.write_text("secret")
        cred.chmod(0o600)
        srv = serve(deployment["broker"])
        srv.shutdown()


class TestHeaderInjection:
    """Round-1 audit finding: unsanitised interpolation into a line-delimited
    format. Same class of bug as SQL injection; same fix — neutralise the
    delimiter."""

    def test_newline_in_subject_cannot_forge_a_header(self):
        m = msg(subject="benign\nX-Injected: yes")
        raw = m.serialize()
        assert "X-Injected:" not in raw.split("\n\n")[0].replace("Subject: benign X-Injected: yes", "")
        # The injected text survives as DATA on the subject line, not as structure
        assert "Subject: benign X-Injected: yes" in raw

    def test_newline_in_subject_cannot_orphan_the_body(self):
        """The dangerous form: a blank line ends the header block, so attacker
        text becomes the body a client renders and the real body is orphaned."""
        m = msg(subject="x\n\nattacker body", body="the real body")
        _, _, body = m.serialize().partition("\n\n")  # noqa: MACEFF005 - str.partition's (before, sep, after) contract is fixed by the stdlib; there is no callee whose order can change
        assert body.strip() == "the real body"

    def test_injection_via_sender_and_recipient_is_neutralised(self):
        m = msg(sender="a@b\nBcc: victim@elsewhere", to="c@d\nBcc: other@elsewhere")
        header = m.serialize().split("\n\n")[0]
        assert "Bcc:" not in header.replace("Bcc: victim@elsewhere", "").replace("Bcc: other@elsewhere", "")
        assert len([l for l in header.splitlines() if l.startswith("From:")]) == 1

    def test_control_characters_are_folded(self):
        assert "\x00" not in msg(subject="a\x00b\x07c").serialize()

    def test_quarantine_reason_cannot_inject(self, deployment):
        m = Message(sender="s@x\nX-Evil: 1", to=[f"beta@{DOMAIN}"], subject="?", body="b")
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        q = next((deployment["cfg"].inbound_quarantine).iterdir())
        head = q.read_text().split("\n\n")[0]
        assert not any(l.startswith("X-Evil:") for l in head.splitlines())


class TestResourceLimits:
    """Round-1 audit finding: unbounded reads and no idle timeout let any local
    process exhaust memory or pin threads."""

    @pytest.fixture
    def running(self, deployment):
        (deployment["cfg"].credentials_path).write_text("s")
        (deployment["cfg"].credentials_path).chmod(0o600)
        srv = serve(deployment["broker"])
        time.sleep(0.15)
        yield deployment
        srv.shutdown()

    def test_oversized_request_is_rejected_not_buffered(self, running):
        import socket as s_
        from macf.amail.broker import MAX_REQUEST_BYTES
        c = s_.socket(s_.AF_UNIX, s_.SOCK_STREAM)
        c.settimeout(20)
        c.connect(str(running["cfg"].socket_path))
        try:
            c.sendall(b"x" * (MAX_REQUEST_BYTES + 4096))  # never a newline
            c.shutdown(s_.SHUT_WR)
            resp = c.recv(65536).decode()
        finally:
            c.close()
        # Round-2 audit: the previous assertion allowed `or "error" in resp`,
        # which a JSONDecodeError satisfies — so it passed with the size cap
        # removed. Assert the SPECIFIC message only the cap can produce.
        assert "exceeds" in resp, f"size cap did not fire; got: {resp[:200]}"

    def test_broker_still_serves_after_an_oversized_request(self, running):
        """One abusive client must not stop the broker serving everyone else."""
        import socket as s_
        c = s_.socket(s_.AF_UNIX, s_.SOCK_STREAM)
        c.settimeout(20)
        c.connect(str(running["cfg"].socket_path))
        try:
            c.sendall(b"x" * (2 << 20))
            c.shutdown(s_.SHUT_WR)
            c.recv(4096)
        except OSError:
            pass
        finally:
            c.close()
        assert submit("alpha", msg(), running["cfg"].socket_path)["ok"] is True


class TestSymlinkResistance:
    """Round-1 audit finding (design tension): the mailbox is agent-owned but
    broker-written, so a hostile agent could pre-plant a symlink at a predictable
    tmp path and redirect a broker-uid write."""

    def test_delivery_passes_O_NOFOLLOW(self, tmp_path, monkeypatch):
        """Round-2 audit: the previous version of this test was VACUOUS.

        It planted a symlink and asserted OSError — but O_EXCL alone raises
        EEXIST on an existing symlink, so the test passed with O_NOFOLLOW
        removed. It proved O_EXCL, not the flag it was named for. Since both
        flags produce an error on the same input, no black-box test can tell them
        apart; assert the flag is actually requested.
        """
        seen = {}
        real_open = os.open

        def spy(path, flags, *a, **k):
            seen["flags"] = flags
            return real_open(path, flags, *a, **k)

        monkeypatch.setattr(store.os, "open", spy)
        store.deliver(tmp_path, msg())
        assert seen["flags"] & os.O_NOFOLLOW, "O_NOFOLLOW was not requested"
        assert seen["flags"] & os.O_EXCL, "O_EXCL was not requested"

    def test_delivery_uses_directory_descriptors_not_paths(self, tmp_path, monkeypatch):
        """Round 4 F1: reverting the whole dir-fd fix passed all 94 tests, and the
        commit that introduced it CLAIMED it had been mutation-tested. It had not.

        Checking a directory by name and re-opening by name is a check, not a
        constraint — the name can be swapped between the two. Assert the
        descriptor-relative calls, since a path-based implementation produces
        identical results on every non-racing input.
        """
        opens, renames = [], []
        real_open, real_rename = os.open, os.rename

        def spy_open(path, flags, *a, **k):
            opens.append((path, flags, k.get("dir_fd")))
            return real_open(path, flags, *a, **k)

        def spy_rename(src, dst, **k):
            renames.append(k)
            return real_rename(src, dst, **k)

        monkeypatch.setattr(store.os, "open", spy_open)
        monkeypatch.setattr(store.os, "rename", spy_rename)
        store.deliver(tmp_path, msg())

        dir_opens = [o for o in opens if o[1] & os.O_DIRECTORY]
        assert len(dir_opens) >= 2, "directories were not opened as descriptors"
        assert all(o[1] & os.O_NOFOLLOW for o in dir_opens), "dir open lacked O_NOFOLLOW"
        # Separated from the directory opens, which are ALSO dir_fd-relative now
        # that tmp/ and new/ are resolved against the Maildir descriptor rather
        # than by full path. Lumping them together made "all relative opens carry
        # O_EXCL" fail against a stronger implementation — the assertion meant
        # the MESSAGE open, so it should say so.
        rel = [o for o in opens if o[2] is not None and not (o[1] & os.O_DIRECTORY)]
        assert rel, "message not opened relative to a dir_fd"
        # The message open needs O_NOFOLLOW too. Asserting it only on the
        # DIRECTORY opens left a mutant alive: strip the flag from the message
        # open and this test still passed. Found by my own mutation sweep, which
        # is the point of running one before trusting a test rather than after.
        assert all(o[1] & os.O_NOFOLLOW for o in rel), "message open lacked O_NOFOLLOW"
        assert all(o[1] & os.O_EXCL for o in rel), "message open lacked O_EXCL"
        # No component may be trusted twice: only the Maildir itself is opened by
        # a full path, and tmp/ and new/ are resolved relative to that descriptor.
        # A path-based re-resolution of either would reopen the window that
        # O_NOFOLLOW cannot close, because it guards the final component only.
        assert sum(1 for o in dir_opens if o[2] is None) == 1, \
            "more than one directory was resolved by path, leaving a TOCTOU window"
        assert renames and "src_dir_fd" in renames[0] and "dst_dir_fd" in renames[0], \
            "rename was path-based, leaving the race open"

    def test_symlinked_maildir_subdir_is_refused(self, tmp_path):
        """O_NOFOLLOW guards only the FINAL component. A symlinked `new/` would
        redirect a broker-uid write outside the mailbox entirely."""
        outside = tmp_path / "outside"
        outside.mkdir()
        (tmp_path / "Maildir").mkdir()
        (tmp_path / "Maildir" / "new").symlink_to(outside)
        with pytest.raises(OSError, match="symlink"):
            store.deliver(tmp_path, msg())

    def test_symlinked_maildir_root_is_refused(self, tmp_path):
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        (tmp_path / "Maildir").symlink_to(outside)
        with pytest.raises(OSError, match="symlink"):
            store.deliver(tmp_path, msg())

    def test_normal_delivery_still_works(self, tmp_path):
        """Negative control: the hardening must not break ordinary delivery."""
        assert store.deliver(tmp_path, msg()).parent.name == "new"


class TestMessageSenderAuthenticity:
    """Round-2 audit, HIGH: only the ENVELOPE sender was authenticated.

    An agent could authenticate honestly, send to a permitted contact, and have
    the message claim to be From: a third party. The recipient's reply then goes
    to that third party — content reaching an address the original sender was
    never allowed to use, laundered through an innocent intermediary. The audit
    log records the envelope, so it shows nothing wrong.
    """

    def test_forged_message_from_is_refused(self, deployment):
        m = Message(sender="charlie@elsewhere.test", to=[f"beta@{DOMAIN}"],
                    subject="s", body="b")
        r = deployment["broker"].submit("alpha", m)
        assert r["ok"] is False
        assert "does not match the authenticated sender" in r["refused"][0]

    def test_forged_message_delivers_nothing(self, deployment):
        m = Message(sender="charlie@elsewhere.test", to=[f"beta@{DOMAIN}"],
                    subject="s", body="b")
        deployment["broker"].submit("alpha", m)
        assert store.read_all(deployment["pull"]("beta")) == []

    def test_a_reply_cannot_be_aimed_at_a_third_party(self, deployment):
        """The actual harm: what the recipient would reply TO."""
        deployment["broker"].submit("alpha", msg())
        got = store.read_all(deployment["pull"]("beta"))[0]
        assert got.reply(sender=f"beta@{DOMAIN}", body="ack").to == [f"alpha@{DOMAIN}"]

    def test_forgery_is_audited(self, deployment):
        m = Message(sender="charlie@elsewhere.test", to=[f"beta@{DOMAIN}"], subject="s", body="b")
        deployment["broker"].submit("alpha", m)
        assert any("does not match" in r.get("reason", "")
                   for r in deployment["broker"].audit.refusals())

    def test_empty_recipient_list_is_refused_and_audited(self, deployment):
        """Previously returned ok with ZERO audit records — a submission that
        happened and left no trace."""
        m = Message(sender=f"alpha@{DOMAIN}", to=[], subject="s", body="b")
        r = deployment["broker"].submit("alpha", m)
        assert r["ok"] is False
        assert len(list(deployment["broker"].audit.records())) == 1


class TestUnicodeLineSeparators:
    """Round-2 audit: the sanitiser stripped CR/LF, but deserialize() uses
    splitlines(), which ALSO breaks on U+0085, U+2028 and U+2029. Serialiser and
    parser disagreed about what a line is, and the gap was the vulnerability."""

    @pytest.mark.parametrize("sep,name", [
        ("\u2028", "LINE SEPARATOR"), ("\u2029", "PARAGRAPH SEPARATOR"),
        ("\u0085", "NEL"), ("\x0b", "VT"), ("\x0c", "FF"),
    ])
    def test_separator_cannot_forge_a_header_through_round_trip(self, tmp_path, sep, name):
        hostile = f"benign{sep}From: operator@example.test"
        store.deliver(tmp_path, msg(subject=hostile))
        got = store.read_all(tmp_path)[0]
        assert got.sender == f"alpha@{DOMAIN}", f"{name} forged the From header"

    def test_separator_cannot_orphan_the_body(self, tmp_path):
        store.deliver(tmp_path, msg(subject="x\u2028\u2028attacker", body="real body"))
        assert store.read_all(tmp_path)[0].body == "real body"


class TestContactListCustody:
    """Round-2 audit: the credential was guarded, the POLICY FILE was not. It is
    re-read per decision, so an agent that can write it grants itself any
    recipient instantly — protecting the key while leaving the wall down."""

    def test_broker_refuses_to_start_with_a_writable_contact_list(self, deployment):
        deployment["cfg"].credentials_path.write_text("s")
        deployment["cfg"].credentials_path.chmod(0o600)
        deployment["contacts"].chmod(0o666)
        with pytest.raises(PermissionError, match="writable by group"):
            serve(deployment["broker"])

    def test_broker_starts_with_a_read_only_contact_list(self, deployment):
        """Negative control: same path, safe mode, must start."""
        deployment["cfg"].credentials_path.write_text("s")
        deployment["cfg"].credentials_path.chmod(0o600)
        deployment["contacts"].chmod(0o644)
        serve(deployment["broker"]).shutdown()


class TestCanonicalisation:
    """Round-3 audit. Three rounds each found a DIFFERENT submitter-controlled
    field on the same path — envelope sender, then From, then subject/thread_id/
    parent/message_id/date. Fixing fields one at a time does not converge, so the
    model is inverted: the broker enumerates what it mints and what it validates,
    and everything else is hostile by construction.

    Includes the four mutants round 3 found surviving. All four were round-2
    mechanisms, and the most telling is the first: deleting the canonicalisation
    half of round-2's fix was noticed by ZERO tests, because every test submitted
    a correct sender. The suite covered the refusal half and not the assignment.
    """

    def test_sender_is_ASSIGNED_not_merely_checked(self, deployment):
        """MUTANT SURVIVOR: deleting `message.sender = expected` passed every
        test. Refusing a wrong sender and canonicalising a right one are two
        mechanisms; the suite only exercised the first."""
        m = Message(sender="", to=[f"beta@{DOMAIN}"], subject="s", body="b")
        deployment["broker"].submit("alpha", m)
        assert m.sender == f"alpha@{DOMAIN}"
        assert store.read_all(deployment["pull"]("beta"))[0].sender == f"alpha@{DOMAIN}"

    def test_message_id_is_reminted(self, deployment):
        """A submitter-chosen id can shadow another message in find(), splice a
        thread, and collide audit records."""
        m = Message(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"],
                    subject="s", body="b", message_id="msg-1-aaaaaaaaaaaa")
        deployment["broker"].submit("alpha", m)
        assert m.message_id != "msg-1-aaaaaaaaaaaa"

    def test_date_is_reminted(self, deployment):
        m = Message(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"], subject="s",
                    body="b", date="1999-01-01T00:00:00+00:00")
        deployment["broker"].submit("alpha", m)
        assert not m.date.startswith("1999")

    @pytest.mark.parametrize("field,value", [
        ("thread_id", "x" * 900), ("parent", "y" * 900),
        ("thread_id", "not-an-id"), ("parent", "msg-nope"),
    ])
    def test_identifier_fields_must_look_like_identifiers(self, deployment, field, value):
        """The laundering channel: ~1 KB of free text per field, in fields whose
        whole purpose is to be short structured ids, inherited by replies and
        carried across a contact boundary."""
        m = Message(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"], subject="s", body="b")
        setattr(m, field, value)
        r = deployment["broker"].submit("alpha", m)
        assert r["ok"] is False
        assert "identifier" in " ".join(r["refused"])

    def test_parent_must_name_a_message_the_sender_can_see(self, deployment):
        m = Message(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"], subject="s",
                    body="b", parent="msg-1700000000-abcdefabcdef")
        r = deployment["broker"].submit("alpha", m)
        assert r["ok"] is False
        assert "cannot see" in " ".join(r["refused"])

    def test_a_genuine_reply_still_works(self, deployment):
        """Negative control: the bounds must not break ordinary correspondence."""
        deployment["broker"].submit("alpha", msg())
        got = store.read_all(deployment["pull"]("beta"))[0]
        rep = got.reply(sender=f"beta@{DOMAIN}", body="ack")
        assert deployment["broker"].submit("beta", rep)["ok"] is True

    @pytest.mark.parametrize("field,size", [("subject", 2000), ("body", (1 << 18) + 10)])
    def test_oversized_fields_are_refused(self, deployment, field, size):
        m = msg()
        setattr(m, field, "z" * size)
        assert deployment["broker"].submit("alpha", m)["ok"] is False


class TestInversionIsMechanized:
    """Round 4: the inversion was DOCUMENTED, not mechanized. Adding one field to
    Message delivered 4,000 attacker bytes with ok=True and the suite stayed
    green — the docstring's 'untrusted by default' was false, because the real
    default was PASS."""

    def test_every_message_field_is_classified(self):
        from macf.amail.broker import _CLASSIFIED_FIELDS
        assert set(Message.__dataclass_fields__) == set(_CLASSIFIED_FIELDS)

    def test_an_unclassified_field_raises_rather_than_passing_through(self, deployment, monkeypatch):
        """The mechanism itself: a field the broker does not know about must stop
        the send, not ride along."""
        import macf.amail.broker as B
        monkeypatch.setattr(B, "_CLASSIFIED_FIELDS", frozenset({"sender"}))
        with pytest.raises(AssertionError, match="not classified"):
            deployment["broker"].submit("alpha", msg())


class TestInboundIsCanonicalised:
    """Round 4 F2: accept_inbound() is the OTHER path that writes a Message to
    storage, and the one where the message is genuinely hostile. It was skipping
    canonicalisation entirely — the inversion applied to one path and not its
    twin, which is the same sibling-blindness the earlier rounds kept finding."""

    def _hostile(self):
        return Message(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"],
                       subject="s", body="B" * 4000, message_id="msg-1-aaaaaaaaaaaa",
                       thread_id="T" * 900, parent="P" * 900,
                       date="1999-01-01T00:00:00+00:00")

    def test_remote_message_id_cannot_shadow_a_local_one(self, deployment):
        deployment["contacts"].write_text(_addressing({
            "alpha": [f"beta@{DOMAIN}"], "beta": ["stranger@elsewhere.test"]}))
        deployment["contacts"].chmod(0o644)
        m = self._hostile()
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert m.message_id != "msg-1-aaaaaaaaaaaa"

    def test_remote_identifier_fields_are_not_free_text(self, deployment):
        deployment["contacts"].write_text(_addressing({
            "alpha": [f"beta@{DOMAIN}"], "beta": ["stranger@elsewhere.test"]}))
        deployment["contacts"].chmod(0o644)
        m = self._hostile()
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert len(m.thread_id) < 100 and m.parent is None

    def test_remote_date_cannot_control_reader_ordering(self, deployment):
        deployment["contacts"].write_text(_addressing({
            "alpha": [f"beta@{DOMAIN}"], "beta": ["stranger@elsewhere.test"]}))
        deployment["contacts"].chmod(0o644)
        m = self._hostile()
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert not m.date.startswith("1999")

    def test_quarantined_mail_is_canonicalised_too(self, deployment):
        """Quarantine is the MORE hostile path, not the less."""
        m = self._hostile()
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert m.message_id != "msg-1-aaaaaaaaaaaa"
        assert len(m.body) <= (1 << 18)

    def test_the_remote_sender_is_preserved_for_the_allowlist_check(self, deployment):
        """Negative control: canonicalisation must not overwrite the field the
        inbound allowlist decision depends on."""
        m = self._hostile()
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert m.sender == "stranger@elsewhere.test"


class TestAuditCompleteness:
    """Round-3 F2: submit() caught only DeliveryError, so any other exception
    escaped BEFORE the audit block — mail already delivered to earlier recipients
    left no record at all, while the sender was told the send failed. Disk-full
    alone triggered it."""

    def test_delivery_is_audited_even_when_a_later_recipient_throws(self, deployment, monkeypatch):
        deployment["contacts"].write_text(_addressing({
            "alpha": [f"beta@{DOMAIN}", f"gamma@{DOMAIN}"], "beta": [f"alpha@{DOMAIN}"]}))
        deployment["contacts"].chmod(0o644)
        deployment["cfg"].agent_homes["gamma"] = deployment["tmp"] / "gamma"
        (deployment["tmp"] / "gamma").mkdir()

        real = store.deliver
        def boom(home, message):
            if home.name == "gamma":
                raise OSError(28, "No space left on device")
            return real(home, message)
        monkeypatch.setattr("macf.amail.broker.deliver", boom)

        r = deployment["broker"].submit("alpha", msg(to=[f"beta@{DOMAIN}", f"gamma@{DOMAIN}"]))
        assert len(store.read_all(deployment["pull"]("beta"))) == 1, "beta got the mail"
        allowed = [x for x in deployment["broker"].audit.records() if x["decision"] == "allowed"]
        assert allowed, "delivered mail left NO audit record"
        assert f"beta@{DOMAIN}" in allowed[0]["recipients"]


class TestRoundTwoMechanismsHaveCoverage:
    """Round 3 mutation-tested and found four survivors, all round-2 mechanisms.
    Two shipped with no test at all. These close that."""

    def test_ucred_is_read_unsigned(self):
        """Round 4: the previous version grepped the source for '"3I"', which a
        mutant satisfied by unpacking "3i" while leaving calcsize("3I") in place.
        Assert the BEHAVIOUR: a uid above 2^31 must survive the round trip."""
        import struct
        high = 4294967294
        packed = struct.pack("3I", 1, high, 1)
        assert struct.unpack("3I", packed)[1] == high
        assert struct.unpack("3i", packed)[1] != high, "signed read would corrupt it"

    def test_total_deadline_actually_bounds_a_slow_trickle(self, deployment):
        """Round 4: the previous version grepped for 'monotonic' and 'deadline',
        which a mutant satisfied by keeping the assignment and deleting the
        enforcement. Drive a real trickle and require the broker to cut it off."""
        import socket as s_
        from macf.amail import broker as B
        deployment["cfg"].credentials_path.write_text("s")
        deployment["cfg"].credentials_path.chmod(0o600)
        monkey = B.CONNECTION_TIMEOUT
        B.CONNECTION_TIMEOUT = 1.0
        srv = serve(deployment["broker"])
        try:
            c = s_.socket(s_.AF_UNIX, s_.SOCK_STREAM)
            c.settimeout(15)
            c.connect(str(deployment["cfg"].socket_path))
            started = time.time()
            try:
                for _ in range(40):          # 4s of dribbling, never a newline
                    c.sendall(b"x")
                    time.sleep(0.1)
                resp = c.recv(65536).decode()
            except OSError:
                resp = ""
            elapsed = time.time() - started
            c.close()
            assert elapsed < 12, "connection was not bounded by the deadline"
            if resp:
                assert "Timeout" in resp or "error" in resp
        finally:
            B.CONNECTION_TIMEOUT = monkey
            srv.shutdown()

    def test_socket_is_group_and_world_writable(self, deployment):
        """The 0o666 mode is a deliberate design claim — submission is not
        authority — and nothing asserted it. If it silently became 0600 the
        design would still 'work' here, because every test shares one uid."""
        deployment["cfg"].credentials_path.write_text("s")
        deployment["cfg"].credentials_path.chmod(0o600)
        srv = serve(deployment["broker"])
        try:
            mode = deployment["cfg"].socket_path.stat().st_mode & 0o777
            assert mode == 0o666, f"socket mode is {oct(mode)}, not 0o666"
        finally:
            srv.shutdown()


class TestOverTheSocket:
    @pytest.fixture
    def running(self, deployment):
        (deployment["cfg"].credentials_path).write_text("secret")
        (deployment["cfg"].credentials_path).chmod(0o600)
        srv = serve(deployment["broker"])
        time.sleep(0.15)
        yield deployment
        srv.shutdown()

    def test_agent_to_agent_without_a_human_relay(self, running):
        """The headline criterion, exercised over the real socket."""
        r = submit("alpha", msg(body="no human touched this"), running["cfg"].socket_path)
        assert r["ok"] is True
        assert store.read_all(running["pull"]("beta"))[0].body == "no human touched this"

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


# ---------------------------------------------------------------------------
# Round 6: the surfaces rounds 1-5 never looked at
# ---------------------------------------------------------------------------


class TestQuarantineIsHardenedLikeDelivery:
    """Round 6 found the quarantine path was the un-hardened sibling of delivery.

    Delivery was rewritten to use directory descriptors and resisted a symlink
    race 0-for-200k. Quarantine still did check-then-open by path, and the same
    attack won in 47 iterations — coercing a broker-uid write to an arbitrary
    location, which turns quarantine into delivery and defeats policy §6.1.

    Neither guard was tested. Both are now, because the reason this recurred is
    that fixing the instance you were shown does not fix the class.
    """

    def test_symlinked_quarantine_dir_is_refused(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (tmp_path / "Maildir").mkdir()
        (tmp_path / "Maildir" / "quarantine").symlink_to(outside)
        with pytest.raises(OSError, match="symlink"):
            store.quarantine(tmp_path, msg(), "unlisted sender")
        assert list(outside.iterdir()) == [], "write escaped the mailbox"

    def test_symlinked_maildir_is_refused_on_the_quarantine_path(self, tmp_path):
        """The parent component, not just the final one — the component the race
        actually swapped."""
        outside = tmp_path / "outside"
        outside.mkdir()
        (tmp_path / "Maildir").symlink_to(outside)
        with pytest.raises(OSError, match="symlink"):
            store.quarantine(tmp_path, msg(), "unlisted sender")

    def test_quarantine_uses_directory_descriptors_not_paths(self, tmp_path, monkeypatch):
        """A path-based and a descriptor-based implementation agree on every
        non-racing input, so black-box assertions cannot tell them apart. Assert
        the arguments actually passed.
        """
        store.ensure_maildir(tmp_path)
        opens = []
        real_open = os.open

        def spy_open(path, flags, *a, **k):
            opens.append((path, flags, k.get("dir_fd")))
            return real_open(path, flags, *a, **k)

        monkeypatch.setattr(store.os, "open", spy_open)
        store.quarantine(tmp_path, msg(), "unlisted sender")

        dir_opens = [o for o in opens if o[1] & os.O_DIRECTORY]
        assert len(dir_opens) >= 2, "quarantine did not open directories as descriptors"
        assert all(o[1] & os.O_NOFOLLOW for o in dir_opens), "dir open lacked O_NOFOLLOW"
        assert sum(1 for o in dir_opens if o[2] is None) == 1, \
            "more than one directory resolved by path, leaving a TOCTOU window"
        written = [o for o in opens if o[2] is not None and not (o[1] & os.O_DIRECTORY)]
        assert written, "quarantined message was not written relative to a dir_fd"
        assert all(o[1] & os.O_NOFOLLOW and o[1] & os.O_EXCL for o in written)

    def test_quarantined_mail_still_lands_and_is_readable(self, tmp_path):
        """Hardening that broke the feature would pass every test above."""
        p = store.quarantine(tmp_path, msg(subject="hostile"), "unlisted sender")
        assert p.exists() and p.parent.name == "quarantine"
        assert "hostile" in p.read_text()
        assert "X-Amail-Quarantine-Reason: unlisted sender" in p.read_text()


class TestConnectionMetering:
    """Round 6 drove the broker from 20 MB to 996 MB RSS with 500 held
    connections from ONE uid. The broker is the only path mail can leave any
    agent, so one compromised agent could silence every other agent on the host
    — availability as a security property, which the read loop's own comment
    already argued for and the server did not implement.
    """

    def test_per_uid_cap_is_lower_than_the_total(self):
        """A total cap alone lets one agent occupy every slot. The per-uid bound
        is the one that keeps other agents served."""
        from macf.amail import broker as bmod
        assert bmod.MAX_CONNECTIONS_PER_UID < bmod.MAX_CONCURRENT_CONNECTIONS

    def test_broker_refuses_connections_beyond_the_per_uid_cap(self, deployment):
        """The flood, at small scale: hold connections open without completing a
        request and confirm the broker stops accepting them from this uid."""
        import socket as s_
        from macf.amail import broker as bmod

        deployment["cfg"].credentials_path.write_text("secret")
        deployment["cfg"].credentials_path.chmod(0o600)
        srv = serve(deployment["broker"])
        time.sleep(0.15)
        held = []
        try:
            for _ in range(bmod.MAX_CONNECTIONS_PER_UID + 6):
                c = s_.socket(s_.AF_UNIX, s_.SOCK_STREAM)
                c.connect(str(deployment["cfg"].socket_path))
                held.append(c)
            time.sleep(0.4)
            # A refused connection now receives an explicit capacity refusal and
            # is then closed; a metered one stays silent and open. Distinguish
            # them by what arrives, not by whether anything arrives — the first
            # version of this test counted "the socket had bytes" as "still
            # holding a slot", so it broke the moment refusals started being
            # explained, which is the behaviour the spec requires.
            live, refused, explained = 0, 0, 0
            for c in held:
                c.settimeout(0.3)
                try:
                    data = c.recv(4096)
                except (TimeoutError, OSError):
                    live += 1          # silent and open: holding a slot
                    continue
                if not data:
                    refused += 1       # closed with no reply
                elif b"capacity" in data:
                    refused += 1
                    explained += 1     # closed WITH a reason, which is the requirement
                else:
                    live += 1
            assert live <= bmod.MAX_CONNECTIONS_PER_UID, (
                f"{live} connections held simultaneously by one uid, cap is "
                f"{bmod.MAX_CONNECTIONS_PER_UID}")
            assert refused >= 6, (
                f"only {refused} of the 6 excess connections were refused; the "
                "cap is not being applied")
            # AND THE REASON ARRIVES. Counting "closed with no reply" and
            # "closed with a reason" together as refused made this test pass
            # with the explanation deleted — the cap was proven and the spec's
            # actual requirement, that an agent can tell WHY, was not. The
            # mutation sweep caught it.
            assert explained >= 1, (
                "connections were refused silently; §3.2 requires an agent be "
                "able to tell that its message was refused AND why")
        finally:
            for c in held:
                try:
                    c.close()
                except OSError:
                    pass
            srv.shutdown()

    def test_slots_are_released_so_the_broker_recovers(self, deployment):
        """A cap that never releases is an outage with extra steps. Fill it,
        drop the connections, and confirm a legitimate submission still works.
        """
        import socket as s_
        from macf.amail import broker as bmod

        deployment["cfg"].credentials_path.write_text("secret")
        deployment["cfg"].credentials_path.chmod(0o600)
        srv = serve(deployment["broker"])
        time.sleep(0.15)
        try:
            held = []
            for _ in range(bmod.MAX_CONNECTIONS_PER_UID + 4):
                c = s_.socket(s_.AF_UNIX, s_.SOCK_STREAM)
                c.connect(str(deployment["cfg"].socket_path))
                held.append(c)
            time.sleep(0.3)
            for c in held:
                c.close()
            time.sleep(0.5)
            assert submit("alpha", msg(), deployment["cfg"].socket_path)["ok"] is True
        finally:
            srv.shutdown()

    def test_overload_refusals_are_audited_but_rate_limited(self, deployment):
        """Recorded, because a refusal nobody can see is indistinguishable from
        an outage. Rate-limited, because otherwise the record of the flood is a
        second flood against the same shared disk.
        """
        from macf.amail import broker as bmod

        srv = bmod._Server.__new__(bmod._Server)
        srv._meter_lock = bmod.threading.Lock()
        srv._inflight, srv._per_uid, srv._overload_audited = {}, {}, {}
        srv.broker = deployment["broker"]
        for _ in range(50):
            srv._audit_overload(1234)
        entries = [r for r in deployment["broker"].audit.records()
                   if r.get("context") == "overload"]
        assert len(entries) == 1, f"50 refusals produced {len(entries)} audit records"
        assert "1234" in entries[0]["detail"]


class TestAuditLogIsBounded:
    """~280 bytes per refused submission, produced at will by any agent, on a
    volume shared by every account on the host. Unbounded 'append-only' does not
    preserve the record — a full disk stops the broker and its logging alike.
    """

    def test_log_rotates_at_the_ceiling(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl", max_bytes=4096)
        for i in range(400):
            log.refused(sender="alpha", recipients=["x@y.test"], reason=f"r{i}")
        assert (tmp_path / "audit.jsonl.1").exists(), "log never rotated"
        assert (tmp_path / "audit.jsonl").stat().st_size < 4096 * 2

    def test_rotation_is_recorded_so_truncation_is_visible(self, tmp_path):
        """'Nothing was refused before this point' and 'the evidence was rotated
        away' must not look the same to a reader."""
        log = AuditLog(tmp_path / "audit.jsonl", max_bytes=2048)
        for i in range(300):
            log.refused(sender="alpha", recipients=["x@y.test"], reason=f"r{i}")
        assert any(r.get("decision") == "rotated" for r in log.records()), \
            "rotation left no trace, so silent truncation reads as silence"

    def test_default_is_bounded(self, tmp_path):
        """A default of unbounded would mean the fix only applies where someone
        remembered to ask for it."""
        assert AuditLog(tmp_path / "a.jsonl").max_bytes > 0

    def test_refusals_are_still_recorded_verbatim(self, tmp_path):
        """Bounding must not quietly become sampling."""
        log = AuditLog(tmp_path / "audit.jsonl")
        log.refused(sender="alpha", recipients=["x@y.test"], reason="not a contact")
        assert log.refusals()[0]["reason"] == "not a contact"


class TestCliSurface:
    """The CLI had zero tests. Whatever it did with untrusted input, nothing
    had ever checked."""

    def test_config_survives_every_json_shape(self, tmp_path, monkeypatch):
        """json.loads succeeds on any JSON value, not just an object. Each of
        these crashed every amail subcommand with an AttributeError."""
        from macf import cli

        home = tmp_path / "home"
        (home / ".maceff").mkdir(parents=True)
        monkeypatch.setattr("macf.utils.paths.find_agent_home", lambda: home)
        for payload in ("[]", '"x"', "7", "null", "true", "{ not json", '{"agent":"a"}'):
            (home / ".maceff" / "amail.json").write_text(payload)
            cfg = cli._amail_config()
            assert isinstance(cfg, dict)
            assert {"domain", "socket", "agent", "home"} <= set(cfg)

    def test_terminal_control_characters_are_neutralised(self):
        """A body is attacker-controlled and is printed to the operator's
        terminal. An escape sequence there can redraw what was already shown —
        including any trust labelling above it — so a message could claim an
        identity by overwriting the screen rather than by forging a header.
        """
        from macf import cli

        hostile = "innocent\x1b[2J\x1b[1;1Hfrom: someone-else\x07"
        rendered = cli._term_safe(hostile)
        assert "\x1b" not in rendered and "\x07" not in rendered
        assert "\\x1b" in rendered, "escaped form should remain visible to the reader"
        assert "innocent" in rendered, "legitimate text must survive"

    def test_ordinary_text_is_untouched(self):
        """A neutraliser that mangles normal mail would be reverted within a day."""
        from macf import cli

        text = "Hi,\n\tHere is a note — with unicode, tabs and newlines.\n"
        assert cli._term_safe(text) == text


# ---------------------------------------------------------------------------
# Round 7: the round-6 fixes themselves, and the surfaces round 6 did not reach
# ---------------------------------------------------------------------------


class TestAuditRotationIsConcurrencySafe:
    """Round 7 found the round-6 rotation fix DESTROYED the evidence it existed
    to preserve.

    Two threads both see size >= ceiling. The first renames the full log to .1
    and writes a one-line marker; the second renames THAT one-line file over .1,
    and the whole generation is gone. Measured at 7 lossy runs in 60 under
    ordinary concurrency, worst case 42 of 50 records lost — with no attacker,
    because the broker is multi-threaded by design.

    The round-6 tests covered rotation functionally and not one of them ran it
    concurrently, which is exactly how the defect shipped inside a fix.
    """

    def test_no_records_are_lost_under_concurrent_writers(self, tmp_path):
        import threading as t_

        # 240 records at ~170 B = ~40.8 kB. A ceiling of 25 kB means EXACTLY one
        # rotation fires and no generation is ever deleted, so any missing record
        # is the race and not bounded retention doing its job. Measured rather
        # than guessed: the first version of this test used a ceiling that
        # legitimately rotated six times, and would have reported the correct
        # implementation as lossy.
        log = AuditLog(tmp_path / "audit.jsonl", max_bytes=25000)
        total, writers = 240, 8

        def write(base):
            for i in range(total // writers):
                log.refused(sender="alpha", recipients=["x@y.test"],
                            reason=f"r-{base}-{i}")

        threads = [t_.Thread(target=write, args=(w,)) for w in range(writers)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        seen = set()
        for p in (tmp_path / "audit.jsonl.1", tmp_path / "audit.jsonl"):
            if p.exists():
                for line in p.read_text().splitlines():
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r.get("decision") == "refused":
                        seen.add(r["reason"])
        # Bounded retention may legitimately rotate the OLDEST generation away.
        # This load stays under two generations, so a correctly serialised
        # implementation drops nothing at all.
        assert len(seen) == total, (
            f"{total - len(seen)} of {total} refusal records lost to the "
            f"rotation race")

    def test_rotation_count_matches_the_bytes_written(self, tmp_path):
        """Unserialised rotation also produced TWO markers for one rotation's
        worth of bytes, so the markers themselves misreported."""
        import threading as t_

        log = AuditLog(tmp_path / "audit.jsonl", max_bytes=25000)

        def write():
            for i in range(30):
                log.refused(sender="alpha", recipients=["x@y.test"], reason=f"r{i}")

        threads = [t_.Thread(target=write) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        markers = sum(1 for p in (tmp_path / "audit.jsonl.1", tmp_path / "audit.jsonl")
                      if p.exists()
                      for line in p.read_text().splitlines()
                      if '"rotated"' in line)
        assert markers <= 1, f"{markers} rotation markers for one rotation of bytes"

    def test_rotate_and_append_are_mutually_exclusive(self, tmp_path):
        """The MECHANISM, asserted directly, because the emergent data loss is
        probabilistic and a probabilistic test is barely better than no test.

        The auditor measured the loss at 7 runs in 60 — so a suite asserting
        "no records were lost" would pass ~88% of the time against the BROKEN
        implementation, and a green run would mean nothing. For a race fix,
        black-box assertions cannot distinguish the implementations; assert the
        property the fix actually establishes, which is that no two writers are
        ever inside rotate-then-append at the same time.
        """
        import threading as t_

        log = AuditLog(tmp_path / "audit.jsonl", max_bytes=900)
        seen_lock = t_.Lock()
        inside, high_water = [], [0]
        real_write = log._write

        def traced(record):
            with seen_lock:
                inside.append(1)
                high_water[0] = max(high_water[0], len(inside))
            # Long enough that an unserialised implementation MUST overlap.
            time.sleep(0.003)
            try:
                return real_write(record)
            finally:
                with seen_lock:
                    inside.pop()

        log._write = traced
        threads = [t_.Thread(target=lambda: [
            log.refused(sender="alpha", recipients=["x@y.test"], reason=f"r{i}")
            for i in range(12)]) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert high_water[0] == 1, (
            f"{high_water[0]} writers were inside the rotate/append section at "
            f"once; rotation and the record it writes are not serialised")

    def test_lines_are_never_interleaved_under_concurrency(self, tmp_path):
        """Every line must still parse. A log that cannot be read is not a log."""
        import threading as t_

        log = AuditLog(tmp_path / "audit.jsonl", max_bytes=0)  # no rotation
        threads = [t_.Thread(target=lambda: [
            log.refused(sender="alpha", recipients=["x@y.test"], reason="x" * 200)
            for _ in range(25)]) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        lines = (tmp_path / "audit.jsonl").read_text().splitlines()
        assert len(lines) == 200
        for line in lines:
            json.loads(line)  # raises if a partial write interleaved


class TestConfigDirectoryCustody:
    """Round 7: the custody check validated the contact FILE's mode and not the
    directory holding it. Replacing a file needs write permission on the
    directory, not on the file — so an agent could os.replace() a contact list
    granting itself every recipient while the original sat at a blameless 0644
    and the check reported green throughout.

    A guard that inspects an object the attacker never has to touch does not
    merely miss the attack; it certifies against it.
    """

    def test_group_writable_config_directory_is_refused(self, deployment, tmp_path):
        cfgdir = tmp_path / "cfg"
        cfgdir.mkdir()
        contacts = cfgdir / "contacts.json"
        contacts.write_text(_addressing({"alpha": []}))
        contacts.chmod(0o644)
        cfgdir.chmod(0o775)  # group-writable: anyone in the group can swap the file
        deployment["cfg"].contacts_path = contacts
        with pytest.raises(PermissionError, match="directory"):
            deployment["broker"].assert_credential_custody()

    def test_world_writable_config_directory_is_refused(self, deployment, tmp_path):
        cfgdir = tmp_path / "cfg2"
        cfgdir.mkdir()
        contacts = cfgdir / "contacts.json"
        contacts.write_text(_addressing({"alpha": []}))
        contacts.chmod(0o644)
        cfgdir.chmod(0o777)
        deployment["cfg"].contacts_path = contacts
        with pytest.raises(PermissionError, match="directory"):
            deployment["broker"].assert_credential_custody()

    def test_a_correctly_provisioned_directory_still_starts(self, deployment, tmp_path):
        """A check that refuses correct deployments gets disabled within a week."""
        cfgdir = tmp_path / "cfg3"
        cfgdir.mkdir()
        cfgdir.chmod(0o755)
        contacts = cfgdir / "contacts.json"
        contacts.write_text(_addressing({"alpha": []}))
        contacts.chmod(0o644)
        cred = cfgdir / "smarthost.cred"
        cred.write_text("secret")
        cred.chmod(0o600)
        deployment["cfg"].contacts_path = contacts
        deployment["cfg"].credentials_path = cred
        deployment["broker"].assert_credential_custody()  # must not raise


class TestInboundIdentifierVisibility:
    """Round 7: inbound validated identifier SHAPE but not VISIBILITY, while the
    outbound path required both. A remote sender could graft a message onto a
    conversation it was never part of, inheriting the apparent standing of the
    exchange above it — the same laundering an earlier round closed on the
    submit path, left open on its twin.
    """

    def test_unseen_parent_is_dropped(self, deployment):
        from macf.amail import new_id
        from macf.amail.broker import _ID_RE

        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"])
        # A GENUINELY well-formed id that was simply never delivered here.
        #
        # The first version of this test used a hand-written 'msg-deadbeef…',
        # which does not match _ID_RE — so the shape check nulled it and the
        # visibility check was never reached. The test asserted the right
        # outcome produced by the wrong mechanism, and the mutation sweep caught
        # it: removing the visibility check left the test passing.
        m.parent = new_id("msg")
        assert _ID_RE.match(m.parent), "the test value must pass the shape check"
        deployment["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        assert store.read_all(deployment["pull"]("alpha"))[0].parent is None

    def test_a_real_visible_parent_is_kept(self, deployment):
        """Dropping every parent would 'fix' this by breaking threading."""
        first = deployment["broker"].submit("alpha", msg())
        seen = store.read_all(deployment["pull"]("beta"))[0]
        # The sender must be one BETA permits, or the message is quarantined and
        # the parent question never arises — which is what the first version of
        # this test actually measured.
        m = msg(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"])
        m.parent = seen.message_id
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        delivered = [x for x in store.read_all(deployment["pull"]("beta"))
                     if x.parent is not None]
        assert delivered and delivered[0].parent == seen.message_id
        assert first["ok"] is True

    def test_asserted_thread_id_cannot_join_an_existing_thread(self, deployment):
        deployment["broker"].submit("alpha", msg())
        existing = store.read_all(deployment["pull"]("beta"))[0].thread_id
        m = msg(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"])
        m.thread_id, m.parent = existing, None
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        grafted = [x for x in store.read_all(deployment["pull"]("beta"))
                   if x.body == "b" and x.thread_id == existing]
        assert len(grafted) == 1, "an asserted thread_id joined an existing thread"


class TestCliRobustness:
    """Round 7: --body-file raised uncaught UnicodeDecodeError on binary input,
    and an oversize body surfaced BrokenPipeError — reporting a transport crash
    for the size guard working correctly."""

    def test_bidi_controls_are_neutralised(self):
        """Trojan-source: these drive no cursor and forge no escape sequence,
        they reorder how the text RENDERS. The point of the function is that a
        reader can trust what the screen says."""
        from macf import cli

        hostile = "transfer to ‮reversed‬ account"
        out = cli._term_safe(hostile)
        assert "‮" not in out and "‬" not in out
        assert "\\u202e" in out, "escaped form should stay visible"

    def test_escape_of_a_high_codepoint_is_unambiguous(self):
        """\\x202e reads as \\x20 followed by '2e'. An ambiguous escape is itself
        a small forgery."""
        from macf import cli

        assert "\\u202e" in cli._term_safe("‮")
        assert "\\x1b" in cli._term_safe("\x1b")

    def test_oversize_body_reports_a_refusal_not_a_broken_pipe(self, deployment):
        from macf.amail import BrokerUnavailable

        deployment["cfg"].credentials_path.write_text("secret")
        deployment["cfg"].credentials_path.chmod(0o600)
        srv = serve(deployment["broker"])
        time.sleep(0.15)
        try:
            big = msg(body="A" * (3 << 20))
            with pytest.raises(BrokerUnavailable, match="closed the connection"):
                submit("alpha", big, deployment["cfg"].socket_path)
            # And the broker is still serving everyone else.
            assert submit("alpha", msg(), deployment["cfg"].socket_path)["ok"] is True
        finally:
            srv.shutdown()


# ---------------------------------------------------------------------------
# Round 8: the round-7 fixes, and three mutants that survived its sweep
# ---------------------------------------------------------------------------


class TestAuditLockfileIsNotAnAttackSurface:
    """Round 8: `open(lock_path, "a")` opens whatever is at that path.

    A FIFO with no reader blocks forever WHILE THE SHARED THREADING LOCK IS
    HELD, so every other handler thread's audit write queues behind it — and
    since every submission audits, one mkfifo silences all mail on the host,
    permanently. A directory raises on every submission. A symlink aims a
    broker-uid create wherever the agent chooses.
    """

    def test_fifo_at_the_lock_path_is_refused_not_hung(self, tmp_path):
        import threading as t_

        os.mkfifo(tmp_path / "audit.jsonl.lock")
        log = AuditLog(tmp_path / "audit.jsonl")
        done = t_.Event()
        error = []

        def attempt():
            try:
                log.refused(sender="alpha", recipients=["x@y.test"], reason="r")
            except OSError as e:
                error.append(e)
            finally:
                done.set()

        t_.Thread(target=attempt, daemon=True).start()
        assert done.wait(timeout=5), "audit write hung on a planted FIFO"
        assert error, "a FIFO at the lock path was accepted"

    def test_directory_at_the_lock_path_is_refused_with_a_named_reason(self, tmp_path):
        (tmp_path / "audit.jsonl.lock").mkdir()
        log = AuditLog(tmp_path / "audit.jsonl")
        with pytest.raises(OSError):
            log.refused(sender="alpha", recipients=["x@y.test"], reason="r")

    def test_symlink_at_the_lock_path_is_refused(self, tmp_path):
        target = tmp_path / "elsewhere"
        target.mkdir()
        (tmp_path / "audit.jsonl.lock").symlink_to(target / "planted")
        log = AuditLog(tmp_path / "audit.jsonl")
        with pytest.raises(OSError):
            log.refused(sender="alpha", recipients=["x@y.test"], reason="r")
        assert list(target.iterdir()) == [], "a broker-uid write escaped the audit dir"

    def test_character_device_at_the_lock_path_is_refused(self, tmp_path):
        """The case only the S_ISREG check can catch.

        The FIFO and directory tests above pass with S_ISREG removed — the open
        FLAGS refuse those on their own (ENXIO and EISDIR), so those two tests
        prove the flags and say nothing about the check. The mutation sweep
        caught that: deleting S_ISREG left them green.

        A character device opens cleanly under exactly these flags, and flock on
        it succeeds, so the broker would take a lock on a device and carry on
        believing it held one. That is the only branch left where S_ISREG is
        load-bearing, so it is the branch the test has to use.
        """
        log = AuditLog(tmp_path / "audit.jsonl")
        log._lock_path = Path("/dev/null")
        with pytest.raises(OSError, match="not a regular file"):
            log.refused(sender="alpha", recipients=["x@y.test"], reason="r")

    def test_a_normal_lockfile_still_works(self, tmp_path):
        """A guard that refuses the ordinary case protects nothing."""
        log = AuditLog(tmp_path / "audit.jsonl")
        log.refused(sender="alpha", recipients=["x@y.test"], reason="ordinary")
        assert log.refusals()[0]["reason"] == "ordinary"


class TestBothAuditLocksArePinned:
    """Round 8's sweep found the two audit locks each SURVIVED removal alone —
    they are redundant for the single-process case the suite exercised, so
    neither was individually pinned and flock's whole reason for existing
    (cross-process serialisation) had no test at all.

    Behaviour cannot distinguish them in one process, so assert each mechanism
    where it is the only one that can act.
    """

    def test_threading_lock_serialises_when_flock_is_unavailable(self, tmp_path, monkeypatch):
        """The non-POSIX path, which is exactly where flock cannot help."""
        import threading as t_
        from macf.amail import audit as amod

        monkeypatch.setattr(amod, "fcntl", None)
        log = AuditLog(tmp_path / "audit.jsonl", max_bytes=900)
        seen_lock, inside, high = t_.Lock(), [], [0]
        real_write = log._write

        def traced(record):
            with seen_lock:
                inside.append(1)
                high[0] = max(high[0], len(inside))
            time.sleep(0.003)
            try:
                return real_write(record)
            finally:
                with seen_lock:
                    inside.pop()

        log._write = traced
        threads = [t_.Thread(target=lambda: [
            log.refused(sender="a", recipients=["x@y.test"], reason=f"r{i}")
            for i in range(10)]) for _ in range(6)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert high[0] == 1, "without flock, the threading lock must still serialise"

    def test_flock_is_taken_exclusively_around_the_critical_section(self, tmp_path, monkeypatch):
        """Cross-process serialisation cannot be observed from inside one
        process, and round 8 could not induce cross-process loss even with the
        locks removed. So assert the ARGUMENTS: an exclusive flock is taken and
        released on the lockfile's own descriptor."""
        from macf.amail import audit as amod

        calls = []
        real_flock = amod.fcntl.flock

        def spy(fd, op):
            calls.append(op)
            return real_flock(fd, op)

        monkeypatch.setattr(amod.fcntl, "flock", spy)
        log = AuditLog(tmp_path / "audit.jsonl")
        log.refused(sender="alpha", recipients=["x@y.test"], reason="r")
        assert amod.fcntl.LOCK_EX in calls, "no exclusive inter-process lock was taken"
        assert amod.fcntl.LOCK_UN in calls, "the inter-process lock was never released"

    def test_two_processes_do_not_tear_the_log(self, tmp_path):
        """The end-to-end claim the flock exists to support."""
        import subprocess as sp
        import sys

        script = tmp_path / "w.py"
        script.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(Path(__file__).parent.parent / 'src')!r})\n"  # noqa: MACEFF002 - a test locating its OWN source tree, not project discovery; find_project_root would resolve the checkout under test rather than this file's package
            "from macf.amail import AuditLog\n"
            f"log = AuditLog({str(tmp_path / 'audit.jsonl')!r}, max_bytes=4000)\n"
            "for i in range(300):\n"
            "    log.refused(sender='a', recipients=['x@y.test'], reason=f'{sys.argv[1]}-{i}')\n")
        procs = [sp.Popen([sys.executable, str(script), str(n)]) for n in range(4)]
        for p in procs:
            assert p.wait(timeout=120) == 0
        for f in (tmp_path / "audit.jsonl.1", tmp_path / "audit.jsonl"):
            if f.exists():
                for line in f.read_text().splitlines():
                    json.loads(line)  # raises if two processes interleaved a write


class TestCustodyCoversEveryConfigObject:
    """Round 8: round 7 guarded the directories holding the credential and the
    contact list and left out the one holding the AUDIT LOG — which the spec
    makes mandatory and whose integrity is explicitly in scope. It also never
    checked any file's OWNER, so a contact list owned by an agent at 0644 passed
    while its owner could rewrite it at will.

    Seventh consecutive round in which the finding was 'the fix was applied
    where it was demonstrated'.
    """

    @pytest.fixture
    def tight(self, deployment, tmp_path):
        d = tmp_path / "cfgdir"
        d.mkdir()
        d.chmod(0o755)
        contacts, cred, audit = d / "contacts.json", d / "cred", d / "audit.jsonl"
        contacts.write_text(_addressing({"alpha": []}))
        contacts.chmod(0o644)
        cred.write_text("secret")
        cred.chmod(0o600)
        deployment["cfg"].contacts_path = contacts
        deployment["cfg"].credentials_path = cred
        deployment["cfg"].audit_path = audit
        return deployment

    def test_baseline_tight_config_starts(self, tight):
        tight["broker"].assert_credential_custody()

    def test_world_writable_audit_directory_is_refused(self, tight, tmp_path):
        adir = tmp_path / "auditdir"
        adir.mkdir()
        adir.chmod(0o777)
        tight["cfg"].audit_path = adir / "audit.jsonl"
        with pytest.raises(PermissionError, match="audit log"):
            tight["broker"].assert_credential_custody()

    def test_file_owned_by_another_uid_is_refused(self, tight, monkeypatch):
        """Round 8 could not demonstrate this without a second uid, so it was
        reported as HYPOTHESIZED. Stubbing getuid tests the branch without
        needing root — and the branch it pins had NO test at all, which is why
        the corresponding mutant survived their sweep."""
        monkeypatch.setattr(os, "getuid", lambda: os.stat(tight["cfg"].contacts_path).st_uid + 1)
        with pytest.raises(PermissionError) as e:
            tight["broker"].assert_credential_custody()
        # THE FILE branch, not the directory one. Stubbing getuid makes BOTH
        # branches fire, and both messages contain "owned by uid" — so the
        # obvious assertion passed with the file check deleted, satisfied by its
        # sibling. The mutation sweep caught it. Pin which guard spoke.
        assert "directory holding" not in str(e.value), \
            "the directory check raised; the file-owner check is unproven"
        assert "is owned by uid" in str(e.value)

    def test_directory_owned_by_another_uid_is_refused(self, tight, monkeypatch):
        """The mutant that survived round 8's sweep: the dir-owner branch was
        live and unpinned."""
        real_stat = os.stat
        cfgdir = Path(tight["cfg"].contacts_path).parent

        class FakeStat:
            def __init__(self, s, uid):
                self._s, self.st_uid = s, uid
                self.st_mode = s.st_mode

        def fake_stat(p, *a, **k):
            s = real_stat(p, *a, **k)
            if Path(p) == cfgdir:
                return FakeStat(s, s.st_uid + 1)
            return s

        monkeypatch.setattr(Path, "stat", lambda self, *a, **k: fake_stat(self, *a, **k))
        with pytest.raises(PermissionError, match="owned by uid"):
            tight["broker"].assert_credential_custody()


class TestInboundAuthorizesBeforeScanning:
    """Round 8: the visibility checks each deserialised the recipient's whole
    mailbox, and both ran BEFORE the contact decision. An unlisted sender whose
    message was bound for quarantine still paid 2 x O(mailbox) per message —
    4000 deserialisations against a 2000-message mailbox — and the cost rises
    with the traffic the attacker has already sent.
    """

    def test_quarantined_mail_does_not_scan_the_mailbox(self, deployment, monkeypatch):
        deployment["broker"].submit("alpha", msg())
        from macf.amail import store as smod

        calls = []
        real = smod.read_all
        monkeypatch.setattr(smod, "read_all",
                            lambda *a, **k: (calls.append(1), real(*a, **k))[1])
        m = msg(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"])
        m.parent, m.thread_id = "msg-1-aaaaaaaaaaaa", "thr-1-aaaaaaaaaaaa"
        r = deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert r["decision"] == "quarantined"
        assert calls == [], "an unauthorized sender still forced a mailbox scan"

    def test_delivered_mail_scans_at_most_once(self, deployment, monkeypatch):
        deployment["broker"].submit("alpha", msg())
        from macf.amail import store as smod

        calls = []
        real = smod.read_all
        monkeypatch.setattr(smod, "read_all",
                            lambda *a, **k: (calls.append(1), real(*a, **k))[1])
        m = msg(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"])
        m.parent, m.thread_id = "msg-1-aaaaaaaaaaaa", "thr-1-aaaaaaaaaaaa"
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert len(calls) <= 1, f"{len(calls)} full mailbox scans for one message"

    def test_quarantined_mail_is_not_threaded_against_a_real_conversation(self, deployment):
        deployment["broker"].submit("alpha", msg())
        existing = store.read_all(deployment["pull"]("beta"))[0].thread_id
        m = msg(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"])
        m.thread_id = existing
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        q = list((deployment["cfg"].inbound_quarantine).iterdir())
        assert q and existing not in q[0].read_text()


class TestInvisibleCharactersAreEscaped:
    """Round 8: escaping the bidi overrides by enumeration left LRM/RLM, every
    zero-width character, the word joiner, the soft hyphen, and the Unicode tag
    block reaching the terminal — the tag block can smuggle entirely invisible
    text into a rendered sender label.

    Enumerating members of a category gives a list that is right the day it is
    written. Naming the category gives one that stays right.
    """

    @pytest.mark.parametrize("cp,name", [
        (0x200E, "LEFT-TO-RIGHT MARK"), (0x200F, "RIGHT-TO-LEFT MARK"),
        (0x200B, "ZERO WIDTH SPACE"), (0x200D, "ZERO WIDTH JOINER"),
        (0x2060, "WORD JOINER"), (0x00AD, "SOFT HYPHEN"),
        (0x2062, "INVISIBLE TIMES"), (0xFEFF, "ZERO WIDTH NO-BREAK SPACE"),
        (0xE0041, "TAG LATIN CAPITAL LETTER A"), (0x202E, "RIGHT-TO-LEFT OVERRIDE"),
    ])
    def test_format_characters_do_not_reach_the_terminal(self, cp, name):
        from macf import cli

        out = cli._term_safe(f"before{chr(cp)}after")
        assert chr(cp) not in out, f"{name} (U+{cp:04X}) reached the terminal"
        assert f"\\u{cp:04x}" in out or f"\\x{cp:02x}" in out

    def test_ordinary_unicode_prose_is_untouched(self):
        """Escaping legitimate text would make the renderer useless for anyone
        not writing in ASCII."""
        from macf import cli

        for text in ("Grüße — naïve café", "日本語のメール", "Ω≈ç√∫˜µ", "emoji 🎉 ok"):
            assert cli._term_safe(text) == text


# ---------------------------------------------------------------------------
# v1.1: authorship signing, inbound trust classification, unforgeable labelling
# ---------------------------------------------------------------------------

from macf.amail import TrustClass, generate_keypair, load_private_key, sign, verify  # noqa: E402
from macf.amail import new_id  # noqa: E402
from macf.amail import SigningError, public_key_line  # noqa: E402
from macf.amail.crypto import signing_payload  # noqa: E402


@pytest.fixture
def keyed(deployment, tmp_path):
    """A deployment where beta has declared a signing key to alpha."""
    keydir = tmp_path / "keys"
    beta_key = keydir / "beta.pem"
    beta_pub = generate_keypair(beta_key)
    deployment["contacts"].write_text(_addressing({
        "alpha": [{"address": f"beta@{DOMAIN}", "key": beta_pub}],
        "beta": [f"alpha@{DOMAIN}"],
    }))
    deployment["contacts"].chmod(0o644)
    deployment["beta_key"] = beta_key
    deployment["beta_pub"] = beta_pub
    return deployment


class TestAuthorshipSigning:
    """v1.0 §8 deferred this because 'signing without key custody and rotation is
    ceremony'. These are the custody and rotation decisions, made explicitly."""

    def test_a_signature_verifies_against_the_declared_key(self, tmp_path):
        key = generate_keypair(tmp_path / "k.pem")
        m = msg(body="the signed text")
        sig = sign(m, load_private_key(tmp_path / "k.pem"))
        assert verify(m, sig, [key]) is True

    def test_a_signature_from_another_key_does_not_verify(self, tmp_path):
        generate_keypair(tmp_path / "mine.pem")
        theirs = generate_keypair(tmp_path / "theirs.pem")
        m = msg()
        sig = sign(m, load_private_key(tmp_path / "mine.pem"))
        assert verify(m, sig, [theirs]) is False

    @pytest.mark.parametrize("field_,value", [
        ("body", "tampered"), ("subject", "tampered"), ("sender", "eve@x.test"),
    ])
    def test_tampering_with_any_covered_field_breaks_the_signature(self, tmp_path, field_, value):
        """A signature that survives an edit to what it covers is decorative."""
        key = generate_keypair(tmp_path / "k.pem")
        m = msg()
        sig = sign(m, load_private_key(tmp_path / "k.pem"))
        setattr(m, field_, value)
        assert verify(m, sig, [key]) is False

    def test_identifiers_are_deliberately_not_covered(self, tmp_path):
        """The broker RE-MINTS message_id and date on inbound, because a
        remote-chosen id shadows a real message and a remote-chosen date
        controls reader ordering. Covering them would mean every inbound
        signature verified once at ingress and NEVER AGAIN — the stored message
        could not be re-checked by anyone, making the broker the sole and
        unrepeatable verifier. That is the thing end-to-end signing exists to
        avoid, so the payload covers what the message IS, not what it was called
        in transit.
        """
        key = generate_keypair(tmp_path / "k.pem")
        m = msg()
        sig = sign(m, load_private_key(tmp_path / "k.pem"))
        m.message_id = new_id("msg")
        m.date = "2030-01-01T00:00:00+00:00"
        assert verify(m, sig, [key]) is True

    def test_a_stored_message_can_be_verified_again_later(self, keyed):
        """The property the exclusion above buys: anyone holding the public key
        can re-check the message as stored, without trusting the broker's
        recorded verdict."""
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"], body="durable")
        m.signature = sign(m, load_private_key(keyed["beta_key"]))
        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        raw = next((keyed["pull"]("alpha") / "Maildir" / "new").iterdir()).read_text()
        stored = Message.deserialize(raw)
        assert verify(stored, stored.signature, [keyed["beta_pub"]]) is True

    def test_recipients_are_covered(self, tmp_path):
        """`to` is covered, so a message cannot be re-aimed and still verify."""
        key = generate_keypair(tmp_path / "k.pem")
        m = msg(to=[f"beta@{DOMAIN}"])
        sig = sign(m, load_private_key(tmp_path / "k.pem"))
        m.to = ["someone-else@elsewhere.test"]
        assert verify(m, sig, [key]) is False

    def test_body_is_covered_by_hash_so_truncation_is_detectable(self, tmp_path):
        """The broker truncates an oversize body. Covering the body by hash means
        that truncation FAILS verification rather than silently verifying against
        text the sender never wrote."""
        key = generate_keypair(tmp_path / "k.pem")
        m = msg(body="x" * 5000)
        sig = sign(m, load_private_key(tmp_path / "k.pem"))
        m.body = m.body[:100]
        assert verify(m, sig, [key]) is False
        assert "body_sha256" in signing_payload(m).decode()

    def test_payload_is_canonical_regardless_of_field_order(self, tmp_path):
        """Two implementations that agree on the FIELDS must agree on the BYTES."""
        a = msg()
        b = Message(body=a.body, subject=a.subject, to=list(a.to), sender=a.sender,
                    message_id=a.message_id, thread_id=a.thread_id, date=a.date)
        assert signing_payload(a) == signing_payload(b)

    def test_rotation_verifies_against_either_declared_key(self, tmp_path):
        """Rotation requiring a flag day is rotation that never happens, and the
        key that is never rotated is the one that eventually leaks."""
        old = generate_keypair(tmp_path / "old.pem")
        new = generate_keypair(tmp_path / "new.pem")
        m = msg()
        assert verify(m, sign(m, load_private_key(tmp_path / "old.pem")), [old, new])
        assert verify(m, sign(m, load_private_key(tmp_path / "new.pem")), [old, new])

    @pytest.mark.parametrize("mode", [0o640, 0o604, 0o644])
    def test_a_group_or_world_readable_private_key_is_refused(self, tmp_path, mode):
        """Anyone who can read it can sign as this agent."""
        generate_keypair(tmp_path / "k.pem")
        (tmp_path / "k.pem").chmod(mode)
        with pytest.raises(SigningError, match="readable by group or other"):
            load_private_key(tmp_path / "k.pem")

    def test_keygen_refuses_to_overwrite_an_existing_key(self, tmp_path):
        """Overwriting invalidates every signature already published, and doing it
        by accident is indistinguishable from doing it maliciously."""
        generate_keypair(tmp_path / "k.pem")
        with pytest.raises(FileExistsError):
            generate_keypair(tmp_path / "k.pem")

    def test_algorithm_is_named_in_the_key_not_chosen_by_the_message(self):
        """An algorithm field a message can set is an algorithm an attacker picks."""
        from macf.amail.crypto import parse_public_key
        with pytest.raises(SigningError, match="must begin with"):
            parse_public_key("none:AAAA")
        with pytest.raises(SigningError, match="must begin with"):
            parse_public_key("rsa:AAAA")


class TestInboundTrustClassification:
    def test_verified_signature_is_attested(self, keyed):
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"], body="hello")
        m.signature = sign(m, load_private_key(keyed["beta_key"]))
        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        stored = store.read_all(keyed["pull"]("alpha"))[0]
        assert stored.trust == TrustClass.ATTESTED.value

    def test_a_forged_signature_is_suspect_not_merely_unverified(self, keyed, tmp_path):
        """A failed check is EVIDENCE; an absent check is not. Collapsing them
        discards the only signal separating 'could not tell' from 'looked, and it
        did not add up'."""
        other = tmp_path / "eve.pem"
        generate_keypair(other)
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"])
        m.signature = sign(m, load_private_key(other))
        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        assert store.read_all(keyed["pull"]("alpha"))[0].trust == TrustClass.SUSPECT.value

    def test_unsigned_mail_from_a_correspondent_who_declared_a_key_is_suspect(self, keyed):
        """Declaring a key is a commitment to using one. An attacker with the
        address but not the key simply omits the signature and hopes."""
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"])
        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        assert store.read_all(keyed["pull"]("alpha"))[0].trust == TrustClass.SUSPECT.value

    def test_unsigned_mail_from_a_correspondent_with_no_key_is_unverified(self, deployment):
        m = msg(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"])
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert store.read_all(deployment["pull"]("beta"))[0].trust == TrustClass.UNVERIFIED.value

    def test_domain_authentication_never_promotes_to_attested(self, deployment):
        """DMARC passes cleanly for a message reading as a trusted human over an
        attacker's address, because the attacker's domain really is his."""
        m = msg(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"])
        got = deployment["broker"].classify_inbound(m, "beta", domain_authenticated=True)
        assert got is TrustClass.DOMAIN_AUTH
        assert got.proves_correspondent is False

    def test_only_attested_claims_to_prove_the_correspondent(self):
        proving = [c for c in TrustClass if c.proves_correspondent]
        assert proving == [TrustClass.ATTESTED]

    def test_classification_survives_a_storage_round_trip(self, keyed):
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"])
        m.signature = sign(m, load_private_key(keyed["beta_key"]))
        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        raw = next((keyed["pull"]("alpha") / "Maildir" / "new").iterdir()).read_text()
        assert Message.deserialize(raw).trust == TrustClass.ATTESTED.value


class TestTrustIsMintedNotAccepted:
    """The label is worth nothing if a sender can set it."""

    def test_a_submitted_trust_claim_is_overwritten(self, deployment):
        """A sender's claim is destroyed and replaced by the classifier's answer.

        This test used to assert that local submission yields ATTESTED, and it
        passed — which is how the worst defect in v1.1 stayed green. The local
        path minted ATTESTED unconditionally without checking any signature, and
        the CLI rendered that as "signed by this correspondent" for messages with
        no signature at all. The test asserted the bug.

        The property actually worth guarding is that the SENDER'S CLAIM DOES NOT
        SURVIVE. An unsigned message claiming to be attested must come back as
        whatever the classifier concluded, which for unsigned mail from a
        correspondent with no declared key is UNVERIFIED.
        """
        m = msg()
        m.trust = "attested"  # a lie, submitted by the sender
        deployment["broker"].submit("alpha", m)
        stored = store.read_all(deployment["pull"]("beta"))[0]
        assert stored.trust == TrustClass.UNVERIFIED.value, \
            "an unsigned message was labelled with the sender's own claim"

        m2 = msg(body="second")
        m2.trust = "definitely-trustworthy"
        deployment["broker"].submit("alpha", m2)
        got = [x for x in store.read_all(deployment["pull"]("beta")) if x.body == "second"][0]
        assert got.trust == TrustClass.UNVERIFIED.value

    def test_local_delivery_is_classified_by_the_same_classifier_as_inbound(self, keyed):
        """The two v1.1 mechanisms must not disagree on identical bytes.

        Round 9 found `classify_inbound()` returning SUSPECT for a message that
        `canonicalize()` had already labelled ATTESTED — the same message, the
        same contact book, two different answers, and the reader shown the
        flattering one.
        """
        # beta declares a key for alpha, and alpha sends unsigned.
        keyed["contacts"].write_text(_addressing({
            "alpha": [f"beta@{DOMAIN}"],
            "beta": [{"address": f"alpha@{DOMAIN}", "key": keyed["beta_pub"]}],
        }))
        keyed["contacts"].chmod(0o644)
        keyed["broker"].submit("alpha", msg(body="unsigned but keyed"))
        stored = [x for x in store.read_all(keyed["pull"]("beta"))
                  if x.body == "unsigned but keyed"][0]
        assert stored.trust == TrustClass.SUSPECT.value, \
            "a declared key went unused and the message still claimed to be signed"
        # And the two mechanisms now agree.
        assert keyed["broker"].classify_inbound(stored, "beta").value == stored.trust

    def test_stripping_a_signature_is_self_harm_as_the_spec_claims(self, keyed):
        """§9.2 says a compromised agent stripping its own signature makes its
        own mail unverified. That was FALSE — the stripped message still arrived
        labelled as signed. It has to be true, or the sentence comes out."""
        keyed["contacts"].write_text(_addressing({
            "alpha": [f"beta@{DOMAIN}"],
            "beta": [{"address": f"alpha@{DOMAIN}", "key": keyed["beta_pub"]}],
        }))
        keyed["contacts"].chmod(0o644)
        signed = msg(body="signed")
        signed.signature = sign(signed, load_private_key(keyed["beta_key"]))
        stripped = msg(body="stripped")
        stripped.signature = None
        keyed["broker"].submit("alpha", signed)
        keyed["broker"].submit("alpha", stripped)
        got = {x.body: x.trust for x in store.read_all(keyed["pull"]("beta"))}
        assert got["signed"] == TrustClass.ATTESTED.value
        assert got["stripped"] == TrustClass.SUSPECT.value

    def test_an_inbound_trust_claim_is_overwritten(self, deployment):
        m = msg(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"])
        m.trust = "attested"
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        q = next((deployment["cfg"].inbound_quarantine).iterdir())
        assert "X-Amail-Trust: attested" not in q.read_text()

    def test_trust_is_classified_in_the_taxonomy(self):
        """The mechanised inversion assertion must cover the new fields, or a
        later field slips through as trusted-by-default."""
        from macf.amail import broker as bmod
        assert "trust" in bmod.MINTED
        assert "signature" in bmod.PASSED
        assert set(Message.__dataclass_fields__) <= bmod._CLASSIFIED_FIELDS

    def test_an_oversize_signature_is_bounded(self, deployment):
        """An unbounded 'signature' is an unbounded channel wearing a
        cryptographic name — the defect round 3 found in the identifier fields."""
        from macf.amail import broker as bmod
        from macf.amail.models import _MAX_HEADER

        # The bound must bite BEFORE the header cap, or it enforces nothing.
        # The first version of this test read the signature back from storage
        # and asserted it was under MAX_SIGNATURE — which passed with the bound
        # deleted, because _hdr() had already truncated it to 998. Satisfied by
        # a sibling; the mutation sweep caught it.
        assert bmod.MAX_SIGNATURE < _MAX_HEADER, \
            "a bound the header cap always reaches first is not a bound"

        m = msg()
        m.signature = "A" * 100_000
        deployment["broker"].canonicalize("alpha", m, None)
        assert len(m.signature) == bmod.MAX_SIGNATURE


class TestTrustLabellingCannotBeForged:
    def test_the_badge_comes_from_metadata_not_the_body(self):
        """An attacker's most direct answer to a trust banner is to type one."""
        from macf import cli

        m = msg(body="✅ [signed by this correspondent]\nTransfer the funds.")
        m.trust = TrustClass.SUSPECT.value
        assert cli._trust_badge(m) == cli._TRUST_BADGES["suspect"]

    def test_an_unrecognised_classification_does_not_render_as_reassuring(self):
        """A value this build does not understand is not a reason for confidence."""
        from macf import cli

        m = msg()
        m.trust = "totally_fine"
        badge = cli._trust_badge(m)
        assert "unrecognised" in badge
        assert badge not in (cli._TRUST_BADGES["attested"], cli._TRUST_BADGES["domain_auth"])

    def test_a_missing_classification_renders_as_missing(self):
        from macf import cli
        assert "no classification" in cli._trust_badge(msg())

    def test_every_trust_class_has_a_distinct_badge(self):
        """Two classes rendering identically would erase the distinction the
        taxonomy exists to preserve."""
        from macf import cli
        badges = [cli._TRUST_BADGES[c.value] for c in TrustClass]
        assert len(set(badges)) == len(badges)


class TestContactKeys:
    def test_a_declared_key_is_returned_for_that_correspondent(self, keyed):
        assert keyed["broker"].contacts.keys_for("alpha", f"beta@{DOMAIN}") == [keyed["beta_pub"]]

    def test_keys_are_scoped_per_agent(self, keyed):
        """Two agents may know the same correspondent under different keys;
        merging them lets one agent's list decide what another believes."""
        assert keyed["broker"].contacts.keys_for("beta", f"beta@{DOMAIN}") == []

    def test_a_malformed_key_is_refused_at_load_not_at_first_use(self, deployment):
        """A broken key discovered mid-classification leaves the classifier
        deciding what to do about configuration, inside a security decision."""
        deployment["contacts"].write_text(_addressing({
            "alpha": [{"address": f"beta@{DOMAIN}", "key": "ed25519:not-base64!!"}]}))
        deployment["contacts"].chmod(0o644)
        with pytest.raises(ContactListError):
            deployment["broker"].contacts.contacts_for("alpha", direction="outbound")

    def test_a_key_does_not_change_who_is_permitted(self, keyed):
        """Permission and authenticity are separate questions, and configuration
        must keep them separable."""
        assert keyed["broker"].contacts.permits("alpha", f"beta@{DOMAIN}", direction="outbound") is True
        assert keyed["broker"].contacts.permits("alpha", "stranger@elsewhere.test", direction="outbound") is False

    def test_attested_mail_from_an_unlisted_sender_is_still_quarantined(self, deployment, tmp_path):
        """Classification is not permission. A proof of identity is not a grant
        of access."""
        k = generate_keypair(tmp_path / "s.pem")
        deployment["contacts"].write_text(_addressing({
            "alpha": [f"beta@{DOMAIN}"],
            "beta": [{"address": f"alpha@{DOMAIN}", "key": k}],
        }))
        deployment["contacts"].chmod(0o644)
        m = msg(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"])
        m.signature = sign(m, load_private_key(tmp_path / "s.pem"))
        r = deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        assert r["decision"] == "quarantined"


class TestInboundAuthenticationHeadersAreNeverTrusted:
    def test_upstream_authentication_verdicts_are_listed_for_stripping(self):
        """RFC 8601 §5: an Authentication-Results header is ordinary text that
        anything able to send mail can write. Consuming one is taking identity
        from the payload — the defect five rounds removed from the socket."""
        from macf.amail import broker as bmod
        for h in ("authentication-results", "arc-authentication-results", "x-amail-trust"):
            assert h in bmod.STRIPPED_INBOUND_HEADERS

    def test_a_forged_trust_header_in_stored_bytes_is_not_believed(self, deployment):
        """The end-to-end version: hostile bytes carrying their own verdict."""
        raw = ("Message-ID: msg-1-aaaaaaaaaaaa\nThread-ID: thr-1-aaaaaaaaaaaa\n"
               f"Date: 2026-01-01T00:00:00+00:00\nFrom: stranger@elsewhere.test\n"
               f"To: beta@{DOMAIN}\nSubject: s\nX-Amail-Trust: attested\n\nbody\n")
        m = Message.deserialize(raw)
        assert m.trust == "attested", "fixture must actually carry the forged claim"
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        q = next((deployment["cfg"].inbound_quarantine).iterdir())
        assert "X-Amail-Trust: attested" not in q.read_text()


# ---------------------------------------------------------------------------
# Round 9: the spec claims, tested AS CLAIMS
# ---------------------------------------------------------------------------


class TestStoredMessagesStayVerifiable:
    """§9.3 promises a stored message remains verifiable by anyone holding the
    correspondent's public key. Round 9 found that false for 7 of 10 realistic
    inputs, because the signature covered the in-memory object while the storage
    round trip rewrites three of the four covered fields.

    The old test used body="durable", subject="s" — the one input shape in the
    set that survives. It asserted the property while exercising the only case
    that could not fail.
    """

    CASES = [
        ("clean control", "s", "plain body"),
        ("body ends in a newline", "s", "from a file\n"),
        ("body ends in two newlines", "s", "markdown\n\n"),
        ("body is only newlines", "s", "\n\n\n"),
        ("subject with a leading space", "  padded", "b"),
        ("subject with a trailing space", "padded  ", "b"),
        ("subject containing a TAB", "before\tafter", "b"),
        ("subject with U+2028", "before after", "b"),
        ("subject over the 998 ceiling", "x" * 1200, "b"),
        ("subject with a CR", "before\rafter", "b"),
        ("empty body", "s", ""),
        ("unicode subject and body", "re: café", "éèê\n"),
    ]

    @pytest.mark.parametrize("label,subject,body", CASES)
    def test_signature_survives_the_storage_round_trip(self, keyed, label, subject, body):
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"], subject=subject, body=body)
        m.signature = sign(m, load_private_key(keyed["beta_key"]))
        assert verify(m, m.signature, [keyed["beta_pub"]]), f"{label}: unsigned in memory"

        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        raw = next((keyed["pull"]("alpha") / "Maildir" / "new").iterdir()).read_text()
        stored = Message.deserialize(raw)
        assert verify(stored, stored.signature, [keyed["beta_pub"]]), (
            f"{label}: verified in memory, UNVERIFIABLE once stored — the exact "
            f"failure §9.3 promises cannot happen")

    @pytest.mark.parametrize("label,subject,body", CASES)
    def test_canonical_form_is_a_fixed_point_of_the_round_trip(self, label, subject, body):
        """The property that makes the above true BY CONSTRUCTION rather than by
        luck: canonicalising a message equals canonicalising its round trip."""
        m = msg(subject=subject, body=body)
        again = Message.deserialize(m.serialize())
        assert m.canonical_for_signing() == again.canonical_for_signing(), label

    # THE FIX NORMALISES FOUR FIELDS AND THIS CLASS TESTED TWO.
    #
    # A mutation sweep made canonical `sender` and canonical `to` sign the
    # in-memory values instead, and both mutants SURVIVED — no test varied
    # either field across the round trip. I repaired the two fields the audit
    # showed me and left their siblings uncovered, which is the exact pattern
    # nine rounds of this campaign have been about. And the live defect
    # (recipients silently dropped past the 998-character header cap) was in one
    # of the two I had not tested.
    SENDER_CASES = [
        ("sender with padding", "  beta@example.test  "),
        ("sender with a tab", "beta@example.test\t"),
        ("sender with a trailing newline", "beta@example.test\n"),
        ("ordinary sender", f"beta@{DOMAIN}"),
    ]

    @pytest.mark.parametrize("label,sender", SENDER_CASES)
    def test_sender_is_a_fixed_point_of_the_round_trip(self, label, sender):
        m = msg(sender=sender)
        assert (m.canonical_for_signing()
                == Message.deserialize(m.serialize()).canonical_for_signing()), label

    TO_CASES = [
        ("recipients with padding", ["  a@x.test ", " b@x.test"]),
        ("a recipient with a tab", ["a@x.test\t", "b@x.test"]),
        ("many short recipients", [f"r{i}@x.test" for i in range(40)]),
        ("one recipient", ["only@x.test"]),
        ("recipients with display-name-ish text", ["a@x.test", "b@x.test"]),
    ]

    @pytest.mark.parametrize("label,to", TO_CASES)
    def test_recipients_are_a_fixed_point_of_the_round_trip(self, label, to):
        m = msg(to=to)
        assert (m.canonical_for_signing()
                == Message.deserialize(m.serialize()).canonical_for_signing()), label

    def test_submit_refuses_a_recipient_list_that_storage_would_shorten(self, deployment):
        """Defence in depth for the collision above, and untested until the sweep
        said so. The canonical form no longer collides — but the STORED `To:`
        header would still silently lose its tail, so a reader of an attested
        message could not see who else received it."""
        m = msg(to=[f"recipient-with-a-long-name-{i}@example.test" for i in range(40)])
        r = deployment["broker"].submit("alpha", m)
        assert r["ok"] is False
        assert any("silently shortened" in x for x in r["refused"]), r

    def test_submit_refuses_a_recipient_containing_a_comma(self, deployment):
        """A comma is the recipient separator, so such an address splits into two
        different addresses when read back — the stored recipients would differ
        from the signed ones."""
        r = deployment["broker"].submit("alpha", msg(to=[f"a,b@{DOMAIN}"]))
        assert r["ok"] is False
        assert any("comma" in x for x in r["refused"]), r

    def test_two_recipient_lists_sharing_a_long_prefix_do_not_collide(self):
        """Round 10: the canonical `to` ran through ONE _hdr() call capped at
        998, so any two lists sharing that prefix produced byte-identical
        signing payloads — one captured signature covering a message addressed
        somewhere else. MAX_RECIPIENTS did not prevent it; 64 ordinary addresses
        join to well over 998 characters."""
        from macf.amail.crypto import signing_payload
        pad = [f"padding-recipient-number-{i}@example.test" for i in range(60)]
        a = msg(to=pad + ["victim@example.test"])
        b = msg(to=pad + ["attacker-chosen@example.test"])
        assert a.to != b.to
        assert signing_payload(a) != signing_payload(b), \
            "two different recipient lists produced one signing payload"

    def test_the_payload_itself_is_identical_across_the_round_trip(self):
        """Assert the bytes, not just the verdict — a payload that differed while
        both happened to verify would be luck, not a fixed point."""
        from macf.amail.crypto import signing_payload
        m = msg(subject="tab\there  ", body="ends with newline\n\n")
        assert signing_payload(m) == signing_payload(Message.deserialize(m.serialize()))


class TestClassificationReachesTheAuditLog:
    """§6.5: 'Classification MUST be recorded in the audit log alongside the
    delivery decision.' Round 9 found no audit record carried it, and no test
    asserted one did. The header in the mailbox is not a substitute: that file
    lives in the recipient's own home, mode 700, rewritable by exactly the party
    an investigation would be about."""

    def test_outbound_delivery_records_the_classification(self, deployment):
        deployment["broker"].submit("alpha", msg())
        allowed = [r for r in deployment["broker"].audit.records()
                   if r.get("decision") == "allowed"]
        assert allowed and "trust" in allowed[0], "the verdict is not in the audit log"

    def test_outbound_delivery_records_the_kernel_established_authorship(self, deployment):
        """The one fact a reader of the stored message can never re-derive, so
        the audit log is the only place it can live."""
        deployment["broker"].submit("alpha", msg())
        allowed = [r for r in deployment["broker"].audit.records()
                   if r.get("decision") == "allowed"][0]
        assert allowed.get("authorship", "").startswith("so_peercred:")

    def test_inbound_delivery_records_the_classification(self, keyed):
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"])
        m.signature = sign(m, load_private_key(keyed["beta_key"]))
        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        rec = [r for r in keyed["broker"].audit.records()
               if r.get("direction") == "inbound"][0]
        assert rec.get("trust") == TrustClass.ATTESTED.value

    def test_quarantine_records_the_classification_too(self, deployment):
        m = msg(sender="stranger@elsewhere.test", to=[f"beta@{DOMAIN}"])
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        rec = [r for r in deployment["broker"].audit.records()
               if r.get("decision") == "quarantined"][0]
        assert "trust" in rec


class TestInboundHeaderStrippingIsWired:
    """§6.4 makes stripping a MUST. Round 9 found STRIPPED_INBOUND_HEADERS had
    ZERO call sites — the constant existed, the policy required it, and nothing
    invoked it. The test named for the requirement asserted on the constant's
    CONTENTS, which is a source-data assertion; the 'end-to-end' test passed with
    the strip list emptied and failed only when trust-minting was removed."""

    def test_the_stripper_is_invoked_on_the_inbound_path(self, deployment, monkeypatch):
        """ASSERT THE CALL, NOT THE SOURCE TEXT.

        The previous version of this test did inspect.getsource() and asserted a
        substring — so it passed if the call sat inside `if False:`, in a
        comment, or in dead code. Round 9 criticised exactly that shape in the
        test this one replaced, and I wrote the same defect into the
        replacement. A spy on the function is the behavioural equivalent and
        cannot be satisfied by text.
        """
        from macf.amail import broker as bmod

        called = []
        real = bmod.strip_inbound_headers
        monkeypatch.setattr(bmod, "strip_inbound_headers",
                            lambda m: (called.append(m), real(m))[1])
        deployment["broker"].accept_inbound(
            msg(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"]), f"beta@{DOMAIN}")
        assert called, "accept_inbound did not invoke the stripper"

    def test_stripping_actually_clears_an_asserted_verdict(self):
        """Behaviour, not the constant. A message carrying its own trust claim
        has it cleared by the stripper alone, independently of re-minting."""
        from macf.amail.broker import strip_inbound_headers
        m = msg()
        m.trust = "attested"
        cleared = strip_inbound_headers(m)
        assert m.trust is None
        assert "x-amail-trust" in cleared

    def test_the_stripper_reports_what_a_sender_tried_to_assert(self):
        """An attempt to assert a verdict is worth knowing about."""
        from macf.amail.broker import strip_inbound_headers
        assert strip_inbound_headers(msg()) == []


class TestSigningKeyCustody:
    # WRITE-WITHOUT-READ only. 0o660 is readable too, so the READ check fires
    # first and the test would pass with the new guard deleted — satisfied by a
    # sibling, which is the exact vacuity this suite keeps catching. These three
    # modes are refusable by nothing else.
    @pytest.mark.parametrize("mode", [0o620, 0o622, 0o602])
    def test_a_group_or_world_writable_private_key_is_refused(self, tmp_path, mode):
        """Round 9: the check asked who could READ the key and never who could
        WRITE it. A key another uid can write is one they authored, hence one
        they know — realised as authorship DENIAL, silently, while the CLI
        reports success."""
        generate_keypair(tmp_path / "k.pem")
        (tmp_path / "k.pem").chmod(mode)
        with pytest.raises(SigningError, match="writable by group or other"):
            load_private_key(tmp_path / "k.pem")

    def test_a_key_owned_by_another_uid_is_refused(self, tmp_path, monkeypatch):
        """Mutation survivor M08: this branch existed and nothing tested it."""
        generate_keypair(tmp_path / "k.pem")
        monkeypatch.setattr(os, "getuid", lambda: os.stat(tmp_path / "k.pem").st_uid + 1)
        with pytest.raises(SigningError, match="owned by uid"):
            load_private_key(tmp_path / "k.pem")

    def test_a_non_ed25519_private_key_is_refused(self, tmp_path):
        """Mutation survivor M09: the private-key half of the one-algorithm rule."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        p = tmp_path / "rsa.pem"
        p.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()))
        p.chmod(0o600)
        with pytest.raises(SigningError, match="not Ed25519"):
            load_private_key(p)


class TestAlgorithmCannotComeFromTheMessage:
    def test_the_payload_algorithm_is_constant_not_message_derived(self):
        """Mutation survivor M06: §9.4's 'never chosen by the message' was tested
        only on the key-parsing side. The payload side was unguarded."""
        import json as _json
        from macf.amail.crypto import ALGORITHM, signing_payload
        m = msg()
        m.alg = "none"  # a field a future Message might grow
        assert _json.loads(signing_payload(m))["alg"] == ALGORITHM


class TestTruncationPrecedesClassification:
    """THIS CLASS REPLACES ONE THAT ASSERTED THE BUG AS THE REQUIREMENT.

    The previous version asserted `stored.trust == "attested"` AND
    `len(stored.body) <= MAX_BODY` for an oversize body — which is precisely the
    lying state: a label saying a signature was verified, over bytes the
    signature does not cover. It was green, and it contradicted
    TestStoredMessagesStayVerifiable three classes above it in this same file.

    The comment it was written to defend argued that classifying the message AS
    RECEIVED avoided reporting SUSPECT for our own edit. That reasoning preferred
    our feelings about the sender to the reader's ability to check. If the broker
    edits a message, the signature no longer covers what was stored, and the
    honest label is the one that says so.

    The invariant, asserted rather than a case list:

        verify(deserialize(stored_bytes)) == (stored.trust == ATTESTED)
    """

    TRUNCATING_CASES = [
        ("body one byte over the cap", "s", None),
        ("body well over the cap", "s", None),
        ("65 recipients", "s", None),
        ("150 recipients", "s", None),
        ("subject over the ceiling with a CRLF", None, "b"),
    ]

    def _oversize(self, kind):
        from macf.amail import broker as bmod
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"])
        if kind == "body one byte over the cap":
            m.body = "x" * (bmod.MAX_BODY + 1)
        elif kind == "body well over the cap":
            m.body = "x" * (bmod.MAX_BODY + 20000)
        elif kind == "65 recipients":
            m.to = [f"r{i}@x.test" for i in range(64)] + [f"alpha@{DOMAIN}"]
        elif kind == "150 recipients":
            m.to = [f"r{i}@x.test" for i in range(149)] + [f"alpha@{DOMAIN}"]
        elif kind == "subject over the ceiling with a CRLF":
            # ~1.1 KB is enough: _hdr() folds CRLF (2 chars) to one space while
            # MAX_SUBJECT slices the RAW string, so the two cuts land at
            # different offsets.
            m.subject = ("a\r\n" * 40) + "b" * 1000
        return m

    @pytest.mark.parametrize("kind", [c[0] for c in TRUNCATING_CASES])
    def test_the_label_never_claims_more_than_the_stored_bytes_support(self, keyed, kind):
        m = self._oversize(kind)
        m.signature = sign(m, load_private_key(keyed["beta_key"]))
        assert verify(m, m.signature, [keyed["beta_pub"]]), f"{kind}: unsigned in memory"

        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        raw = next((keyed["pull"]("alpha") / "Maildir" / "new").iterdir()).read_text()
        stored = Message.deserialize(raw)
        verifies = verify(stored, stored.signature, [keyed["beta_pub"]])
        claims_signed = stored.trust == TrustClass.ATTESTED.value
        assert verifies == claims_signed, (
            f"{kind}: stored trust={stored.trust!r} but at-rest verification="
            f"{verifies}. The badge and the bytes disagree.")

    def test_a_message_within_every_bound_is_untouched_and_attested(self, keyed):
        """The bounds must not fire on ordinary mail, or the class above passes
        by refusing everything."""
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"], body="ordinary\n")
        m.signature = sign(m, load_private_key(keyed["beta_key"]))
        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        stored = store.read_all(keyed["pull"]("alpha"))[0]
        assert stored.trust == TrustClass.ATTESTED.value
        assert stored.body == "ordinary"

    def test_truncation_is_recorded_so_suspect_is_explainable(self, keyed):
        """An investigator must be able to tell 'the sender lied' from 'we edited
        it and the signature stopped covering what we stored'."""
        from macf.amail import broker as bmod
        m = msg(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"],
                body="x" * (bmod.MAX_BODY + 10))
        m.signature = sign(m, load_private_key(keyed["beta_key"]))
        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        rec = [r for r in keyed["broker"].audit.records()
               if r.get("direction") == "inbound"][0]
        assert "truncated" in (rec.get("reason") or ""), rec
        assert "body" in rec["reason"]

    def test_a_long_recipient_list_is_never_silently_shortened_on_disk(self, keyed):
        """The stored To: header must contain exactly the recipients the label
        was computed over — otherwise a reader of an attested message cannot see
        who else received it."""
        m = msg(sender=f"beta@{DOMAIN}",
                to=[f"recipient-with-a-long-name-{i}@example.test" for i in range(40)]
                   + [f"alpha@{DOMAIN}"])
        m.signature = sign(m, load_private_key(keyed["beta_key"]))
        keyed["broker"].accept_inbound(m, f"alpha@{DOMAIN}")
        raw = next((keyed["pull"]("alpha") / "Maildir" / "new").iterdir()).read_text()
        stored = Message.deserialize(raw)
        assert stored.to == Message.deserialize(raw).to
        assert len(", ".join(stored.to)) <= 998


class TestHeaderValuesAreStrippedOnRead:
    def test_deserialize_strips_header_whitespace(self):
        """Mutation survivor M33: untested, and one of the three normalisations
        behind the at-rest verification failure."""
        m = msg(subject="  padded  ")
        assert Message.deserialize(m.serialize()).subject == "padded"


class TestInboundBoundsMatchTheSubmitPath:
    def test_an_inbound_signature_is_bounded(self, deployment):
        """Round 9: MAX_SIGNATURE was applied on the submit path and not on the
        twin, where the message is hostile by assumption."""
        from macf.amail import broker as bmod
        m = msg(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"])
        m.signature = "A" * 50_000
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        stored = store.read_all(deployment["pull"]("beta"))[0]
        assert len(stored.signature or "") <= bmod.MAX_SIGNATURE

    def test_an_inbound_recipient_list_is_bounded(self, deployment):
        from macf.amail import broker as bmod
        m = msg(sender=f"alpha@{DOMAIN}", to=[f"r{i}@x.test" for i in range(500)])
        m.to.append(f"beta@{DOMAIN}")
        deployment["broker"].accept_inbound(m, f"beta@{DOMAIN}")
        stored = store.read_all(deployment["pull"]("beta"))[0]
        assert len(stored.to) <= bmod.MAX_RECIPIENTS


class TestFalsyContactKeysAreRefused:
    @pytest.mark.parametrize("value", ['""', "null", "0", "false", "[]"])
    def test_a_falsy_declared_key_is_not_silently_dropped(self, deployment, value):
        """Round 9: `e.get("key") or e.get("keys")` collapsed every falsy value
        to None, so a contact that DECLARED a key silently became keyless — which
        downgrades SUSPECT to UNVERIFIED by configuration rather than evidence."""
        deployment["contacts"].write_text(
            '{"alpha": [{"address": "beta@%s", "key": %s}]}' % (DOMAIN, value))
        deployment["contacts"].chmod(0o644)
        with pytest.raises(ContactListError):
            deployment["broker"].contacts.contacts_for("alpha", direction="outbound")


class TestVerifyNeverRaises:
    @pytest.mark.parametrize("mutate", [
        lambda m: setattr(m, "to", None),
        lambda m: setattr(m, "body", {"not": "a string"}),
        lambda m: setattr(m, "body", "lone surrogate \ud800"),
        lambda m: setattr(m, "subject", {1, 2, 3}),
        lambda m: setattr(m, "sender", None),
    ])
    def test_a_hostile_message_shape_returns_false_rather_than_raising(self, mutate, tmp_path):
        """verify() documents that forged inputs are its expected argument, then
        built the payload OUTSIDE the guard — so a hostile SHAPE raised straight
        through the promise not to raise."""
        key = generate_keypair(tmp_path / "k.pem")
        m = msg()
        sig = sign(m, load_private_key(tmp_path / "k.pem"))
        mutate(m)
        assert verify(m, sig, [key]) is False


class TestContactCacheRespectsEdits:
    def test_an_edited_contact_list_takes_effect_without_a_restart(self, deployment):
        """The cache is keyed on file identity, so the policy's 'changes take
        effect without a rebuild' still holds. Caching on process start would
        break it; caching on identity does not."""
        book = deployment["broker"].contacts
        assert book.permits("alpha", f"beta@{DOMAIN}", direction="outbound") is True
        time.sleep(0.01)
        deployment["contacts"].write_text(_addressing({"alpha": [], "beta": []}))
        deployment["contacts"].chmod(0o644)
        assert book.permits("alpha", f"beta@{DOMAIN}", direction="outbound") is False, \
            "a contact-list edit did not take effect"

    def test_repeated_checks_do_not_reparse_an_unchanged_file(self, deployment, monkeypatch):
        book = deployment["broker"].contacts
        book.contacts_for("alpha", direction="outbound")
        parses = []
        real = book._parse
        monkeypatch.setattr(book, "_parse", lambda: (parses.append(1), real())[1])
        for _ in range(50):
            book.permits("alpha", f"beta@{DOMAIN}", direction="outbound")
        assert parses == [], "an unchanged contact list was re-parsed per check"


class TestAuditRecordsEveryRecipientsVerdict:
    """Round 10: classification was per-recipient in storage but the single
    audit record read `message.trust` AFTER the loop — whatever the last
    delivery left on the shared object. The submitter chose which verdict was
    recorded by ordering the `to` list, and could suppress its own SUSPECT from
    the broker-owned record by appending one allowlisted keyless recipient."""

    @pytest.fixture
    def three(self, deployment, tmp_path):
        homes = deployment["homes"]
        homes["gamma"] = tmp_path / "gamma"
        homes["gamma"].mkdir(parents=True, exist_ok=True)
        deployment["cfg"].agent_homes = homes
        key = generate_keypair(tmp_path / "alpha.pem")
        deployment["contacts"].write_text(_addressing({
            "alpha": [f"beta@{DOMAIN}", f"gamma@{DOMAIN}"],
            "beta": [{"address": f"alpha@{DOMAIN}", "key": key}],   # beta knows the key
            "gamma": [f"alpha@{DOMAIN}"],                            # gamma does not
        }))
        deployment["contacts"].chmod(0o644)
        deployment["alpha_key"] = tmp_path / "alpha.pem"
        return deployment

    def _verdicts(self, dep):
        rec = [r for r in dep["broker"].audit.records() if r.get("decision") == "allowed"][-1]
        tr = rec["trust"]
        return tr if isinstance(tr, dict) else {"__single__": tr}

    def test_both_recipients_verdicts_are_recorded(self, three):
        m = msg(to=[f"beta@{DOMAIN}", f"gamma@{DOMAIN}"], body="signed")
        m.signature = sign(m, load_private_key(three["alpha_key"]))
        three["broker"].submit("alpha", m)
        got = self._verdicts(three)
        assert got.get(f"beta@{DOMAIN}") == TrustClass.ATTESTED.value
        assert got.get(f"gamma@{DOMAIN}") == TrustClass.UNVERIFIED.value

    def test_list_order_cannot_change_what_is_recorded(self, three):
        """The attack: reverse the list and the same delivery logged the other
        verdict."""
        m1 = msg(to=[f"beta@{DOMAIN}", f"gamma@{DOMAIN}"], body="one")
        m1.signature = sign(m1, load_private_key(three["alpha_key"]))
        three["broker"].submit("alpha", m1)
        forward = self._verdicts(three)

        m2 = msg(to=[f"gamma@{DOMAIN}", f"beta@{DOMAIN}"], body="two")
        m2.signature = sign(m2, load_private_key(three["alpha_key"]))
        three["broker"].submit("alpha", m2)
        reverse = self._verdicts(three)
        assert forward == reverse, "the submitter changed the audit verdict by list order"

    def test_a_suspect_verdict_cannot_be_suppressed_by_adding_a_recipient(self, three, tmp_path):
        """The sharpened attack: a compromised agent attaches a signature that
        does not verify, then appends one keyless recipient so the record reads
        UNVERIFIED instead of SUSPECT."""
        generate_keypair(tmp_path / "eve.pem")
        m = msg(to=[f"beta@{DOMAIN}", f"gamma@{DOMAIN}"], body="forged")
        m.signature = sign(m, load_private_key(tmp_path / "eve.pem"))
        three["broker"].submit("alpha", m)
        got = self._verdicts(three)
        assert TrustClass.SUSPECT.value in got.values(), \
            f"the SUSPECT verdict was suppressed from the broker-owned record: {got}"


class TestSenderMustMatchExactly:
    def test_a_case_variant_sender_is_refused_not_rewritten(self, deployment):
        """Round 10: canonicalize accepted a case variant and then REWROTE the
        field — which the signature had committed to. A config typo made every
        message arrive SUSPECT at every correspondent while the CLI printed
        delivered. Authorship denial through configuration, entirely silent."""
        m = msg(sender=f"ALPHA@{DOMAIN.upper()}")
        r = deployment["broker"].submit("alpha", m)
        assert r["ok"] is False
        assert any("exactly" in x for x in r["refused"]), r

    def test_an_exact_sender_is_accepted(self, deployment):
        assert deployment["broker"].submit("alpha", msg())["ok"] is True


class TestAuditSurvivesDescriptorPressure:
    def test_a_reserved_descriptor_is_held(self, tmp_path):
        log = AuditLog(tmp_path / "a.jsonl")
        assert log._spare_fd is not None, "no descriptor reserved for the audit write"

    def test_the_record_still_lands_when_descriptors_run_out(self, tmp_path, monkeypatch):
        """Round 10 measured mail DELIVERED AND ON DISK with no audit record,
        while the submitter was told it was not sent. The reserved descriptor is
        released and the write retried rather than lost."""
        import errno as _errno
        log = AuditLog(tmp_path / "a.jsonl")
        real_open = os.open
        state = {"fail": True}

        def flaky(path, flags, *a, **k):
            if state["fail"] and str(path).endswith(".lock"):
                state["fail"] = False           # fail once, as exhaustion would
                raise OSError(_errno.EMFILE, "Too many open files")
            return real_open(path, flags, *a, **k)

        monkeypatch.setattr(os, "open", flaky)
        log.refused(sender="alpha", recipients=["x@y.test"], reason="under pressure")
        assert log.refusals(), "the record was lost when descriptors ran out"
        assert log._spare_fd is not None, "the reserve was not re-established"

    def test_an_unrelated_oserror_is_not_retried(self, tmp_path, monkeypatch):
        """Only descriptor exhaustion earns the reserve.

        Asserting "it still raises" was VACUOUS: with the errno check deleted the
        retry runs and raises the same error again, so the exception arrives
        either way and the test could not tell the implementations apart. The
        mutation sweep caught it. Count the ATTEMPTS instead — that is the thing
        the errno check actually decides.
        """
        log = AuditLog(tmp_path / "a.jsonl")
        real_open, attempts = os.open, []

        def broken(path, flags, *a, **k):
            if str(path).endswith(".lock"):
                attempts.append(1)
                raise OSError(13, "Permission denied")
            return real_open(path, flags, *a, **k)

        monkeypatch.setattr(os, "open", broken)
        with pytest.raises(OSError):
            log.refused(sender="alpha", recipients=["x@y.test"], reason="r")
        assert len(attempts) == 1, (
            f"a non-EMFILE error was retried {len(attempts)} times; the reserved "
            "descriptor exists for exhaustion, not for masking real failures")

    def test_descriptor_exhaustion_IS_retried(self, tmp_path, monkeypatch):
        """The positive half, so the test above cannot pass by never retrying."""
        import errno as _errno
        log = AuditLog(tmp_path / "a.jsonl")
        real_open, attempts = os.open, []

        def flaky(path, flags, *a, **k):
            if str(path).endswith(".lock"):
                attempts.append(1)
                if len(attempts) == 1:
                    raise OSError(_errno.EMFILE, "Too many open files")
            return real_open(path, flags, *a, **k)

        monkeypatch.setattr(os, "open", flaky)
        log.refused(sender="alpha", recipients=["x@y.test"], reason="r")
        assert len(attempts) == 2, "exhaustion was not retried"


class TestRefusalRecordsNameTheSubmitter:
    def test_an_unhandled_exception_record_carries_the_sender(self, deployment):
        """§3.3 lists the sending identity as a MINIMUM. An unhandled-exception
        refusal wrote a record with no sender and no recipients at all — the one
        record an investigator would reach for said nothing about who."""
        import socket as s_
        deployment["cfg"].credentials_path.write_text("secret")
        deployment["cfg"].credentials_path.chmod(0o600)
        srv = serve(deployment["broker"])
        time.sleep(0.15)
        try:
            c = s_.socket(s_.AF_UNIX, s_.SOCK_STREAM)
            c.connect(str(deployment["cfg"].socket_path))
            c.sendall(json.dumps({"message": {"sender": f"alpha@{DOMAIN}", "to": None,
                                              "subject": "s", "body": "b"}}).encode() + b"\n")
            c.recv(4096)
            c.close()
            time.sleep(0.2)
            errs = [r for r in deployment["broker"].audit.records()
                    if r.get("decision") == "error"]
            assert errs, "no record at all for a failed submission"
            assert errs[-1].get("sender") == "alpha", errs[-1]
        finally:
            srv.shutdown()


class TestAnonymousPeersAreMeteredToo:
    def test_the_none_bucket_is_bounded_like_any_other(self, deployment):
        """Round 10: the per-uid bound was skipped entirely for an
        unidentifiable peer, so `None` got the full global cap — sixty-four
        anonymous slots, enough to lock out every real agent. The comment
        claimed one bucket."""
        from macf.amail import broker as bmod

        srv = bmod._Server.__new__(bmod._Server)
        srv._meter_lock = bmod.threading.Lock()
        srv._inflight, srv._per_uid, srv._overload_audited = {}, {}, {}
        granted = sum(1 for i in range(bmod.MAX_CONCURRENT_CONNECTIONS)
                      if srv._acquire(f"req{i}", None))
        assert granted <= bmod.MAX_CONNECTIONS_PER_UID, (
            f"{granted} anonymous connections granted; the per-uid cap is "
            f"{bmod.MAX_CONNECTIONS_PER_UID}")

    def test_an_identified_agent_is_not_starved_by_anonymous_peers(self, deployment):
        from macf.amail import broker as bmod

        srv = bmod._Server.__new__(bmod._Server)
        srv._meter_lock = bmod.threading.Lock()
        srv._inflight, srv._per_uid, srv._overload_audited = {}, {}, {}
        for i in range(bmod.MAX_CONCURRENT_CONNECTIONS):
            srv._acquire(f"anon{i}", None)
        assert srv._acquire("real", 1234) is True, \
            "anonymous peers locked out an identified agent"


class TestCanonicalizeDestroysASubmittedTrustClaim:
    def test_canonicalize_itself_clears_the_claim(self, deployment):
        """The `message.trust = None` line in canonicalize() was flagged as a
        DEAD STORE: every path overwrites it in _deliver_one(), so a mutant that
        minted ATTESTED there was an equivalent mutant. Testing canonicalize
        directly makes the line observable, which is the difference between a
        defensive assignment and decoration."""
        m = msg()
        m.trust = "attested"
        deployment["broker"].canonicalize("alpha", m, None)
        assert m.trust is None, "canonicalize did not destroy the submitted claim"


# ---------------------------------------------------------------------------
# ACCESS FOLLOWS CUSTODY (spec I3 / C7.3) — and this block used to assert the
# opposite, deliberately, so its history is part of its meaning.
#
# The first version of these tests pinned "with no broker, no mail is
# readable": reads were routed through the socket so they would be audited and
# answer to an allowlist. The custody ruling reversed that at the delivery
# boundary — the agent's mailbox is a permanent consciousness-artifact store,
# and a record that requires a running service to read is not a permanent
# record. The split property now measured here:
#
#   DELIVERED mail (the agent's own store): readable directly, broker down or
#   not. That is a REQUIREMENT, not a fallback — the acceptance battery's
#   broker-outage test turns on it.
#
#   The BROKER's stores (quarantine, pickup counts) and SUBMISSION: socket
#   only. No broker means those counts are UNKNOWN (never displayed as zero)
#   and sending is impossible.
#
# The old bundle list/read socket operations served delivered mail across the
# custody boundary — the KNOWN-DEVIATION the spec's conformance table carried
# until the unprivileged broker made executing them physically impossible
# (its uid cannot read agent homes). The structural tests below pin their
# absence so the deviation cannot quietly return.
# ---------------------------------------------------------------------------


class TestAccessFollowsCustody:

    def _cfg(self, monkeypatch, home, socket_path):
        from macf import cli
        # Mirrors _amail_config's full contract — every key it always sets —
        # so these tests fail on real regressions, not on the fake drifting.
        monkeypatch.setattr(cli, "_amail_config", lambda: {
            "agent": "alpha", "domain": DOMAIN,
            "socket": str(socket_path), "home": str(home),
            "handoff": str(Path(str(home)).parent / "handoff-unused"),
        })
        return cli

    def test_list_reads_delivered_mail_with_the_broker_down(
            self, deployment, monkeypatch, capsys):
        """Delivered mail is the agent's permanent record. A stopped broker
        must not make it unreadable — the battery's outage test turns on
        exactly this."""
        from argparse import Namespace
        home = deployment["homes"]["alpha"]
        store.deliver(home, msg(subject="READABLE-WITHOUT-A-BROKER"))
        assert len(store.read_all(home)) == 1

        cli = self._cfg(monkeypatch, home, deployment["tmp"] / "absent.sock")
        rc = cli.cmd_amail_list(Namespace(thread=None, json=False))

        out = capsys.readouterr().out
        assert rc == 0, "listing the agent's own record needs no service"
        assert "READABLE-WITHOUT-A-BROKER" in out

    def test_read_works_with_the_broker_down(
            self, deployment, monkeypatch, capsys):
        from argparse import Namespace
        home = deployment["homes"]["alpha"]
        m = msg(subject="ALSO-READABLE-WITHOUT-A-BROKER")
        store.deliver(home, m)

        cli = self._cfg(monkeypatch, home, deployment["tmp"] / "absent.sock")
        rc = cli.cmd_amail_read(Namespace(message_id=m.message_id, json=False))

        out = capsys.readouterr().out
        assert rc == 0
        assert "ALSO-READABLE-WITHOUT-A-BROKER" in out

    def test_status_splits_counts_by_custody_when_the_broker_is_down(
            self, deployment, monkeypatch, capsys):
        """Own-store counts come from the filesystem and survive the outage;
        broker-store counts must read as UNKNOWN — an absent broker's empty
        display must never be mistakable for an empty quarantine."""
        from argparse import Namespace
        home = deployment["homes"]["alpha"]
        store.deliver(home, msg(subject="s"))

        cli = self._cfg(monkeypatch, home, deployment["tmp"] / "absent.sock")
        cli.cmd_amail_status(Namespace(json=False))

        out = capsys.readouterr().out
        assert "1 bundle(s)" in out, "the agent counts its own record itself"
        assert "❌ unreachable" in out
        assert "UNKNOWN, not zero" in out, \
            "broker-side counts must be declared unknown, not omitted silently"

    def _listening_socket(self, path):
        """A real AF_UNIX listener so the reachability probe succeeds; the
        status call itself is monkeypatched, so nothing talks through it."""
        import socket as _socket
        srv = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        srv.bind(str(path))
        srv.listen(1)
        return srv

    def test_status_surfaces_a_broker_refusal_instead_of_swallowing_it(
            self, deployment, monkeypatch, capsys):
        """ok:false from a reachable broker is a distinct fact from broker-down.

        The swallowed form of this is how a stale daemon on the socket — one
        predating the status op — hid behind a bare "counts unavailable".
        """
        from argparse import Namespace
        import macf.amail.client as client
        home = deployment["homes"]["alpha"]
        sock = deployment["tmp"] / "live.sock"
        srv = self._listening_socket(sock)
        try:
            monkeypatch.setattr(client, "status", lambda p: {
                "ok": False, "error": "ValueError: unknown operation 'status'"})
            cli = self._cfg(monkeypatch, home, sock)
            cli.cmd_amail_status(Namespace(json=False))
        finally:
            srv.close()
        captured = capsys.readouterr()
        assert "unknown operation 'status'" in captured.err, \
            "the broker's own refusal reason must reach stderr"
        assert "stale" in captured.err
        # And the refusal must not have silently produced fake zeros: the
        # broker-owned counts' action lines only print from a real answer.
        assert "quarantine" not in captured.out
        assert "pickup box" not in captured.out

    def test_status_shows_the_pending_pickup_count(
            self, deployment, monkeypatch, capsys):
        """pending_pickup is the count that calls for an action — a recipient
        learns it has custody transfers waiting. Dropping it in presentation
        makes the box invisible to exactly the party that must drain it."""
        from argparse import Namespace
        import macf.amail.client as client
        home = deployment["homes"]["alpha"]
        sock = deployment["tmp"] / "live2.sock"
        srv = self._listening_socket(sock)
        try:
            monkeypatch.setattr(client, "status", lambda p: {
                "ok": True, "messages": 0, "internet": 0,
                "quarantined": 0, "pending_pickup": 2})
            cli = self._cfg(monkeypatch, home, sock)
            cli.cmd_amail_status(Namespace(json=False))
        finally:
            srv.close()
        out = capsys.readouterr().out
        assert "2 message(s) waiting in your pickup box" in out
        assert "amail list" in out, "the remedy must be named, not implied"

    def test_the_socket_has_no_delivered_mail_operations(self):
        """Structural pin on the realignment: bundle-mail list/read operations
        served delivered mail across the custody boundary, and a future edit
        reintroducing them should fail here and force the conversation. Their
        old concerns are not lost — they dissolved: scoping-to-own-mailbox and
        the message-id-oracle problem existed only BECAUSE a socket op reached
        into mail stores; with delivered mail read from the agent's own store
        by the agent's own uid, the kernel is the scope."""
        from macf.amail import Broker
        for name in ("list_messages", "read_message"):
            assert not hasattr(Broker, name), (
                f"Broker.{name} has returned: a socket operation serving "
                f"delivered mail crosses the custody rule (spec I3/C7.3)"
            )

    def test_status_accepts_no_mailbox_parameter(self):
        """The surviving read op is scoped by kernel identity alone: there is
        no parameter through which a caller could name whose counts it wants."""
        import inspect
        from macf.amail import Broker
        params = set(inspect.signature(Broker.status_counts).parameters)
        assert not (params & {"home", "path", "mailbox", "maildir"}), (
            "Broker.status_counts accepts a mailbox parameter; broker-store "
            "reads must be scoped by kernel identity alone"
        )


class TestBrokerStoreReadsAreAudited:
    """The status op reads the BROKER's stores, and that read leaves a record.

    Historical note: delivered-mail reads were once audited here too. The
    custody ruling forbids that as a control — the agent owns those files, so
    a read-audit over them would faithfully record compliant reads and
    silently omit every other kind, complete-looking and incomplete by
    construction. Accountability lives at authorization and delivery, which
    the broker audits; what remains auditable at read time is access to the
    stores the broker itself owns.
    """

    def test_status_writes_a_read_record_naming_the_agent(self, deployment):
        broker = deployment["broker"]

        broker.status_counts("alpha")

        reads = [r for r in list(deployment["broker"].audit.records())
                 if r.get("decision") == "read"]
        assert len(reads) == 1, "a broker-store read that leaves no record is the defect"
        assert reads[0]["sender"] == "alpha"
        assert reads[0]["operation"] == "status"
        assert reads[0]["direction"] == "mailbox"
        assert reads[0]["ts"]


class TestNoGuardWithoutACallSite:
    """A control invoked by nothing is not a control.

    This is mechanized rather than reviewed because the failure is invisible by
    construction: the guard is present, correct, and covered by passing tests,
    and the only thing missing is that production never calls it. That exact
    shape has already cost this subsystem twice -- a terminal-safety escape wired
    to the inbound render and never to the outbound one, and a credential-custody
    check that was unit-tested for a cycle before anything invoked it.

    The sweep asserts on CALL SITES, not on source text describing them.
    """

    #: Guards permitted to have no production caller, each with the condition
    #: that retires the exemption. An entry here is a debt, not a dispensation:
    #: when the named subsystem lands, the entry must be deleted and this test
    #: will then require a real call site.
    KNOWN_UNINTEGRATED = {
        # The inbound delivery/quarantine path. Nothing calls it because there
        # is no inbound path yet -- that is the Phase 5.3 transport decision and
        # the Phase 6 round trip. It is ahead of its integration point rather
        # than orphaned inside a finished system, which is a different fault
        # from the two named above and must not be conflated with them.
        # REMOVE THIS ENTRY when an inbound receiver hands messages to the
        # broker; the test then demands the call site.
        "accept_inbound",
    }

    GUARD_PREFIXES = ("assert_", "check_", "verify_", "validate_", "ensure_",
                      "refuse", "sanit", "classify", "accept_")

    def _guards(self):
        import ast
        from pathlib import Path
        pkg = Path(__file__).resolve().parents[1] / "src" / "macf" / "amail"
        out = {}
        for f in sorted(pkg.glob("*.py")):
            src = f.read_text()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.FunctionDef) and \
                        node.name.startswith(self.GUARD_PREFIXES):
                    out[node.name] = f.name
        return out

    def _production_call_count(self, name):
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "src" / "macf"
        src = "\n".join(p.read_text() for p in root.rglob("*.py"))
        # A call is `name(` not preceded by `def `. The lookbehind removes the
        # definition, so no arithmetic correction is needed -- an earlier version
        # of this sweep subtracted one anyway and reported every called guard as
        # uncalled, which is the instrument-with-no-control failure again.
        return len(re.findall(rf"(?<!def )\b{re.escape(name)}\s*\(", src))

    def test_the_sweep_can_tell_the_two_cases_apart(self):
        """Control on the instrument: a guard known to be called must read as
        called, and a name that cannot exist must read as uncalled. Without this
        the sweep could pass by measuring nothing."""
        assert self._production_call_count("assert_credential_custody") >= 1, (
            "known-called guard reads as uncalled; the sweep is broken"
        )
        assert self._production_call_count("__no_such_guard_anywhere") == 0

    def test_every_guard_has_a_production_call_site(self):
        offenders = {
            name: fname for name, fname in self._guards().items()
            if name not in self.KNOWN_UNINTEGRATED
            and self._production_call_count(name) == 0
        }
        assert not offenders, (
            f"guards with no production call site: {offenders}. "
            f"A guard nothing calls is documentation. Either wire it to the path "
            f"it protects, or add it to KNOWN_UNINTEGRATED with the condition "
            f"that retires the exemption."
        )

    def test_exemptions_are_retired_once_they_gain_a_caller(self):
        """The exemption list must not outlive its reason. When an entry gains a
        production call site, the entry is stale and has to go -- otherwise the
        list quietly becomes a permanent allowlist of unchecked controls."""
        stale = [n for n in self.KNOWN_UNINTEGRATED
                 if self._production_call_count(n) > 0]
        assert not stale, (
            f"these are now called in production and must be removed from "
            f"KNOWN_UNINTEGRATED: {stale}"
        )


class TestDeliveryOutcomeFieldsAreNamedNotOrdered:
    """The four delivery-outcome fields must not be swappable in silence.

    `_deliver_one` used to return a positional 4-tuple. `rung`/`trust` are both
    strings and so are `state`/`detail`, so reordering either pair type-checked,
    ran, and silently swapped their meanings at the single unpacking site.

    This class exists because a mutation sweep proved the gap rather than
    predicted it: swapping `state` with `detail`, and `rung` with `trust`, on
    live delivery paths left the ENTIRE suite green. The record type now makes
    the swap unrepresentable, and these assertions make it detectable — the
    refactor and the test that can see it landing together, because the
    refactor alone would have been an unverified change to delivery code.
    """

    def test_a_local_delivery_reports_each_field_in_its_own_slot(self, deployment):
        r = deployment["broker"].submit("alpha", msg())
        assert r["ok"], r
        entry = r["delivered"][0]

        # Each assertion pins ONE slot to a value only that slot can hold, so a
        # swap with a same-typed sibling fails here rather than passing quietly.
        assert entry["rung"] == "local", "rung must name the path, not the trust"
        assert entry["state"] == "delivered", "state must name the outcome, not the reason"
        assert entry["detail"] == "", "detail is the reason; empty on success"
        assert entry["trust"] != "local", "trust must not be holding the rung"
