"""Non-delivery notices: the affirmative half, the safety half, and the seam.

Drafts through 0.7 contained ONLY prohibitions here, so an implementation that
emitted nothing under any circumstance was fully conformant -- which is exactly
the state that generated the section. Both halves are tested, and the silences
are tested as deliberately as the sends: silence is this module's most common
CORRECT outcome, which makes it the one most easily confused with a step that
never ran.
"""
from conftest import _addressing

import json

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from macf import opsec
from macf.amail import notices
from macf.amail.ratelimit import RateLimit, RateLimiter, RateLimitError


class TestTheGate:
    """`decide()` is free of I/O so every branch is exercisable. The branches
    ARE the specification."""

    def test_an_authenticated_aligned_sender_IS_notified(self):
        """amail spec O5g.3 "a-qualifying-refusal-produces-at-most-one-notice".
        THE AFFIRMATIVE HALF. Without it, a system that never notifies anyone
        satisfies every other rule in this module."""
        d = notices.decide(authenticated=True, sender="a@x.test",
                           refused_was_notice=False)
        assert d.emitted is True

    def test_an_unauthenticated_sender_is_NOT_notified(self):
        """amail spec O5g.1 "never-notify-an-unauthenticated-sender". A notice
        returned to a forged sender is delivered to the SPOOF VICTIM, who did
        nothing. This is the most important silence in the module."""
        d = notices.decide(authenticated=False, sender="forged@victim.test",
                           refused_was_notice=False)
        assert d.emitted is False
        assert "not authenticated" in d.reason

    def test_a_notice_is_never_itself_notified_about(self):
        """amail spec O5g.4 "a-notice-is-never-itself-notified-about". Two
        conformant systems, each refusing the other's notices as non-contacts
        and each notifying about it, is an infinite loop built entirely out of
        correct behaviour."""
        d = notices.decide(authenticated=True, sender="postmaster@peer.test",
                           refused_was_notice=True)
        assert d.emitted is False
        assert "loop" in d.reason

    def test_one_per_refusal_not_one_per_retry(self):
        d = notices.decide(authenticated=True, sender="a@x.test",
                           refused_was_notice=False, already_notified=True)
        assert d.emitted is False

    def test_the_notice_check_beats_the_authentication_check(self):
        """Order matters: a refused notice from an AUTHENTICATED peer must
        still not be answered, or two well-configured systems loop forever."""
        d = notices.decide(authenticated=True, sender="postmaster@peer.test",
                           refused_was_notice=True)
        assert d.emitted is False and "loop" in d.reason


class TestTheContent:
    def test_a_notice_carries_no_bytes_from_the_refused_message(self):
        """amail spec O5g.4a. The standard NDN quotes the original, which for a
        REFUSED message means echoing attacker bytes back outward under our
        name. Every mail library does this by default, which is why it is a
        control and not a style."""
        marker = "CANARY-8f3a9c2b-attacker-supplied"
        n = notices.compose_notice("a@x.test", notices.CODE_NOT_ACCEPTED,
                                   sender_address="postmaster@ours.test")
        blob = n.serialize()
        assert marker not in blob          # trivially true; the real check follows
        # The notice's ENTIRE body is broker-generated, so nothing from any
        # message can appear in it. Asserted structurally rather than by
        # searching for one canary a future author might forget to plant.
        assert n.body.startswith("Your message was not delivered.")
        assert notices.CODE_NOT_ACCEPTED in n.body
        assert len(n.body) < 400, "a notice that grew this much is quoting something"

    def test_a_notice_does_not_disclose_which_check_failed(self):
        """Disclosing the failed check turns every refusal into a probe result
        for the party the check refused."""
        n = notices.compose_notice("a@x.test", notices.CODE_NOT_ACCEPTED,
                                   sender_address="postmaster@ours.test")
        for leak in ("dmarc", "contact", "authserv", "spf", "quarantine",
                     "not a contact", "allowlist"):
            assert leak not in n.body.lower(), f"the notice discloses '{leak}'"

    def test_a_notice_is_marked_so_a_receiving_broker_can_recognise_one(self):
        n = notices.compose_notice("a@x.test", notices.CODE_NOT_ACCEPTED,
                                   sender_address="postmaster@ours.test")
        assert notices.is_notice(n) is True

    def test_a_correspondent_cannot_disguise_a_message_as_a_notice(self):
        """The marker is broker-MINTED. Inferring notice-ness from the subject
        would let any correspondent suppress its own notices by naming a
        message well -- and suppression is a denial of the notification
        channel, which is what the loop rule exists to bound."""
        from macf.amail.models import Message
        impostor = Message(sender="clever@x.test", to=["us@ours.test"],
                           subject=notices.NOTICE_SUBJECT, body="not really")
        assert notices.is_notice(impostor) is False


