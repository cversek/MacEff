"""Tests for internet-inbound spool processing (macf.amail.inbound).

Known-answer FIRST: a suite that only exercises refusals cannot distinguish
a working authorizer from one that refuses everything, so the opening test
is an authorized message reaching the mailbox byte-exact. Refusal tests then
vary ONE thing each from that accepted baseline.

The push-eligibility and conservation tests are the spec's own named
controls: a generous contacts file MUST fail the run, and the conservation
check MUST go red when fed an audit log with a terminal record removed.
"""
from conftest import _addressing

import hashlib
import json
import time
from pathlib import Path

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from macf.amail import inbound
from macf.amail.broker import BrokerConfig
from macf.amail.inbound import (
    HANDED_OFF, DELIVER_PULL, DELIVER_PUSH_WAKE, QUARANTINED,
    InboundConfig, PushEligibilityError,
)

AUTHORITY = "mx.test.example"
HUMAN = "human@example.org"
PUSHY = "operator@example.org"
AGENT = "agent_alpha"
DOMAIN = "agents.test"


def make_raw(sender: str = HUMAN, dmarc: str = "pass",
             authority: str = AUTHORITY, extra_headers: str = "",
             body: str = "hello there", aligned: str = None,
             omit_header_from: bool = False) -> bytes:
    """A spooled message as the edge would hand it over.

    `header.from=` is part of the BASELINE because a real authority states
    which domain it aligned; the verdict is only bindable to a sender if that
    statement is present. `aligned` overrides it (the parser-differential
    case: aligned as one domain, From reading as another) and
    `omit_header_from` removes it entirely.
    """
    dmarc_from = "" if omit_header_from else \
        f" header.from={aligned or sender.rsplit('@', 1)[1]};"
    ar = (f"Authentication-Results: {authority}; dmarc={dmarc}"
          f"{dmarc_from} spf=pass\r\n")
    return (f"{extra_headers}{ar}From: Someone <{sender}>\r\n"
            f"To: {AGENT}@{DOMAIN}\r\nSubject: test\r\n\r\n{body}").encode()


@pytest.fixture
def deploy(tmp_path):
    """A miniature inbound deployment: one agent, contacts, spool, audit."""
    home = tmp_path / "home" / AGENT
    (home / "Maildir").mkdir(parents=True)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_addressing({
        AGENT: [HUMAN, {"address": PUSHY, "push": True}],
    }))
    cfg = InboundConfig(
        broker_config=BrokerConfig(
            domain=DOMAIN,
            agent_homes={AGENT: home},
            contacts_path=contacts,
            audit_path=tmp_path / "audit.jsonl",
        ),
        spool_dir=tmp_path / "spool",
        quarantine_dir=tmp_path / "quarantine",
        handoff_dir=tmp_path / "handoff",
        verdict_authority=AUTHORITY,
    )
    cfg.spool_dir.mkdir()
    return cfg


def spool(cfg: InboundConfig, raw: bytes, *, envelope_to: str = f"{AGENT}@{DOMAIN}",
          sha: str = None) -> tuple:
    digest = sha or hashlib.sha256(raw).hexdigest()
    eml = cfg.spool_dir / f"20260817T000000_{digest[:16]}.eml"
    eml.write_bytes(raw)
    sidecar = eml.with_suffix(".json")
    sidecar.write_text(json.dumps({
        "raw_sha256": digest,
        "observed": {"trusted": False, "envelope_to": envelope_to},
    }))
    return eml, sidecar


# ---- known answer first ----------------------------------------------------

def test_authorized_mail_is_handed_off_byte_exact(deploy):
    raw = make_raw()
    eml, sidecar = spool(deploy, raw)
    result = inbound.process_entry(deploy, eml, sidecar)

    assert result["disposition"] == HANDED_OFF
    assert result["delivery_class"] == DELIVER_PULL
    box = deploy.handoff_dir / AGENT
    handed = list(box.glob("*.eml"))
    assert len(handed) == 1
    assert handed[0].read_bytes() == raw
    # Spool consumed only after the handoff completed.
    assert not eml.exists() and not sidecar.exists()


def test_ingest_executes_the_custody_transfer(deploy):
    # The RECIPIENT moves mail from the pickup box into its own store, as
    # itself -- ownership correct by construction, no privileged component.
    from macf.amail.client import ingest, list_delivered_internet
    raw = make_raw()
    inbound.process_entry(deploy, *spool(deploy, raw))
    home = deploy.broker_config.agent_homes[AGENT]
    results = ingest(home, deploy.handoff_dir / AGENT)
    assert len(results) == 1 and results[0]["ingested"] is True
    # Box emptied only after the ingested copy exists.
    assert list((deploy.handoff_dir / AGENT).glob("*.eml")) == []
    items = list_delivered_internet(home)
    assert len(items) == 1
    assert items[0]["sidecar"]["raw_sha256"] == hashlib.sha256(raw).hexdigest()


def test_ingest_refuses_a_tampered_box_entry(deploy):
    # A box entry whose bytes do not match its sidecar hash stays in the
    # box with the reason -- never silently ingested, never silently gone.
    from macf.amail.client import ingest
    raw = make_raw()
    inbound.process_entry(deploy, *spool(deploy, raw))
    box = deploy.handoff_dir / AGENT
    victim = next(box.glob("*.eml"))
    victim.write_bytes(raw + b"tampered")
    results = ingest(deploy.broker_config.agent_homes[AGENT], box)
    assert results[0]["ingested"] is False
    assert "hash mismatch" in results[0]["reason"]
    assert victim.exists()


def test_handoff_sidecar_carries_authorization_and_untrusted_observations(deploy):
    raw = make_raw()
    inbound.process_entry(deploy, *spool(deploy, raw))
    sidecars = list((deploy.handoff_dir / AGENT).glob("*.json"))
    assert len(sidecars) == 1
    meta = json.loads(sidecars[0].read_text())
    assert meta["authorization"]["outcome"] == DELIVER_PULL
    assert meta["observed"]["trusted"] is False


def test_audit_records_seen_and_exactly_one_terminal(deploy):
    raw = make_raw()
    inbound.process_entry(deploy, *spool(deploy, raw))
    records = [json.loads(l) for l in
               deploy.broker_config.audit_path.read_text().splitlines()]
    decisions = [r["decision"] for r in records if r.get("direction") == "inbound"]
    assert decisions.count(inbound.SEEN) == 1
    assert decisions.count(HANDED_OFF) == 1


# ---- refusals: one variable each -------------------------------------------

def test_forged_later_verdict_cannot_override_first_instance(deploy):
    # Our authority stamps dmarc=fail FIRST; the sender pre-embedded a
    # forged pass claiming the same authority. First instance must win.
    forged = f"Authentication-Results: {AUTHORITY}; dmarc=pass\r\n"
    raw = make_raw(dmarc="fail") .replace(b"From:", forged.encode() + b"From:", 1)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == QUARANTINED
    assert "dmarc" in result["reason"]


# ---- the verdict must be BOUND to the sender, not merely adjacent to it ----
# Reported by the peer reviewer from a read of authorize(): dmarc=pass and
# contacts.permits(sender) were two independent gates, so a pass covering ANY
# domain admitted a sender at a DIFFERENT domain. It could not be weaponised
# from outside (producing the pass side needs a signable domain), which is why
# it needed a reader rather than a prober.

