"""Tests for internet-inbound spool processing (macf.amail.inbound).

Known-answer FIRST: a suite that only exercises refusals cannot distinguish
a working authorizer from one that refuses everything, so the opening test
is an authorized message reaching the mailbox byte-exact. Refusal tests then
vary ONE thing each from that accepted baseline.

The push-eligibility and conservation tests are the spec's own named
controls: a generous contacts file MUST fail the run, and the conservation
check MUST go red when fed an audit log with a terminal record removed.
"""
import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from macf.amail import inbound
from macf.amail.broker import BrokerConfig
from macf.amail.inbound import (
    DELIVERED, DELIVER_PULL, DELIVER_PUSH_WAKE, QUARANTINED,
    InboundConfig, PushEligibilityError,
)

AUTHORITY = "mx.test.example"
HUMAN = "human@example.org"
PUSHY = "operator@example.org"
AGENT = "agent_alpha"
DOMAIN = "agents.test"


def make_raw(sender: str = HUMAN, dmarc: str = "pass",
             authority: str = AUTHORITY, extra_headers: str = "",
             body: str = "hello there") -> bytes:
    ar = f"Authentication-Results: {authority}; dmarc={dmarc}; spf=pass\r\n"
    return (f"{extra_headers}{ar}From: Someone <{sender}>\r\n"
            f"To: {AGENT}@{DOMAIN}\r\nSubject: test\r\n\r\n{body}").encode()


@pytest.fixture
def deploy(tmp_path):
    """A miniature inbound deployment: one agent, contacts, spool, audit."""
    home = tmp_path / "home" / AGENT
    (home / "Maildir").mkdir(parents=True)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(json.dumps({
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

def test_authorized_mail_is_delivered_byte_exact(deploy):
    raw = make_raw()
    eml, sidecar = spool(deploy, raw)
    result = inbound.process_entry(deploy, eml, sidecar)

    assert result["disposition"] == DELIVERED
    assert result["delivery_class"] == DELIVER_PULL
    delivered = list((deploy.broker_config.agent_homes[AGENT] / "Maildir" / "new").iterdir())
    assert len(delivered) == 1
    assert delivered[0].read_bytes() == raw
    # Spool consumed only after delivery.
    assert not eml.exists() and not sidecar.exists()


def test_delivery_sidecar_carries_authorization_and_untrusted_observations(deploy):
    raw = make_raw()
    inbound.process_entry(deploy, *spool(deploy, raw))
    sidecars = list((deploy.broker_config.agent_homes[AGENT] / "Maildir" / "sidecars").iterdir())
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
    assert decisions.count(DELIVERED) == 1


# ---- refusals: one variable each -------------------------------------------

def test_forged_later_verdict_cannot_override_first_instance(deploy):
    # Our authority stamps dmarc=fail FIRST; the sender pre-embedded a
    # forged pass claiming the same authority. First instance must win.
    forged = f"Authentication-Results: {AUTHORITY}; dmarc=pass\r\n"
    raw = make_raw(dmarc="fail") .replace(b"From:", forged.encode() + b"From:", 1)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == QUARANTINED
    assert "dmarc" in result["reason"]


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
    assert result["disposition"] == DELIVERED
    assert result["delivery_class"] == DELIVER_PUSH_WAKE


def test_generous_contacts_file_fails_the_run(deploy):
    # CONTROL: push granted to an address in the AGENT NAMESPACE must be
    # fatal -- not a warning, not a skip. This is the derivation, checkable.
    deploy.broker_config.contacts_path.write_text(json.dumps({
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
    assert result["disposition"] == DELIVERED
    assert result["delivery_class"] == DELIVER_PULL
    assert "degraded" in capsys.readouterr().err


def test_history_backstop_fails_closed_without_audit(deploy):
    deploy.push_wake_enabled = True
    deploy.broker_config.audit_path = None
    raw = make_raw(sender=PUSHY)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == DELIVERED
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
             if json.loads(l).get("decision") != DELIVERED]
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
    """One authorized internet message, delivered into the agent's store."""
    raw = make_raw(body="the readable one")
    inbound.process_entry(deploy, *spool(deploy, raw))
    return deploy.broker_config.agent_homes[AGENT], raw


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


def test_broker_listing_no_longer_carries_delivered_internet_mail(delivered, deploy):
    # The socket is the access path to the BROKER's stores only; delivered
    # mail must not be surfaced through it.
    from macf.amail.broker import Broker
    resp = Broker(deploy.broker_config).list_messages(AGENT)
    assert resp["ok"] is True
    assert "internet" not in resp


# ---- push-wake ships disabled: the no-path-produces-it control -------------

def test_push_wake_disabled_by_default_degrades_grant_to_pull(deploy):
    # The control for shipping with the wake unbuilt: even a fully granted,
    # eligible sender must deliver as pull, with the reason visible.
    raw = make_raw(sender=PUSHY)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["disposition"] == DELIVERED
    assert result["delivery_class"] == DELIVER_PULL
    assert "push-wake is disabled" in result["reason"]


def test_push_wake_when_enabled_grants_the_class(deploy):
    deploy.push_wake_enabled = True
    raw = make_raw(sender=PUSHY)
    result = inbound.process_entry(deploy, *spool(deploy, raw))
    assert result["delivery_class"] == DELIVER_PUSH_WAKE


def test_status_counts_attribute_quarantine_to_the_recipient(deploy):
    from macf.amail.broker import Broker
    deploy.broker_config.inbound_quarantine = deploy.quarantine_dir
    inbound.process_entry(deploy, *spool(deploy, make_raw()))  # delivered
    inbound.process_entry(deploy, *spool(deploy,               # quarantined
        make_raw(sender="stranger@example.org", body="refused")))
    resp = Broker(deploy.broker_config).status_counts(AGENT)
    assert resp["ok"] is True
    assert resp["internet"] == 1
    assert resp["quarantined"] == 1


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