class TestEmissionGates:
    def _scan(self, m):
        return opsec.scan_message(m, env={"hostname": "buildbox42.internal",
                                          "username": "deployer"})

    def test_a_clean_notice_is_emitted(self):
        """The paired green. Every other test in this class is a refusal, and a
        refusal-shaped test passes when its instrument is dead."""
        d = notices.decide(authenticated=True, sender="a@x.test",
                           refused_was_notice=False)
        out = notices.emit(d, to_address="a@x.test",
                           sender_address="postmaster@ours.test",
                           scrub=self._scan)
        assert out.emitted is True and out.message is not None

    def test_fail_closed_BEATS_exactly_one(self, capsys):
        """amail spec O5g.4c/O5g.4d. The two MUSTs collide the first time the
        gate refuses a notice. Fail-closed wins, under a stated rule: they
        protect DIFFERENT PARTIES and the gate guards the IRREVERSIBLE harm.

        And it ALERTS, because a notice's content is broker-generated -- a
        scrub refusal means OUR text tripped OUR gate, which is a defect here
        and invisible from anywhere else."""
        def always_refuses(_m):
            return opsec.ScanResult(findings=[opsec.Finding("body", "hostname", 0, 5)])
        d = notices.decide(authenticated=True, sender="a@x.test",
                           refused_was_notice=False)
        out = notices.emit(d, to_address="a@x.test",
                           sender_address="postmaster@ours.test",
                           scrub=always_refuses)
        assert out.emitted is False
        assert out.alert is True, "this case needs a human"
        assert "our own text" in capsys.readouterr().err.lower()

    def test_a_scrub_that_raises_does_not_emit(self):
        def explodes(_m):
            raise RuntimeError("scanner down")
        d = notices.decide(authenticated=True, sender="a@x.test",
                           refused_was_notice=False)
        out = notices.emit(d, to_address="a@x.test",
                           sender_address="postmaster@ours.test", scrub=explodes)
        assert out.emitted is False and out.alert is True

    def test_notices_are_charged_to_the_BROKER_budget(self, tmp_path):
        """amail spec O5g.5. No agent composed them, so they cannot be charged
        to one -- and the budget must exist, or the clause defers to a number
        nobody set."""
        rl = RateLimiter(tmp_path / "rl",
                         {notices.BROKER_PRINCIPAL: RateLimit(1, 3600)})
        d = notices.decide(authenticated=True, sender="a@x.test",
                           refused_was_notice=False)
        first = notices.emit(d, to_address="a@x.test",
                             sender_address="postmaster@ours.test", rate_limiter=rl)
        assert first.emitted is True
        second = notices.emit(d, to_address="b@x.test",
                              sender_address="postmaster@ours.test", rate_limiter=rl)
        assert second.emitted is False and "rate limit" in second.reason

    def test_an_unknown_budget_does_not_emit(self, tmp_path):
        class Broken:
            def check_and_consume(self, principal, now=None):
                raise RateLimitError("unreadable")
        d = notices.decide(authenticated=True, sender="a@x.test",
                           refused_was_notice=False)
        out = notices.emit(d, to_address="a@x.test",
                           sender_address="postmaster@ours.test",
                           rate_limiter=Broken())
        assert out.emitted is False and out.alert is True


class TestOnTheRealInboundPath:
    """The PATH test. The gates above certify the DECISION; only this certifies
    that a refusal actually reaches it."""

    def test_a_refused_authenticated_sender_gets_a_notice(self, deploy_with_notices):
        from macf.amail import inbound
        cfg, spool_fn, make = deploy_with_notices
        # Authenticated and aligned, but NOT a contact: the qualifying case.
        raw = make(sender="stranger@example.org")
        result = inbound.process_entry(cfg, *spool_fn(cfg, raw))
        assert result["disposition"] == "quarantined"
        assert result["notice"]["emitted"] is True

    def test_a_forged_sender_gets_SILENCE(self, deploy_with_notices):
        """The amplifier case. Our bounce would go to whoever was forged."""
        from macf.amail import inbound
        cfg, spool_fn, make = deploy_with_notices
        raw = make(sender="stranger@example.org", dmarc="fail")
        result = inbound.process_entry(cfg, *spool_fn(cfg, raw))
        assert result["disposition"] == "quarantined"
        assert result["notice"]["emitted"] is False
        assert "not authenticated" in result["notice"]["reason"]

    def test_a_refused_NOTICE_is_not_answered(self, deploy_with_notices):
        from macf.amail import inbound
        cfg, spool_fn, make = deploy_with_notices
        raw = make(sender="postmaster@example.org",
                   extra_headers=f"{notices.NOTICE_HEADER}: 1\r\n")
        result = inbound.process_entry(cfg, *spool_fn(cfg, raw))
        assert result["notice"]["emitted"] is False
        assert "loop" in result["notice"]["reason"]