def test_verdict_aligned_to_another_domain_does_not_admit_this_sender(deploy):
    # The exact parser differential: the authority aligned a domain the
    # attacker can sign; parseaddr resolves the From to a real contact.
    # Single variable from the accepted baseline — only the aligned domain.
    raw = make_raw(sender=HUMAN, aligned="attacker-controlled.example")
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == QUARANTINED
    assert "does not cover this sender" in result["reason"]
    assert "attacker-controlled.example" in result["reason"], \
        "the refusal must name BOTH domains or it cannot be diagnosed"
    assert HUMAN.rsplit("@", 1)[1] in result["reason"]


def test_dmarc_pass_naming_no_aligned_domain_is_refused(deploy):
    # A pass with no header.from is unbindable: it says somebody's mail
    # passed. Fail closed rather than fall back to trusting adjacency.
    raw = make_raw(omit_header_from=True)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == QUARANTINED
    assert "names no aligned domain" in result["reason"]


def test_aligned_domain_is_read_from_the_first_instance_only(deploy):
    # The binding must inherit the first-instance rule, or it becomes a new
    # way to smuggle a claim: forged LATER instance aligning the sender's
    # real domain, first instance aligning something else.
    forged = (f"Authentication-Results: {AUTHORITY}; dmarc=pass "
              f"header.from={HUMAN.rsplit('@', 1)[1]}; spf=pass\r\n")
    raw = make_raw(aligned="attacker-controlled.example")
    raw = raw.replace(b"From:", forged.encode() + b"From:", 1)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == QUARANTINED
    assert "does not cover this sender" in result["reason"]


def test_multiple_from_headers_are_refused_not_resolved(deploy):
    # RFC 5322 permits one. Two means our parser and the authority's may pick
    # different ones, which is the vehicle for the differential above.
    raw = make_raw(extra_headers=f"From: Someone Else <{PUSHY}>\r\n")
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == QUARANTINED
    assert "From headers" in result["reason"]


def test_untrusted_authority_reads_as_no_verdict(deploy):
    raw = make_raw(authority="mx.somebody-else.example")
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == QUARANTINED
    assert "no trustworthy" in result["reason"]


def test_unlisted_sender_is_quarantined_with_reason_artifact(deploy):
    raw = make_raw(sender="stranger@example.org")
    eml, sidecar = spool(deploy, raw)
    result = inbound.process_entry(deploy, eml, sidecar)
    assert result["disposition"] == QUARANTINED
    # Quarantine is an ARTIFACT, not an alert: content + reason inspectable.
    assert (deploy.quarantine_dir / eml.name).exists()
    assert "not in the contact list" in \
        (deploy.quarantine_dir / f"{eml.stem}.reason").read_text()


def test_hash_mismatch_is_quarantined_as_corruption(deploy):
    raw = make_raw()
    eml, sidecar = spool(deploy, raw, sha="0" * 64)
    result = inbound.process_entry(deploy, eml, sidecar)
    assert result["disposition"] == QUARANTINED
    assert "hash mismatch" in result["reason"]
    assert (deploy.quarantine_dir / eml.name).exists()


def test_mail_for_unknown_recipient_is_quarantined(deploy):
    raw = make_raw()
    result = inbound.process_entry(
        deploy, *spool(deploy, raw, envelope_to="nobody@elsewhere.example"))
    assert result["disposition"] == QUARANTINED
    assert "no local agent" in result["reason"]


# ---- push-wake eligibility (the spec's named controls) ---------------------

def test_push_granted_human_gets_push_wake_class(deploy):
    deploy.push_wake_enabled = True
    raw = make_raw(sender=PUSHY)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == HANDED_OFF
    assert result["delivery_class"] == DELIVER_PUSH_WAKE


def test_generous_contacts_file_fails_the_run(deploy):
    # CONTROL: push granted to an address in the AGENT NAMESPACE must be
    # fatal -- not a warning, not a skip. This is the derivation, checkable.
    deploy.broker_config.contacts_path.write_text(_addressing({
        AGENT: [{"address": f"other_agent@{DOMAIN}", "push": True}],
    }))
    deploy.broker_config.agent_homes["other_agent"] = Path("/nonexistent")
    with pytest.raises(PushEligibilityError):
        inbound.process_spool(deploy)


def test_history_backstop_degrades_push_to_pull_visibly(deploy, capsys):
    # The pushy sender has originated agent-bundle traffic per the audit log.
    deploy.push_wake_enabled = True
    from macf.amail.audit import AuditLog
    AuditLog(deploy.broker_config.audit_path).allowed(
        sender=PUSHY, recipients=[f"{AGENT}@{DOMAIN}"], message_id="m1",
        rung="local")
    raw = make_raw(sender=PUSHY)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == HANDED_OFF
    assert result["delivery_class"] == DELIVER_PULL
    assert "degraded" in capsys.readouterr().err


def test_history_backstop_fails_closed_without_audit(deploy):
    deploy.push_wake_enabled = True
    deploy.broker_config.audit_path = None
    raw = make_raw(sender=PUSHY)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == HANDED_OFF
    assert result["delivery_class"] == DELIVER_PULL  # not push: fails closed


# ---- conservation (the control carries its own known-answer red) -----------

def test_conservation_balances_after_mixed_dispositions(deploy):
    inbound.process_entry(deploy, *spool(deploy, make_raw()))
    inbound.process_entry(deploy, *spool(deploy,
                                         make_raw(sender="stranger@example.org",
                                                  body="different")))
    report = inbound.reconcile(deploy)
    assert report["balanced"] is True
    assert report["seen"] == 2 and report["terminal"] == 2


def test_conservation_goes_red_when_a_terminal_record_is_removed(deploy):
    inbound.process_entry(deploy, *spool(deploy, make_raw()))
    audit_path = deploy.broker_config.audit_path
    lines = [l for l in audit_path.read_text().splitlines()
             if json.loads(l).get("decision") != HANDED_OFF]
    audit_path.write_text("\n".join(lines) + "\n")
    report = inbound.reconcile(deploy)
    assert report["balanced"] is False
    assert len(report["missing_terminal"]) == 1


def test_in_flight_spool_entries_are_not_shortfalls(deploy):
    from macf.amail.audit import AuditLog
    raw = make_raw()
    spool(deploy, raw)  # spooled, SEEN recorded manually, never processed
    AuditLog(deploy.broker_config.audit_path).inbound(
        sender="unknown", recipient="unknown",
        message_id=hashlib.sha256(raw).hexdigest(),
        decision=inbound.SEEN, reason="test in-flight")
    report = inbound.reconcile(deploy)
    assert report["balanced"] is True
    assert report["in_flight"] == 1


# ---- the read surface, per the custody rule --------------------------------
# Delivered mail is the agent's own permanent store: read DIRECTLY from the
# filesystem. The socket remains the access path to the BROKER's stores
# (status counts, quarantine) — tested further down against the Broker.

