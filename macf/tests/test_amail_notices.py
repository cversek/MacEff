"""Non-delivery notices: the affirmative half, the safety half, and the seam.

Drafts through 0.7 contained ONLY prohibitions here, so an implementation that
emitted nothing under any circumstance was fully conformant -- which is exactly
the state that generated the section. Both halves are tested, and the silences
are tested as deliberately as the sends: silence is this module's most common
CORRECT outcome, which makes it the one most easily confused with a step that
never ran.
"""
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
    contacts.write_text(json.dumps({AGENT: ["friend@example.org"]}))
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

    return cfg, spool_fn, make