@pytest.fixture
def deploy_with_notices(tmp_path):
    """An inbound deployment with the notice path fully wired."""
    from macf.amail.broker import BrokerConfig
    from macf.amail.inbound import InboundConfig
    import hashlib

    AUTHORITY = "mx.test.example"
    AGENT, DOMAIN = "agent_alpha", "agents.test"
    home = tmp_path / "home" / AGENT
    (home / "Maildir").mkdir(parents=True)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_addressing({AGENT: ["friend@example.org"]}))
    cfg = InboundConfig(
        broker_config=BrokerConfig(
            domain=DOMAIN, agent_homes={AGENT: home}, contacts_path=contacts,
            audit_path=tmp_path / "audit.jsonl",
            opsec_scan=lambda m: opsec.scan_message(m, env={}),
        ),
        spool_dir=tmp_path / "spool", quarantine_dir=tmp_path / "quarantine",
        handoff_dir=tmp_path / "handoff", verdict_authority=AUTHORITY,
    )
    cfg.spool_dir.mkdir()

    def make(sender="friend@example.org", dmarc="pass", extra_headers=""):
        ar = (f"Authentication-Results: {AUTHORITY}; dmarc={dmarc}"
              f" header.from={sender.rsplit('@', 1)[1]}; spf=pass\r\n")
        return (f"{extra_headers}{ar}From: Someone <{sender}>\r\n"
                f"To: {AGENT}@{DOMAIN}\r\nSubject: test\r\n\r\nhello").encode()

    def spool_fn(c, raw):
        digest = hashlib.sha256(raw).hexdigest()
        eml = c.spool_dir / f"20260820T000000_{digest[:16]}.eml"
        eml.write_bytes(raw)
        side = eml.with_suffix(".json")
        side.write_text(json.dumps({"raw_sha256": digest,
                                    "observed": {"trusted": False,
                                                 "envelope_to": f"{AGENT}@{DOMAIN}"}}))
        return eml, side

    return cfg, spool_fn, make  # noqa: MACEFF004 - a test fixture's local 3-tuple, unpacked once in this file; a record here would add indirection without adding a caller that could reorder it


# ------------------------------------------- transmission (found by a battery)
#
# For one whole phase `emitted` was the only field, it meant "decided and
# composed", and every reader took it to mean SENT. A live run reported
# `emitted: true` for a notice that reached no transport, no audit record and
# no ledger.

class _Recording:
    name = "recording"
    def __init__(self): self.sent = []
    def send(self, message, credential, recipient=None):
        self.sent.append((recipient, message))
        from macf.amail import transport as T
        return T.TransportResult(T.ACCEPTED, "accepted for sending (202)")


class _Broken:
    name = "broken"
    def send(self, message, credential, recipient=None):
        from macf.amail.transport import TransportError
        raise TransportError("endpoint unreachable")


def _composed():
    from macf.amail import notices as N
    return N.emit(N.NoticeDecision(True, "authenticated and aligned"),
                  to_address="them@example.org",
                  sender_address="postmaster@ours.test")


def test_a_transmitted_notice_reports_sent():
    from macf.amail import notices as N
    t = _Recording()
    r = N.transmit(_composed(), transport=t, credential="cred")
    assert r.sent is True
    assert len(t.sent) == 1 and t.sent[0][0] == "them@example.org"


def test_a_freshly_composed_notice_is_not_yet_sent():
    """THE DEFAULT IS THE HAZARD, and the first version of this suite missed it.

    A mutant flipping the `sent` default to True survived, because every test
    exercised a branch that passes `sent` explicitly. The branch that does NOT
    pass it is `emit` itself — which composes and returns without transmitting,
    and is precisely the object whose optimism caused the original defect.
    """
    from macf.amail import notices as N
    d = _composed()
    assert d.emitted is True
    assert d.sent is False, "a composed notice claimed to have been sent"