@pytest.fixture
def delivered(deploy):
    """One authorized message, handed off AND ingested by the recipient."""
    from macf.amail.client import ingest
    raw = make_raw(body="the readable one")
    inbound.process_entry(deploy, *spool(deploy, raw))
    home = deploy.broker_config.agent_homes[AGENT]
    ingest(home, deploy.handoff_dir / AGENT)
    return home, raw


def test_delivered_internet_listed_directly_via_sidecar(delivered):
    from macf.amail.client import list_delivered_internet
    home, raw = delivered
    items = list_delivered_internet(home)
    assert len(items) == 1
    assert items[0]["message_present"] is True
    assert items[0]["sidecar"]["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert items[0]["sidecar"]["authorization"]["outcome"] == DELIVER_PULL


def test_delivered_internet_read_directly_by_sha_prefix_and_name(delivered):
    from macf.amail.client import read_delivered_internet, list_delivered_internet
    home, raw = delivered
    sha = hashlib.sha256(raw).hexdigest()
    found = read_delivered_internet(home, sha[:12])
    assert found is not None and found[0] == raw
    name = list_delivered_internet(home)[0]["name"]
    assert read_delivered_internet(home, name) is not None
    assert read_delivered_internet(home, "feedfeedfeed") is None


# ---- the two facets must not overlap (found live, by the operator) --------
# Delivered internet mail is stored as raw RFC 822 (F6.1), which parses well
# enough to impersonate a bundle in the shared Maildir. That produced a
# phantom bundle AND a thread id minted from the clock on every read.

def test_internet_mail_does_not_appear_in_the_bundle_facet(delivered, deploy):
    from macf.amail import store
    from macf.amail.client import list_delivered_internet
    home, _ = delivered
    assert len(list_delivered_internet(home)) == 1, "the internet facet must see it"
    assert store.read_all(home) == [], \
        "one delivery counted twice: raw internet mail read as a bundle"


def test_a_real_bundle_still_appears_in_the_bundle_facet(delivered, deploy):
    """The control on the fix. Excluding by sidecar could 'fix' the count by
    hiding everything; this proves genuine bundles are still listed, and that
    the two facets partition rather than overlap."""
    from macf.amail import store
    from macf.amail.client import list_delivered_internet
    from macf.amail.models import Message
    home, _ = delivered
    store.deliver(home, Message(sender="peer@agents.test", to=[f"{AGENT}@{DOMAIN}"],
                                subject="a real bundle", body="hi"))
    assert len(store.read_all(home)) == 1, "the genuine bundle must be listed"
    assert store.read_all(home)[0].subject == "a real bundle"
    assert len(list_delivered_internet(home)) == 1, "and the internet one, once"


def test_thread_id_is_stable_across_reads(delivered, deploy):
    """A thread identifier minted at read time changes between two listings
    and cannot thread anything. Stored bundles keep theirs; a stored message
    with no thread-id keeps NONE rather than acquiring a fresh one per read."""
    from macf.amail import store
    from macf.amail.models import Message
    home, _ = delivered
    m = Message(sender="peer@agents.test", to=[f"{AGENT}@{DOMAIN}"],
                subject="threaded", body="hi")
    minted = m.thread_id
    assert minted, "composition still mints"
    store.deliver(home, m)
    first = store.read_all(home)[0].thread_id
    second = store.read_all(home)[0].thread_id
    assert first == second == minted, "thread id must survive reading, unchanged"


def test_reading_a_message_without_a_thread_id_does_not_invent_one(deploy):
    from macf.amail.models import Message
    stored = ("From: peer@agents.test\r\nTo: a@b.test\r\nSubject: s\r\n"
              "Message-ID: mid-1\r\n\r\nbody")
    a = Message.deserialize(stored)
    b = Message.deserialize(stored)
    assert a.thread_id == b.thread_id == "", \
        "reading is not composing: an absent thread id must stay absent"


def test_the_socket_carries_no_delivered_mail_operations(delivered, deploy):
    # The socket is the access path to the BROKER's stores only. This test
    # once asserted that list_messages omitted internet mail — the half-step;
    # the realignment removed the delivered-mail operations outright, and
    # status_counts no longer counts the agent's store either.
    from macf.amail.broker import Broker
    assert not hasattr(Broker, "list_messages")
    assert not hasattr(Broker, "read_message")
    deploy.broker_config.inbound_quarantine = deploy.quarantine_dir
    deploy.broker_config.inbound_handoff = deploy.handoff_dir
    resp = Broker(deploy.broker_config).status_counts(AGENT)
    assert resp["ok"] is True
    assert "internet" not in resp and "messages" not in resp, \
        "own-store counts crossing the socket is the custody deviation returning"


# ---- push-wake ships disabled: the no-path-produces-it control -------------

def test_push_wake_disabled_by_default_degrades_grant_to_pull(deploy):
    # The control for shipping with the wake unbuilt: even a fully granted,
    # eligible sender must deliver as pull, with the reason visible.
    raw = make_raw(sender=PUSHY)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == HANDED_OFF
    assert result["delivery_class"] == DELIVER_PULL
    assert "push-wake is disabled" in result["reason"]


def test_push_wake_when_enabled_grants_the_class(deploy):
    deploy.push_wake_enabled = True
    raw = make_raw(sender=PUSHY)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["delivery_class"] == DELIVER_PUSH_WAKE


def test_status_counts_track_pickup_ingest_and_quarantine(deploy):
    from macf.amail.broker import Broker
    from macf.amail.client import ingest
    deploy.broker_config.inbound_quarantine = deploy.quarantine_dir
    deploy.broker_config.inbound_handoff = deploy.handoff_dir
    inbound.process_entry(deploy, *spool(deploy, make_raw()))  # handed off
    inbound.process_entry(deploy, *spool(deploy,               # quarantined
        make_raw(sender="stranger@example.org", body="refused")))
    broker = Broker(deploy.broker_config)
    resp = broker.status_counts(AGENT)
    assert resp["ok"] is True
    assert resp["pending_pickup"] == 1
    assert resp["quarantined"] == 1
    # After the recipient ingests, the box drains — and the delivered copy is
    # visible where custody now lives: the agent's own store, via the
    # filesystem, not through any socket count.
    from macf.amail.client import list_delivered_internet
    home = deploy.broker_config.agent_homes[AGENT]
    ingest(home, deploy.handoff_dir / AGENT)
    resp = broker.status_counts(AGENT)
    assert resp["pending_pickup"] == 0
    assert len(list_delivered_internet(home)) == 1


def test_status_counts_damaged_quarantine_metadata_still_counts(deploy):
    # A refusal artifact with unreadable metadata is still a refusal
    # artifact; dropping it from the count rebuilds the silent-drop
    # ambiguity one layer up.
    from macf.amail.broker import Broker
    deploy.broker_config.inbound_quarantine = deploy.quarantine_dir
    deploy.quarantine_dir.mkdir(parents=True, exist_ok=True)
    (deploy.quarantine_dir / "broken.json").write_text("{not json")
    resp = Broker(deploy.broker_config).status_counts(AGENT)
    assert resp["quarantined"] == 1


# ---- unified delivery: agent mail travels the same pickup box -------------
# The pickup-box model covered internet mail only; agent-to-agent delivery
# still wrote across a uid boundary, which worked solely because the broker
# ran as root and was invisible because nothing exercised the path.

@pytest.fixture
def two_agents(tmp_path):
    """Two local agents with a mutual contact list, delivery by pickup box."""
    from macf.amail.broker import Broker, BrokerConfig
    homes = {a: tmp_path / a for a in ("alpha", "beta")}
    for h in homes.values():
        (h / "Maildir").mkdir(parents=True)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_addressing({
        "alpha": [f"beta@{DOMAIN}"], "beta": [f"alpha@{DOMAIN}"]}))
    contacts.chmod(0o644)
    import os as _os
    cfg = BrokerConfig(
        domain=DOMAIN, agent_homes=homes, contacts_path=contacts,
        audit_path=tmp_path / "audit.jsonl",
        inbound_handoff=tmp_path / "handoff",
        inbound_quarantine=tmp_path / "quarantine",
        agent_uids={_os.getuid(): "alpha"})
    return {"cfg": cfg, "broker": Broker(cfg), "homes": homes,
            "contacts": contacts, "tmp": tmp_path}


