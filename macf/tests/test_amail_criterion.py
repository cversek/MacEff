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
    r = C.read_criterion(RECEIVER_A, AUTH_A, IDENT, provenance=C.FETCHED)
    assert r["verdict"] == C.AUTHENTICATED
    assert C.is_pass(r)
    assert C.gate_reason(r) is None


def test_a_relayed_copy_may_be_read_and_may_not_discharge_a_gate():
    """PROVENANCE, MECHANISED. The criterion rests on the reader FETCHING the
    raw bytes from a mailbox under our control. Every receiver reading taken
    before this existed arrived as text a human pasted out of a mail client --
    a RENDERING, which may fold, reorder or omit without saying so.

    The verdict is still computed and still reported: a relayed copy is
    evidence, and refusing to look at it would be its own kind of blindness.
    What it cannot do is discharge a gate, and the reason is reported
    SEPARATELY from the verdict, because "the mail failed" and "this reading
    cannot be acted on" are different facts that a boolean flattens.
    """
    r = C.read_criterion(RECEIVER_A, AUTH_A, IDENT, provenance=C.RELAYED)
    assert r["verdict"] == C.AUTHENTICATED
    assert not C.is_pass(r)
    assert C.gate_reason(r) == C.NOT_FETCHED


def test_unasserted_provenance_is_treated_as_relayed():
    """A caller who did not think about how the bytes arrived is the caller
    this distinction exists for."""
    assert not C.is_pass(C.read_criterion(RECEIVER_A, AUTH_A, IDENT))


def test_self_authored_mail_may_waive_the_authority_check():
    """The receiver-B case, and the reason the waiver is safe: the check
    defends against an ADVERSARIAL SENDER, and on this path the sender is us --
    we compose it, submit it on our own credential to our own endpoint, and
    read it out of a mailbox we control. There is no forger in that loop."""
    r = C.read_criterion(RECEIVER_B, None, IDENT,
                         self_authored=True, provenance=C.FETCHED)
    assert r["verdict"] == C.AUTHENTICATED
    assert C.is_pass(r)


def test_the_waiver_is_refused_on_mail_we_did_not_write():
    """THE SCOPE IS THE POINT, because the danger is migration. Asking to waive
    the check on a stranger's mail is a programming error, not a lenient
    verdict -- a lenient verdict would be adopted by whoever needed one."""
    with pytest.raises(ValueError, match="authored"):
        C.read_criterion(RECEIVER_B, None, IDENT,
                         self_authored=False, provenance=C.FETCHED)


def test_a_stale_authority_less_declaration_is_detected():
    """If we declare a receiver stamps no authserv-id and one turns up, the
    receiver changed under us. That is a finding, not a pass."""
    r = C.read_criterion(RECEIVER_A, None, IDENT,
                         self_authored=True, provenance=C.FETCHED)
    assert r["verdict"] == C.UNEXPECTED_AUTHSERV_ID
    assert not C.is_pass(r)


def test_the_arc_header_is_not_collected():
    """O5i.3. On a first-hop message the ARC copy carries IDENTICAL values, so
    conflating them is invisible in the output -- the count is the only place
    it shows."""
    assert C.read_criterion(RECEIVER_A, AUTH_A, IDENT, provenance=C.FETCHED)["instances_present"] == 1


def test_a_missing_authserv_id_is_detected_not_invented():
    """THE DEFECT. The reader took the first token unconditionally, so a field
    beginning `spf=pass` reported its authserv-id AS `spf=pass`."""
    r = C.read_criterion(RECEIVER_B, "mx.example-b.net", IDENT, provenance=C.FETCHED)
    assert r["authserv_id"] is None
    assert r["verdict"] == C.NO_AUTHSERV_ID
    assert not C.is_pass(r)


def test_the_invented_authserv_id_cannot_be_declared_as_the_authority():
    """The security consequence, made explicit. Under the old reader a caller
    declaring the literal string `spf=pass` as its expected authority passed
    the authority check on a header that names no authority at all."""
    r = C.read_criterion(RECEIVER_B, "spf=pass", IDENT, provenance=C.FETCHED)
    assert not r["authority_ok"]
    assert not C.is_pass(r)


def test_an_unreadable_authority_is_distinguishable_from_a_wrong_one():
    """Three different facts, three different verdicts. Collapsing them would
    make a provider whose header shape we cannot parse look identical to a
    forged verdict, and those want opposite responses."""
    assert C.read_criterion(RECEIVER_B, "anything", IDENT, provenance=C.FETCHED)["verdict"] == C.NO_AUTHSERV_ID
    assert C.read_criterion(RECEIVER_A, "mx.wrong.net", IDENT, provenance=C.FETCHED)["verdict"] == C.UNTRUSTED_AUTHORITY
    assert C.read_criterion(b"From: a@b\n\nx", AUTH_A, IDENT, provenance=C.FETCHED)["verdict"] == C.ABSENT