def test_a_decision_not_to_emit_is_never_transmitted_even_carrying_a_message():
    """THE GUARD THE FIRST VERSION DID NOT REACH.

    A mutant removing the `not decision.emitted` check survived, because the
    gate-refused decision it was tested with also carries `message=None`, so
    the message check caught it and the emitted check was never exercised. A
    control that passes because a DIFFERENT control fired is a dead control
    wearing a live one's result. Here the message is present and emitted is
    False, so only the guard under test can refuse.
    """
    from macf.amail import notices as N
    t = _Recording()
    suppressed = N.NoticeDecision(False, "sender was not authenticated",
                                  message=N.compose_notice(
                                      "victim@example.org", N.CODE_NOT_ACCEPTED,
                                      sender_address="postmaster@ours.test"))
    r = N.transmit(suppressed, transport=t, credential="cred")
    assert r.sent is False
    assert t.sent == [], "a notice the gate declined reached the transport"


def test_no_transport_is_composed_but_NOT_sent():
    """The state the system was actually in, now nameable. A deployment with no
    outbound leg is legitimate; what must never happen is that state being
    indistinguishable from a delivered one."""
    from macf.amail import notices as N
    r = N.transmit(_composed(), transport=None)
    assert r.emitted is True
    assert r.sent is False
    assert "NOT sent" in r.reason


def test_a_transport_failure_does_not_undo_the_refusal():
    """The refusal this notice answers has ALREADY happened and is recorded.
    Letting a transport error propagate would make an undeliverable notice
    reach back and break the quarantine decision that produced it."""
    from macf.amail import notices as N
    r = N.transmit(_composed(), transport=_Broken(), credential="cred")
    assert r.sent is False
    assert r.alert is True, "a notice that could not be sent must be visible"


def test_a_notice_the_gate_refused_is_never_transmitted():
    """Fail-closed beats exactly-one, and it must survive the new wire: the
    scrub's refusal cannot be undone by a later transmission step."""
    from macf.amail import notices as N
    class _Findings:
        findings = ["planted"]
        unscanned = None
        def reason(self): return "planted"
    refused = N.emit(N.NoticeDecision(True, "aligned"),
                     to_address="them@example.org",
                     sender_address="postmaster@ours.test",
                     scrub=lambda m: _Findings())
    assert refused.emitted is False and refused.alert is True
    t = _Recording()
    r = N.transmit(refused, transport=t, credential="cred")
    assert r.sent is False
    assert t.sent == [], "a gate-refused notice reached the transport"


# ------------------------------- the WIRE itself (the thing that was missing)
#
# The notice module was complete and correct for a whole phase while nothing
# carried its output outward. Testing `transmit` proves the sender works;
# only this proves the inbound path CALLS it. That distinction is the entire
# defect being repaired here, so it gets its own control.

def _inbound_cfg(tmp_path, transport):
    import json as _json
    from macf.amail.broker import BrokerConfig
    from macf.amail.inbound import InboundConfig
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_json.dumps({"alpha": []}))
    cred = tmp_path / "cred"
    cred.write_text("CF_ACCESS_CLIENT_ID=x.access\nCF_ACCESS_CLIENT_SECRET=y\n")
    cred.chmod(0o600)
    (tmp_path / "alpha").mkdir()
    bc = BrokerConfig(domain="ours.test", contacts_path=contacts,
                      credentials_path=cred, agent_homes={"alpha": tmp_path / "alpha"},
                      transport=transport)
    return InboundConfig(broker_config=bc, spool_dir=tmp_path / "s",
                         quarantine_dir=tmp_path / "q")


_AUTHED = (b"Authentication-Results: mx.test; dmarc=pass header.from=them.example\n"
           b"From: them@them.example\nSubject: hi\n\nbody\n")


def test_the_inbound_path_actually_transmits_the_notice(tmp_path, monkeypatch):
    """THE CONTROL FOR THE WIRE. `transmit` being correct proves the sender
    works; it does not prove anybody calls it, and for a whole phase nobody
    did while the report claimed otherwise."""
    from macf.amail import inbound as I
    t = _Recording()
    monkeypatch.setattr(I, "authentication_status",
                        lambda cfg, raw: I.AuthStatus(True, "them@them.example", "aligned"))
    out = I._notify_refusal(_inbound_cfg(tmp_path, t), _AUTHED, "them@them.example")
    assert out["emitted"] is True
    assert out["sent"] is True, "the notice was decided and never transmitted"
    assert len(t.sent) == 1