def _bundle(sender="alpha", to="beta"):
    from macf.amail.models import Message
    return Message(sender=f"{sender}@{DOMAIN}", to=[f"{to}@{DOMAIN}"],
                   subject="unified", body="one mechanism")


def test_submission_lands_in_the_pickup_box_not_the_recipient_home(two_agents):
    from macf.amail import store
    r = two_agents["broker"].submit("alpha", _bundle())
    assert r["ok"] is True
    box = two_agents["cfg"].inbound_handoff / "beta"
    assert len(list(box.glob("*.amsg"))) == 1, "delivery must end in the box"
    assert len(list(box.glob("*.json"))) == 1, "and carry its sidecar"
    assert store.read_all(two_agents["homes"]["beta"]) == [], \
        "the broker must not write into the recipient's own store"


def test_the_recipient_executes_the_custody_transfer(two_agents):
    from macf.amail import store
    from macf.amail.client import ingest
    two_agents["broker"].submit("alpha", _bundle())
    box = two_agents["cfg"].inbound_handoff / "beta"
    results = ingest(two_agents["homes"]["beta"], box,
                     contacts_path=two_agents["contacts"], agent="beta")
    assert [r["ingested"] for r in results] == [True]
    msgs = store.read_all(two_agents["homes"]["beta"])
    assert [m.subject for m in msgs] == ["unified"]
    assert list(box.glob("*")) == [], "box drained only after the copy exists"


def test_ingest_refuses_a_tampered_bundle_and_leaves_it_in_the_box(two_agents):
    from macf.amail import store
    from macf.amail.client import ingest
    two_agents["broker"].submit("alpha", _bundle())
    box = two_agents["cfg"].inbound_handoff / "beta"
    amsg = next(box.glob("*.amsg"))
    amsg.write_bytes(amsg.read_bytes().replace(b"one mechanism", b"tampered!!!!"))
    results = ingest(two_agents["homes"]["beta"], box,
                     contacts_path=two_agents["contacts"], agent="beta")
    assert results[0]["ingested"] is False
    assert "hash mismatch" in results[0]["reason"]
    assert store.read_all(two_agents["homes"]["beta"]) == []
    assert amsg.exists(), "evidence stays in the box rather than vanishing"


def test_ingest_works_with_no_broker_process_at_all(two_agents):
    """R4 extended to agent mail: custody transfer is a filesystem act, and
    signature verification must not need a broker round-trip or it breaks
    silently the first time the broker is down."""
    from macf.amail import store
    from macf.amail.client import ingest
    two_agents["broker"].submit("alpha", _bundle())
    del two_agents["broker"]          # nothing serving, nothing to call
    box = two_agents["cfg"].inbound_handoff / "beta"
    results = ingest(two_agents["homes"]["beta"], box,
                     contacts_path=two_agents["contacts"], agent="beta")
    assert results[0]["ingested"] is True
    assert len(store.read_all(two_agents["homes"]["beta"])) == 1


def test_ingest_records_three_distinct_key_states(two_agents, tmp_path):
    """keys_for's three states must not flatten: no key declared is not
    declared-and-failed is not verified."""
    from macf.amail.client import _verify_at_ingest
    from macf.amail.crypto import generate_keypair, load_private_key, sign
    from macf.amail.trust import TrustClass

    # (a) unsigned, no key declared -> UNVERIFIED, nothing concluded
    v = _verify_at_ingest(_bundle(), two_agents["contacts"], "beta")
    assert v["trust"] == TrustClass.UNVERIFIED.value and v["keys_declared"] == 0

    # (b) key declared, message unsigned -> SUSPECT (a broken commitment)
    key = tmp_path / "alpha.pem"
    pub = generate_keypair(key)
    two_agents["contacts"].write_text(_addressing({
        "beta": [{"address": f"alpha@{DOMAIN}", "key": pub}],
        "alpha": [f"beta@{DOMAIN}"]}))
    v = _verify_at_ingest(_bundle(), two_agents["contacts"], "beta")
    assert v["trust"] == TrustClass.SUSPECT.value and v["keys_declared"] == 1

    # (c) signed and verifiable -> ATTESTED
    m = _bundle()
    m.signature = sign(m, load_private_key(key))
    v = _verify_at_ingest(m, two_agents["contacts"], "beta")
    assert v["trust"] == TrustClass.ATTESTED.value

    # (d) signed but the signature does not check out -> SUSPECT, and NOT the
    #     same answer as (a): "we looked and it did not add up" is the case
    #     worth waking someone for.
    m2 = _bundle()
    m2.signature = sign(m, load_private_key(key))   # signature for a different body
    m2.body = "swapped after signing"
    v = _verify_at_ingest(m2, two_agents["contacts"], "beta")
    assert v["trust"] == TrustClass.SUSPECT.value
    assert "did NOT verify" in v["reason"]


def test_ingest_preserves_the_signature_for_re_verification(two_agents, tmp_path):
    """The verdict must not collapse to a boolean: a declared key can change,
    so the evidence has to survive the transfer."""
    from macf.amail import store
    from macf.amail.client import ingest
    from macf.amail.crypto import generate_keypair, load_private_key, sign
    key = tmp_path / "alpha.pem"
    pub = generate_keypair(key)
    two_agents["contacts"].write_text(_addressing({
        "beta": [{"address": f"alpha@{DOMAIN}", "key": pub}],
        "alpha": [f"beta@{DOMAIN}"]}))
    m = _bundle()
    m.signature = sign(m, load_private_key(key))
    two_agents["broker"].submit("alpha", m)
    box = two_agents["cfg"].inbound_handoff / "beta"
    ingest(two_agents["homes"]["beta"], box,
           contacts_path=two_agents["contacts"], agent="beta")
    stored = store.read_all(two_agents["homes"]["beta"])[0]
    assert stored.signature, "signature discarded; re-verification impossible"
    from macf.amail.crypto import verify
    assert verify(stored, stored.signature, [pub])