def test_a_pass_for_somebody_elses_domain_is_not_our_pass():
    """THE SECOND DEFECT. `header.from` was reported and never tested, so a
    message authenticating for another domain read AUTHENTICATED."""
    r = C.read_criterion(RECEIVER_A, AUTH_A, "someone-else.example", provenance=C.FETCHED)
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
    r = C.read_criterion(reordered, AUTH_A, IDENT, provenance=C.FETCHED)
    assert r["results"]["dmarc"] == "pass", "the disposition field shadowed the result"


def test_a_forged_later_instance_is_ignored():
    """O5i.2. A sender can append its own header; only the outermost is the
    receiving boundary's."""
    forged = RECEIVER_A.replace(
        b"From: agent@ours.example.dev",
        b"Authentication-Results: mx.example-a.net; dmarc=pass header.from=evil.example\n"
        b"From: agent@ours.example.dev")
    r = C.read_criterion(forged, AUTH_A, IDENT, provenance=C.FETCHED)
    assert r["instances_present"] == 2
    assert r["header_from"] == IDENT, "a later instance was read"
    assert r["verdict"] == C.AUTHENTICATED


# ------------------------- a receiver that SPLITS its verdict (third shape)
#
# Three real receivers, three header shapes: one header with every method and
# an authserv-id; one header with NO authserv-id; and FOUR headers, one method
# each, all from the same authority. The reader handled the first by design and
# the third by luck -- the dmarc token happened to be listed first.

RECEIVER_C = b"""\
Authentication-Results: mail.example-c.ch; dmarc=pass (p=none dis=none) header.from=ours.example.dev
Authentication-Results: mail.example-c.ch; spf=pass smtp.mailfrom=ours.example.dev
Authentication-Results: mail.example-c.ch; dkim=pass (2048-bit key) header.d=ours.example.dev
From: agent@ours.example.dev
Subject: s

body
"""

# The same receiver, methods in a different order. Nothing in RFC 8601 fixes
# the order, so a reader that gets C right must get this right too.
RECEIVER_C_REORDERED = b"""\
Authentication-Results: mail.example-c.ch; spf=pass smtp.mailfrom=ours.example.dev
Authentication-Results: mail.example-c.ch; dkim=pass (2048-bit key) header.d=ours.example.dev
Authentication-Results: mail.example-c.ch; dmarc=pass (p=none dis=none) header.from=ours.example.dev
From: agent@ours.example.dev
Subject: s

body
"""

AUTH_C = "mail.example-c.ch"


def test_a_split_verdict_is_read_across_the_receivers_own_stamps():
    r = C.read_criterion(RECEIVER_C, AUTH_C, IDENT, provenance=C.FETCHED)
    assert r["verdict"] == C.AUTHENTICATED
    assert r["results"]["spf"] == "pass"
    assert r["results"]["dkim"] == "pass", "a method the receiver stated was read as absent"


def test_the_order_of_the_receivers_stamps_does_not_change_the_verdict():
    """THE LUCK, REMOVED. RFC 8601 fixes no order, so a reader that returns the
    right answer because the dmarc token happens to be listed first is a
    constant waiting for a provider to reorder."""
    a = C.read_criterion(RECEIVER_C, AUTH_C, IDENT, provenance=C.FETCHED)
    b = C.read_criterion(RECEIVER_C_REORDERED, AUTH_C, IDENT, provenance=C.FETCHED)
    assert a["verdict"] == b["verdict"] == C.AUTHENTICATED
    assert a["results"] == b["results"]


def test_the_run_STOPS_at_a_header_that_is_not_the_receivers():
    """THE SECURITY PROPERTY, unchanged and now load-bearing in a new way. A
    sender-supplied header arrives BELOW the receiver's own stamps, so the run
    must stop at the first instance that is not ours -- which is exactly where
    a forgery begins. Reading past it builds a gate whose reading the attacker
    writes.

    THE FIRST VERSION OF THIS TEST DID NOT DISCRIMINATE, and the mutation
    sweep said so: it asserted on `header.from`, which is protected by
    first-match-wins whether or not the forged instances are joined in. A
    control that passes because a DIFFERENT mechanism happens to hold is a dead
    control wearing a live one's result -- the second time that exact shape has
    turned up in this suite today.

    The discriminating case is a receiver that does NOT state the deciding
    method, with an attacker supplying it below. Reading past the run then
    lifts the verdict straight out of the forgery.
    """
    receiver_silent_on_dmarc = b"""\
Authentication-Results: mail.example-c.ch; spf=pass smtp.mailfrom=ours.example.dev
Authentication-Results: mail.example-c.ch; dkim=pass (2048-bit key) header.d=ours.example.dev
Authentication-Results: attacker.invalid; dmarc=pass header.from=ours.example.dev
From: agent@ours.example.dev
Subject: s

body
"""
    r = C.read_criterion(receiver_silent_on_dmarc, AUTH_C, IDENT,
                         provenance=C.FETCHED)
    assert r["results"]["dmarc"] is None, \
        "a dmarc verdict was taken from a header the receiver did not write"
    assert r["verdict"] == C.NOT_AUTHENTICATED
    assert not C.is_pass(r)