def test_the_report_distinguishes_decided_from_sent(tmp_path, monkeypatch):
    """With no transport the decision still stands and the report must NOT
    claim delivery — the exact pair of facts one field could not carry."""
    from macf.amail import inbound as I
    monkeypatch.setattr(I, "authentication_status",
                        lambda cfg, raw: I.AuthStatus(True, "them@them.example", "aligned"))
    out = I._notify_refusal(_inbound_cfg(tmp_path, None), _AUTHED, "them@them.example")
    assert out["emitted"] is True and out["sent"] is False


def test_an_unauthenticated_sender_still_gets_silence_through_the_wire(tmp_path, monkeypatch):
    """The amplifier case must survive the new wire. A notice to a forged
    sender is delivered to the SPOOF VICTIM, so the wire must not become a
    path that reaches the transport before the decision is consulted."""
    from macf.amail import inbound as I
    t = _Recording()
    monkeypatch.setattr(I, "authentication_status",
                        lambda cfg, raw: I.AuthStatus(False, "", "unauthenticated"))
    out = I._notify_refusal(_inbound_cfg(tmp_path, t), b"From: forged@x\n\nx", "forged@x")
    assert out["emitted"] is False and out["sent"] is False
    assert t.sent == [], "a notice reached the transport for an unauthenticated sender"


# ------------------------------------------ the ACCOUNT of the notice (c_22)
#
# A notice went out over the real transport, charged the broker's budget, and
# wrote neither an audit record nor a disposition. Three accounting mechanisms
# and one fired.

def _ledger_cfg(tmp_path, transport):
    import json as _json
    from macf.amail.broker import BrokerConfig
    contacts = tmp_path / "contacts.json"; contacts.write_text(_json.dumps({"alpha": []}))
    (tmp_path / "alpha").mkdir()
    return BrokerConfig(domain="ours.test", contacts_path=contacts,
                        audit_path=tmp_path / "audit.jsonl",
                        dispositions_dir=tmp_path / "disp",
                        agent_homes={"alpha": tmp_path / "alpha"},
                        transport=transport)


def test_a_sent_notice_is_recorded_in_both_stores(tmp_path):
    """THE DEFECT. The message left; the account of it did not."""
    import json as _json
    from macf.amail import notices as N
    from macf.amail.broker import Broker
    from macf.amail.ratelimit import BROKER_PRINCIPAL
    bc = _ledger_cfg(tmp_path, _Recording())
    r = N.transmit(_composed(), transport=bc.transport, credential="c",
                   ledger=Broker(bc))
    assert r.sent is True
    recs = list((tmp_path / "disp").glob("*.json"))
    assert len(recs) == 1, "the notice left no disposition record"
    d = _json.loads(recs[0].read_text())
    assert d["agent"] == BROKER_PRINCIPAL, "a notice was billed to an agent"
    assert "them@example.org" in d["recipients"]
    audit = (tmp_path / "audit.jsonl").read_text()
    assert "broker-originated" in audit, "the audit log cannot say who sent it"


def test_a_failed_notice_is_recorded_too(tmp_path):
    """A notice that reached the transport and failed is not the same fact as
    one never attempted, and leaving it unrecorded puts the gap back on the
    path where it matters most."""
    import json as _json
    from macf.amail import notices as N
    from macf.amail.broker import Broker
    bc = _ledger_cfg(tmp_path, _Broken())
    r = N.transmit(_composed(), transport=bc.transport, credential="c",
                   ledger=Broker(bc))
    assert r.sent is False
    recs = list((tmp_path / "disp").glob("*.json"))
    assert len(recs) == 1
    hist = _json.loads(recs[0].read_text())["recipients"]["them@example.org"]["history"]
    assert "TransportError" in hist[-1]["detail"]


def test_a_recording_failure_does_not_undo_a_send(tmp_path, capsys):
    """The message is already gone. Pretending otherwise would make the
    ledger's error into a second and larger lie -- so it announces."""
    from macf.amail import notices as N
    class _BrokenLedger:
        def record_notice(self, *a, **k): raise OSError("disk full")
    t = _Recording()
    r = N.transmit(_composed(), transport=t, credential="c", ledger=_BrokenLedger())
    assert r.sent is True, "a recording failure was allowed to deny a real send"
    assert "ledger is short by one" in capsys.readouterr().err