def test_a_trust_disagreement_with_the_broker_is_surfaced(two_agents, tmp_path, capsys):
    """The recipient verifying with its OWN keys is only worth doing if a
    disagreement with the broker's read is visible — that is what a stale or
    compromised broker looks like from this side."""
    from macf.amail.client import ingest
    two_agents["broker"].submit("alpha", _bundle())
    box = two_agents["cfg"].inbound_handoff / "beta"
    sidecar = next(box.glob("*.json"))
    meta = json.loads(sidecar.read_text())
    meta["broker_trust"] = "attested"          # broker claims more than we can confirm
    sidecar.write_text(json.dumps(meta))
    ingest(two_agents["homes"]["beta"], box,
           contacts_path=two_agents["contacts"], agent="beta")
    err = capsys.readouterr().err
    assert "trust disagreement" in err
    assert "attested" in err


def test_no_component_writes_outside_its_own_stores(two_agents):
    """The no-privileged-component property, mechanised for AGENT mail.

    The broker may touch only its own handoff and quarantine trees; the
    recipient's home must be untouched until the recipient itself ingests.
    """
    two_agents["broker"].submit("alpha", _bundle())
    beta_home = two_agents["homes"]["beta"]
    written = [p for p in beta_home.rglob("*") if p.is_file()]
    assert written == [], f"broker wrote into the recipient's home: {written}"


# ---- the orphan sweep ------------------------------------------------------
# The spec required this sweep for four drafts and nothing implemented it,
# while a later design leaned on it as the backstop for an unattended watcher.
# A specified-but-absent alarm is worse than a missing one: the design above it
# assumes cover it does not have.

def test_sweep_does_not_fire_on_fresh_entries(deploy):
    """KNOWN-ANSWER FIRST. A sweep that alarms on everything would pass every
    positive test below while telling an operator nothing."""
    spool(deploy, make_raw())
    report = inbound.sweep_aged(deploy)
    assert report["aged_spool"] == [] and report["aged_pickup"] == []
    assert report["alerts"] == 0


def test_aged_spool_entry_is_quarantined_and_alerts(deploy, capsys):
    eml, sidecar = spool(deploy, make_raw())
    # One variable: the clock. Nothing about the entry itself is unusual.
    future = time.time() + deploy.spool_age_bound_s + 60
    report = inbound.sweep_aged(deploy, now=future)
    assert report["aged_spool"] == [eml.name]
    assert report["alerts"] == 1
    assert not eml.exists(), "an aged entry must leave the spool"
    assert list(deploy.quarantine_dir.glob("*.eml")), \
        "aged entries move to quarantine; content is never deleted"
    assert "MACF" in capsys.readouterr().err


def test_aged_spool_entry_is_audited_so_conservation_still_balances(deploy):
    """An aged entry that left the spool with no terminal record would make the
    ledger go red for a message the system actually handled correctly."""
    eml, _ = spool(deploy, make_raw())
    inbound.sweep_aged(deploy, now=time.time() + deploy.spool_age_bound_s + 60)
    records = [json.loads(l) for l in
               deploy.broker_config.audit_path.read_text().splitlines()]
    terminals = [r for r in records if r.get("decision") == QUARANTINED]
    assert len(terminals) == 1
    assert "aged out of the spool" in terminals[0]["reason"]


def test_aged_pickup_entry_alerts_but_is_left_in_the_box(deploy, capsys):
    """Custody was handed to the recipient. Pulling mail back out of its box
    would undo the transfer the whole model rests on, so the alert IS the
    remedy rather than a repair."""
    inbound.process_entry(deploy, *spool(deploy, make_raw()))
    box = deploy.handoff_dir / AGENT
    entry = next(box.glob("*.eml"))
    report = inbound.sweep_aged(
        deploy, now=time.time() + deploy.pickup_age_bound_s + 60)
    assert report["aged_pickup"] == [f"{AGENT}/{entry.name}"]
    assert entry.exists(), "an aged pickup entry must NOT be taken back"
    assert "stopped draining, or cannot read its own box" in capsys.readouterr().err, \
        "the alert must name the mis-provisioned box, which is silent at the sender"


def test_the_two_populations_are_reported_separately(deploy):
    """A dead consumer and a non-draining recipient are different faults with
    different remedies; one combined count would hide which one happened."""
    spool(deploy, make_raw(body="stuck in spool"))
    inbound.process_entry(deploy, *spool(deploy, make_raw(body="stuck in box")))
    far = time.time() + max(deploy.spool_age_bound_s,
                            deploy.pickup_age_bound_s) + 60
    report = inbound.sweep_aged(deploy, now=far)
    assert len(report["aged_spool"]) == 1
    assert len(report["aged_pickup"]) == 1
    assert report["alerts"] == 2


# ---- the sender's canonical copy, and the fate it cannot self-determine ----
# Required by the spec since draft 0.4 and never built; the peer found it by
# looking for a Sent concept and discovering there was none.

def test_the_sender_keeps_its_own_copy(tmp_path):
    from macf.amail import store
    from macf.amail.models import Message
    home = tmp_path / "sender"
    (home / "Maildir").mkdir(parents=True)
    m = Message(sender="me@agents.test", to=["you@example.org"],
                subject="outbound", body="my own words")
    store.deliver_sent(home, m)
    sent = store.read_sent(home)
    assert [x.subject for x in sent] == ["outbound"]
    assert sent[0].body == "my own words"


def test_the_sent_copy_is_readable_with_no_broker_in_existence(tmp_path):
    """The agent authored it, so nothing about reading it may require a service."""
    from macf.amail import store
    from macf.amail.models import Message
    home = tmp_path / "sender"
    (home / "Maildir").mkdir(parents=True)
    store.deliver_sent(home, Message(sender="me@agents.test", to=["you@example.org"],
                                     subject="offline", body="x"))
    # No broker object is constructed anywhere in this test, deliberately.
    assert len(store.read_sent(home)) == 1


def test_sent_and_received_do_not_contaminate_each_other(tmp_path):
    """Direction is a different KIND of artifact, not a flag: a sent copy must
    not appear in the inbox listing, and received mail must not appear in sent."""
    from macf.amail import store
    from macf.amail.models import Message
    home = tmp_path / "sender"
    (home / "Maildir").mkdir(parents=True)
    store.deliver(home, Message(sender="peer@agents.test", to=["me@agents.test"],
                                subject="INBOUND", body="to me"))
    store.deliver_sent(home, Message(sender="me@agents.test", to=["peer@agents.test"],
                                     subject="OUTBOUND", body="from me"))
    assert [m.subject for m in store.read_all(home)] == ["INBOUND"]
    assert [m.subject for m in store.read_sent(home)] == ["OUTBOUND"]


def test_disposition_is_a_history_not_a_last_value(tmp_path):
    """A bounce after three deferrals is a different fact from an immediate
    bounce, and only a sequence can tell them apart."""
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.client import sent_disposition
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    b = Broker(cfg)
    for state in ("submitted", "deferred", "deferred", "bounced"):
        b.record_disposition("alpha", "msg-1", state, detail=f"{state} detail",
                             recipients=["you@example.org"])
    rec = sent_disposition(cfg.dispositions_dir, "msg-1")
    assert [h["state"] for h in rec["recipients"]["you@example.org"]["history"]] == \
        ["submitted", "deferred", "deferred", "bounced"]


