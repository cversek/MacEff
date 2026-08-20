"""The outbound authentication criterion, against REAL receiver specimens.

Both specimens are real headers from two providers, reduced to the fields the
criterion reads and with sender-identifying values replaced. They are kept
because the two defects these tests pin were found by pointing the reader at a
second real receiver, and neither was reachable from a corpus built by the
reader's own author -- a corpus contains the shapes its author thought of.
"""
import pytest

from macf.amail import criterion as C


# Receiver A: an authserv-id, RFC 8601 shape.
RECEIVER_A = b"""\
ARC-Authentication-Results: i=1; mx.example-a.net; dmarc=pass header.from=ours.example.dev
Authentication-Results: mx.example-a.net; dkim=pass header.i=@ours.example.dev; \
spf=pass smtp.mailfrom=bounce@ours.example.dev; \
dmarc=pass (p=NONE sp=NONE dis=NONE) header.from=ours.example.dev
From: agent@ours.example.dev
Subject: s

body
"""

# Receiver B: NO authserv-id. The field begins with a method-result, which is
# what a major provider actually emits.
RECEIVER_B = b"""\
Authentication-Results: spf=pass (sender IP is 203.0.113.1) \
smtp.mailfrom=ours.example.dev; dkim=pass (signature was verified) \
header.d=ours.example.dev;dmarc=pass action=none \
header.from=ours.example.dev;compauth=pass reason=100
From: agent@ours.example.dev
Subject: s

body
"""

AUTH_A = "mx.example-a.net"
IDENT = "ours.example.dev"


def test_receiver_a_authenticates():
    """The known-answer green, first: a reader that fails everything scores
    perfectly against a corpus made only of failures."""
    r = C.read_criterion(RECEIVER_A, AUTH_A, IDENT)
    assert r["verdict"] == C.AUTHENTICATED
    assert C.is_pass(r)


def test_the_arc_header_is_not_collected():
    """O5i.3. On a first-hop message the ARC copy carries IDENTICAL values, so
    conflating them is invisible in the output -- the count is the only place
    it shows."""
    assert C.read_criterion(RECEIVER_A, AUTH_A, IDENT)["instances_present"] == 1


def test_a_missing_authserv_id_is_detected_not_invented():
    """THE DEFECT. The reader took the first token unconditionally, so a field
    beginning `spf=pass` reported its authserv-id AS `spf=pass`."""
    r = C.read_criterion(RECEIVER_B, "mx.example-b.net", IDENT)
    assert r["authserv_id"] is None
    assert r["verdict"] == C.NO_AUTHSERV_ID
    assert not C.is_pass(r)


def test_the_invented_authserv_id_cannot_be_declared_as_the_authority():
    """The security consequence, made explicit. Under the old reader a caller
    declaring the literal string `spf=pass` as its expected authority passed
    the authority check on a header that names no authority at all."""
    r = C.read_criterion(RECEIVER_B, "spf=pass", IDENT)
    assert not r["authority_ok"]
    assert not C.is_pass(r)


def test_an_unreadable_authority_is_distinguishable_from_a_wrong_one():
    """Three different facts, three different verdicts. Collapsing them would
    make a provider whose header shape we cannot parse look identical to a
    forged verdict, and those want opposite responses."""
    assert C.read_criterion(RECEIVER_B, "anything", IDENT)["verdict"] == C.NO_AUTHSERV_ID
    assert C.read_criterion(RECEIVER_A, "mx.wrong.net", IDENT)["verdict"] == C.UNTRUSTED_AUTHORITY
    assert C.read_criterion(b"From: a@b\n\nx", AUTH_A, IDENT)["verdict"] == C.ABSENT


def test_a_pass_for_somebody_elses_domain_is_not_our_pass():
    """THE SECOND DEFECT. `header.from` was reported and never tested, so a
    message authenticating for another domain read AUTHENTICATED."""
    r = C.read_criterion(RECEIVER_A, AUTH_A, "someone-else.example")
    assert r["results"]["dmarc"] == "pass"
    assert r["verdict"] == C.IDENTITY_MISMATCH
    assert not C.is_pass(r)


def test_the_disposition_field_is_never_read_as_the_result():
    """O5i.5, and the lookbehind that enforces it. `\\b` matches inside a
    dotted token, so an unguarded `dmarc=` pattern matches the `dmarc=` in
    `policy.dmarc=none` -- the DISPOSITION, which reads `none` in both
    polarities. RFC 8601 fixes no field order, so a reader that gets this right
    by field order degrades silently the day a provider reorders."""
    reordered = b"""\
Authentication-Results: mx.example-a.net; policy.dmarc=none; \
dmarc=pass header.from=ours.example.dev
From: agent@ours.example.dev

body
"""
    r = C.read_criterion(reordered, AUTH_A, IDENT)
    assert r["results"]["dmarc"] == "pass", "the disposition field shadowed the result"


def test_a_forged_later_instance_is_ignored():
    """O5i.2. A sender can append its own header; only the outermost is the
    receiving boundary's."""
    forged = RECEIVER_A.replace(
        b"From: agent@ours.example.dev",
        b"Authentication-Results: mx.example-a.net; dmarc=pass header.from=evil.example\n"
        b"From: agent@ours.example.dev")
    r = C.read_criterion(forged, AUTH_A, IDENT)
    assert r["instances_present"] == 2
    assert r["header_from"] == IDENT, "a later instance was read"
    assert r["verdict"] == C.AUTHENTICATED