def test_disposition_is_recorded_per_recipient_not_per_message(tmp_path):
    """amail spec O5d.8 "disposition-is-per-recipient". Delivered to one and bounced
    for another is the ordinary case, and one shared history cannot hold it."""
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.client import sent_disposition
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    b = Broker(cfg)
    b.record_disposition("alpha", "msg-multi", "submitted",
                         recipients=["a@example.org", "b@example.org"])
    b.record_disposition("alpha", "msg-multi", "delivered", recipients=["a@example.org"])
    b.record_disposition("alpha", "msg-multi", "bounced", recipients=["b@example.org"])
    per = sent_disposition(cfg.dispositions_dir, "msg-multi")["recipients"]
    assert [h["state"] for h in per["a@example.org"]["history"]] == ["submitted", "delivered"]
    assert [h["state"] for h in per["b@example.org"]["history"]] == ["submitted", "bounced"]


def test_a_message_level_refusal_writes_a_record_for_every_recipient(tmp_path):
    """amail spec O5d.8a "message-level-refusal-writes-a-record-for-every-recipient".
    The refusal is a decision about the submission as a UNIT, so
    a permitted recipient with no record at all would leave the derived view
    with nothing to read."""
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.client import sent_disposition
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    Broker(cfg).record_disposition(
        "alpha", "msg-denied", "denied", detail="b@example.org is not a contact",
        recipients=["a@example.org", "b@example.org"])
    per = sent_disposition(cfg.dispositions_dir, "msg-denied")["recipients"]
    assert set(per) == {"a@example.org", "b@example.org"}
    assert all(e["history"][-1]["state"] == "denied" for e in per.values())


def test_the_derived_view_is_the_least_successful_outcome(tmp_path):
    """amail spec O5d.8b "message-level-view-is-the-least-successful-outcome".
    Any recipient bounced makes the message bounced; delivered
    requires that every recipient reached it. A summary reporting success while
    a recipient bounced is the silent-delivery failure, one level up."""
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.client import sent_disposition, derive_message_state
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    b = Broker(cfg)
    b.record_disposition("alpha", "m", "delivered", recipients=["a@example.org"])
    b.record_disposition("alpha", "m", "bounced", recipients=["b@example.org"])
    assert derive_message_state(sent_disposition(cfg.dispositions_dir, "m")) == "bounced"

    # The paired positive: without the bounce the same code must say delivered,
    # or "bounced" proves only that the function returns a constant.
    b.record_disposition("alpha", "m2", "delivered",
                         recipients=["a@example.org", "b@example.org"])
    assert derive_message_state(sent_disposition(cfg.dispositions_dir, "m2")) == "delivered"


def test_an_unrecognised_state_makes_the_derivation_unknown_not_optimistic(tmp_path, capsys):
    """A state this version does not know must not be SKIPPED — skipping it lets
    an unrecognised outcome silently improve the summary."""
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.client import sent_disposition, derive_message_state
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    b = Broker(cfg)
    b.record_disposition("alpha", "m3", "bounced", recipients=["a@example.org"])
    b.record_disposition("alpha", "m3", "quarantined-by-a-future-version",
                         recipients=["b@example.org"])
    assert derive_message_state(sent_disposition(cfg.dispositions_dir, "m3")) is None
    assert "unrecognised state" in capsys.readouterr().err


def test_an_unrecorded_disposition_reads_as_none_not_as_delivered(tmp_path):
    """None is a real answer. A caller treating it as success would invent the
    silent delivery this store exists to prevent."""
    from macf.amail.client import sent_disposition
    (tmp_path / "disp").mkdir()
    assert sent_disposition(tmp_path / "disp", "msg-never-sent") is None


def test_the_disposition_is_readable_by_the_sender_but_broker_owned(tmp_path):
    from macf.amail.broker import Broker, BrokerConfig
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    f = Broker(cfg).record_disposition("alpha", "msg-2", "submitted",
                                       recipients=["you@example.org"])
    import stat as _stat
    mode = f.stat().st_mode
    assert mode & _stat.S_IROTH, "the sender must be able to read its own mail's fate"
    assert not (mode & _stat.S_IWOTH), "but it must not be able to forge it"


def test_an_unreadable_disposition_record_is_never_overwritten(tmp_path, capsys):
    """THE ONE THAT MATTERS. A record that exists and cannot be parsed used to be
    silently replaced with an empty history, and the next write committed that
    emptiness -- evidence destruction inside the function whose job is to keep
    evidence, which is the audit log's own rotation defect one subsystem later.

    Refusing must be LOUD and must leave the bytes alone."""
    from macf.amail.broker import Broker, BrokerConfig
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    b = Broker(cfg)
    b.record_disposition("alpha", "msg-corrupt", "submitted",
                         recipients=["you@example.org"])
    f = cfg.dispositions_dir / "msg-corrupt.json"
    f.write_text("{ this is not json")           # simulate a truncated write
    corrupt_bytes = f.read_bytes()

    with pytest.raises(ValueError):
        b.record_disposition("alpha", "msg-corrupt", "delivered",
                             recipients=["you@example.org"])

    assert f.read_bytes() == corrupt_bytes, \
        "the unreadable record must survive untouched; it is the only copy"
    err = capsys.readouterr().err
    assert "REFUSING to overwrite" in err
    assert "cannot be read" in err


def test_a_first_disposition_is_not_warned_about(tmp_path, capsys):
    """The paired positive for the test above, and it is the reason the three
    states are kept distinct: a missing record is EXPECTED (this is the first
    fate for this message), so warning about it would train readers to ignore
    the two warnings that matter."""
    from macf.amail.broker import Broker, BrokerConfig
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    Broker(cfg).record_disposition("alpha", "msg-first", "submitted",
                                   recipients=["you@example.org"])
    assert capsys.readouterr().err == ""


def test_no_recipients_records_nothing_and_says_so(tmp_path, capsys):
    """A fate belongs to a message-recipient PAIR — amail spec O5d.8c
    "conservation-unit-is-the-message-recipient-pair". With no
    recipient there is no pair, and a placeholder row could never reach a
    terminal state -- it would sit in the conservation ledger forever."""
    from macf.amail.broker import Broker, BrokerConfig
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    assert Broker(cfg).record_disposition("alpha", "msg-none", "submitted") is None
    assert "no recipients given" in capsys.readouterr().err


def test_the_content_hash_is_written_once_and_never_rewritten(tmp_path):
    """amail spec O5c.7a "the-hash-lives-where-its-verifier-can-reach-it".
    A hash that changes is not evidence of anything, so a later
    call carrying a different value must not be able to relabel what was sent."""
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.client import sent_disposition
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    b = Broker(cfg)
    b.record_disposition("alpha", "msg-h", "submitted", recipients=["a@example.org"],
                         content_sha256="a" * 64)
    b.record_disposition("alpha", "msg-h", "delivered", recipients=["a@example.org"],
                         content_sha256="b" * 64)
    assert sent_disposition(cfg.dispositions_dir, "msg-h")["content_sha256"] == "a" * 64


def test_concurrent_appends_do_not_lose_records(tmp_path):
    """amail spec O5d.10 "disposition-appends-are-safe-under-concurrent-writers".
    The audit log's rotation lost 42 of 50 records under
    ordinary concurrency with no attacker involved; this store has the same
    read-modify-write shape and must not repeat it."""
    import threading
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.client import sent_disposition
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=tmp_path / "disp")
    b = Broker(cfg)
    n = 40

    def append(i):
        b.record_disposition("alpha", "msg-race", "deferred", detail=str(i),
                             recipients=["a@example.org"])

    threads = [threading.Thread(target=append, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    history = sent_disposition(cfg.dispositions_dir, "msg-race")["recipients"]["a@example.org"]["history"]
    assert len(history) == n, f"lost {n - len(history)} of {n} concurrent records"
    assert sorted(int(h["detail"]) for h in history) == list(range(n))


def test_a_missing_disposition_store_is_announced_not_silent(tmp_path, capsys):
    """Submitting mail while recording no fate rebuilds the silent drop on the
    sending side, so the absence must be loud."""
    from macf.amail.broker import Broker, BrokerConfig
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=None)
    assert Broker(cfg).record_disposition("alpha", "msg-3", "submitted") is None
    assert "no disposition store configured" in capsys.readouterr().err


# ---- Phase 1: send-by-copy custody, wired ----------------------------------
# `deliver_sent` and `record_disposition` both existed, were tested, and had
# ZERO non-test call sites -- a reader with no writer, which returns an
# emptiness that reads as "nothing was sent" rather than "this is not wired".

def _custody_fixture(tmp_path, monkeypatch, *, ok=True, refused=None, raises=False):
    """A send path with the socket replaced, so the custody sequence is what is
    under test rather than the broker."""
    from macf.amail import client
    home = tmp_path / "sender"
    (home / "Maildir").mkdir(parents=True)

    def fake_submit(sender, message, socket_path, timeout=10.0):
        if raises:
            raise client.BrokerUnavailable("broker is down")
        return {"ok": ok, "message_id": "msg-BROKER-MINTED",
                "refused": refused or []}

    monkeypatch.setattr(client, "submit", fake_submit)
    return home


def test_the_sent_copy_exists_before_the_broker_is_asked(tmp_path, monkeypatch):
    """amail spec O5c.6 "the-sent-copy-is-written-before-submission". Write-after
    loses the record of anything that died mid-flight, which is exactly the
    case a sender most needs evidence of."""
    from macf.amail import client, store
    from macf.amail.models import Message
    home = tmp_path / "sender"
    (home / "Maildir").mkdir(parents=True)
    seen = {}

    def fake_submit(sender, message, socket_path, timeout=10.0):
        # AT THE MOMENT OF SUBMISSION the copy must already be on disk.
        seen["copies"] = len(store.read_sent(home))
        seen["state"] = store.read_sent_sidecar(
            home, store.read_sent_with_state(home)[0]["name"])["state"]
        return {"ok": True, "message_id": "msg-BROKER-MINTED"}

    monkeypatch.setattr(client, "submit", fake_submit)
    client.send_with_custody(home, "alpha",
                             Message(sender="me@agents.test", to=["you@example.org"],
                                     subject="s", body="b"),
                             tmp_path / "sock")
    assert seen["copies"] == 1, "the copy must exist BEFORE the broker is asked"
    assert seen["state"] == client.ATTEMPTED, \
        "and the annotation must already say an attempt is in flight"


def test_a_crash_before_the_broker_answers_leaves_attempted_not_refused(tmp_path, monkeypatch):
    """The client must never assert a broker decision it did not hear. `refused`
    written here would be the same invention the disposition store exists to
    prevent, committed on the other side."""
    from macf.amail import client, store
    from macf.amail.models import Message
    home = _custody_fixture(tmp_path, monkeypatch, raises=True)
    with pytest.raises(client.BrokerUnavailable):
        client.send_with_custody(home, "alpha",
                                 Message(sender="me@agents.test", to=["you@example.org"],
                                         subject="s", body="b"),
                                 tmp_path / "sock")
    entry = store.read_sent_with_state(home)[0]
    assert entry["sidecar"]["state"] == client.ATTEMPTED
    assert len(store.read_sent(home)) == 1, "the copy survives the failed send"


def test_a_refusal_is_recorded_on_the_agents_own_copy(tmp_path, monkeypatch):
    from macf.amail import client, store
    from macf.amail.models import Message
    home = _custody_fixture(tmp_path, monkeypatch, ok=False,
                            refused=["you@example.org is not a contact"])
    client.send_with_custody(home, "alpha",
                             Message(sender="me@agents.test", to=["you@example.org"],
                                     subject="s", body="b"),
                             tmp_path / "sock")
    side = store.read_sent_with_state(home)[0]["sidecar"]
    assert side["state"] == client.REFUSED
    assert side["refused"] == ["you@example.org is not a contact"]


def test_both_message_ids_are_recorded_so_the_two_records_can_be_joined(tmp_path, monkeypatch):
    """The broker RE-MINTS message_id, so the agent's copy carries an id that
    matches no disposition record. Recording both is what lets the agent find
    the fate of its own mail."""
    from macf.amail import client, store
    from macf.amail.models import Message
    home = _custody_fixture(tmp_path, monkeypatch)
    m = Message(sender="me@agents.test", to=["you@example.org"], subject="s", body="b")
    local = m.message_id
    client.send_with_custody(home, "alpha", m, tmp_path / "sock")
    side = store.read_sent_with_state(home)[0]["sidecar"]
    assert side["local_message_id"] == local
    assert side["broker_message_id"] == "msg-BROKER-MINTED"
    assert side["local_message_id"] != side["broker_message_id"]


def test_the_content_hash_survives_the_brokers_reminting(tmp_path, monkeypatch):
    """THE DEVIATION, TESTED. Byte-equality of the serialized message is
    unsatisfiable because the broker re-mints message_id and date. The hash
    covers `signing_payload` -- the named canonical subset -- which excludes
    exactly those two fields, so it still means something after canonicalisation."""
    from macf.amail import client, store
    from macf.amail.models import Message
    from macf.amail.crypto import signing_payload
    import hashlib
    home = _custody_fixture(tmp_path, monkeypatch)
    m = Message(sender="me@agents.test", to=["you@example.org"], subject="s", body="b")
    result = client.send_with_custody(home, "alpha", m, tmp_path / "sock")

    # The broker's canonicalisation, simulated: new id, new date, same content.
    remined = Message(sender=m.sender, to=list(m.to), subject=m.subject, body=m.body)
    assert remined.message_id != m.message_id, "precondition: the ids differ"
    assert hashlib.sha256(signing_payload(remined)).hexdigest() == result["content_sha256"]

    # The paired NEGATIVE: change the content and the hash must move, or the
    # comparison proves only that it returns a constant.
    altered = Message(sender=m.sender, to=list(m.to), subject=m.subject, body="tampered")
    assert hashlib.sha256(signing_payload(altered)).hexdigest() != result["content_sha256"]


def test_the_agent_side_reconciliation_goes_red_in_both_directions(tmp_path, monkeypatch):
    """amail spec O5d.6a "composed-never-submitted-is-reconciled-agent-side", and the
    control V19c asks for: BOTH directions, run as the agent with no broker."""
    from macf.amail import client, store
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.models import Message
    home = _custody_fixture(tmp_path, monkeypatch)
    disp = tmp_path / "disp"
    cfg = BrokerConfig(domain="agents.test", dispositions_dir=disp)

    m = Message(sender="me@agents.test", to=["you@example.org"], subject="s", body="b")
    client.send_with_custody(home, "alpha", m, tmp_path / "sock")

    # SUBMITTED with no disposition recorded -> red, naming the id.
    red = client.reconcile_sent(home, disp)
    assert red["ok"] is False
    assert red["missing_disposition"] == ["msg-BROKER-MINTED"]

    # The paired GREEN: record the fate and the same check must go clean.
    Broker(cfg).record_disposition("alpha", "msg-BROKER-MINTED", "delivered",
                                   recipients=["you@example.org"])
    green = client.reconcile_sent(home, disp)
    assert green["ok"] is True and green["submitted"] == 1

    # The OTHER direction: a copy never submitted must NOT have a disposition.
    store.deliver_sent(home, Message(sender="me@agents.test", to=["x@example.org"],
                                     subject="draft", body="never sent"))
    name = [e["name"] for e in store.read_sent_with_state(home) if e["sidecar"] is None][0]
    store.write_sent_sidecar(home, name, {"state": client.COMPOSED,
                                          "local_message_id": "msg-LOCAL-ONLY"})
    assert client.reconcile_sent(home, disp)["composed"] == 1, \
        "composed-never-submitted is EXPECTED, not a shortfall"
    Broker(cfg).record_disposition("alpha", "msg-LOCAL-ONLY", "delivered",
                                   recipients=["x@example.org"])
    surplus = client.reconcile_sent(home, disp)
    assert surplus["ok"] is False
    assert surplus["unexpected_disposition"] == ["msg-LOCAL-ONLY"]


def test_an_unresolved_attempt_is_named_rather_than_sorted(tmp_path, monkeypatch):
    """amail spec O13.10 "the-outbound-ledger's-left-edge". A submission that died
    before the broker's first look is indistinguishable from one it lost, and
    folding it into either column would balance the ledger by deciding a
    question the system cannot answer."""
    from macf.amail import client
    from macf.amail.models import Message
    home = _custody_fixture(tmp_path, monkeypatch, raises=True)
    with pytest.raises(client.BrokerUnavailable):
        client.send_with_custody(home, "alpha",
                                 Message(sender="me@agents.test", to=["you@example.org"],
                                         subject="s", body="b"),
                                 tmp_path / "sock")
    out = client.reconcile_sent(home, tmp_path / "disp")
    assert len(out["unresolved"]) == 1
    assert out["composed"] == 0 and out["submitted"] == 0, \
        "it must be in NEITHER column, or the balance is a false one"


def test_the_real_send_path_keeps_a_copy_and_records_a_fate(tmp_path, monkeypatch):
    """THE PATH TEST, and it replaces a weaker guard that I nearly shipped.

    The first version of this asserted `deliver_sent` had a non-test CALL SITE.
    That guard passed the moment `send_with_custody` existed -- while
    `send_with_custody` itself had no caller, so the CLI still sent mail keeping
    no copy. The property is "the write is ON the live send path"; the guard
    measured "something references the function", which is the easier adjacent
    property, and it went green while the thing it protects was false.

    Same shape as the round-1 finding about the pre-send gate: the corpus
    certifies the scanner, only the path certifies the gate. So this drives the
    REAL CLI entry point and asserts the artifacts exist afterwards."""
    import argparse
    from macf import cli
    from macf.amail import store, client
    from macf.amail.broker import Broker, BrokerConfig

    home = tmp_path / "home"
    (home / "Maildir").mkdir(parents=True)
    peer_home = tmp_path / "peer"
    (peer_home / "Maildir").mkdir(parents=True)
    disp = tmp_path / "disp"
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_addressing({"alpha": ["peer@agents.test"]}))
    broker = Broker(BrokerConfig(domain="agents.test", dispositions_dir=disp,
                                 contacts_path=contacts,
                                 inbound_handoff=tmp_path / "handoff",
                                 agent_homes={"alpha": home, "peer": peer_home}))

    monkeypatch.setattr(cli, "_amail_config", lambda: {
        "agent": "alpha", "domain": "agents.test", "home": str(home),
        "socket": str(tmp_path / "sock"), "signing_key": None})
    # The socket is replaced by the real broker object: the transport is not
    # what is under test, the SEQUENCE is.
    monkeypatch.setattr(client, "submit",
                        lambda sender, message, socket_path, timeout=10.0:
                        broker.submit(sender, message))

    args = argparse.Namespace(to=["peer@agents.test"], subject="hi",
                              body="real path", body_file=None, reply_to=None,
                              json=False)
    assert cli.cmd_amail_send(args) == 0

    # 1. The agent kept its own copy, from the REAL entry point.
    copies = store.read_sent(home)
    assert [m.body for m in copies] == ["real path"]

    # 2. Its annotation reached `submitted`, so a crash is distinguishable.
    entry = store.read_sent_with_state(home)[0]
    assert entry["sidecar"]["state"] == client.SUBMITTED

    # 3. The broker recorded a fate, per recipient, joined by the id it minted.
    rec = client.sent_disposition(disp, entry["sidecar"]["broker_message_id"])
    assert rec is not None, "the send path must WRITE a disposition, not just have one"
    assert list(rec["recipients"]) == ["peer@agents.test"]

    # 4. And the two records reconcile, as the agent, with no broker call.
    assert client.reconcile_sent(home, disp)["ok"] is True


def test_a_denied_submission_records_a_terminal_fate_for_every_recipient(tmp_path):
    """A DENY is TERMINAL and IS counted -- amail spec O5d.7
    "terminal-dispositions-are-enumerated-and-closed". A ledger that omitted
    refusals would let two implementations compute different balances from
    identical traffic, and a ledger whose value is that a discrepancy means
    something cannot afford an ambiguous denominator.

    Recorded against BOTH recipients even though only one offended, per spec
    O5d.8a "message-level-refusal-writes-a-record-for-every-recipient": the
    refusal is a decision about the submission as a unit."""
    from macf.amail.broker import Broker, BrokerConfig
    from macf.amail.client import sent_disposition, derive_message_state
    from macf.amail.models import Message

    home = tmp_path / "home"
    (home / "Maildir").mkdir(parents=True)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_addressing({"alpha": ["ok@agents.test"]}))
    disp = tmp_path / "disp"
    b = Broker(BrokerConfig(domain="agents.test", contacts_path=contacts,
                            dispositions_dir=disp, agent_homes={"alpha": home}))

    m = Message(sender="alpha@agents.test",
                to=["ok@agents.test", "stranger@example.org"],
                subject="s", body="b")
    result = b.submit("alpha", m)
    assert result["ok"] is False

    rec = sent_disposition(disp, result["message_id"])
    assert rec is not None, "a refusal is a FATE and must be recorded"
    assert set(rec["recipients"]) == {"ok@agents.test", "stranger@example.org"}, \
        "the permitted recipient needs a record too, or the derivation has nothing to read"
    assert all(e["history"][-1]["state"] == "denied" for e in rec["recipients"].values())
    assert derive_message_state(rec) == "denied"
