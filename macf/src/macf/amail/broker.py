"""The amail broker — the single point where mail may leave an agent.

WHY THIS PROCESS EXISTS AT ALL. A contact restriction an agent enforces in its
own client is advisory: anything with code execution as that uid bypasses it, and
that is precisely the state a prompt injection aims for. So enforcement lives in
a process the agent does not control, holding a credential the agent has never
been given.

    A fully compromised agent still cannot send to an unlisted address,
    because it has never held a credential that reaches the internet.

Agents submit over a local socket rather than speaking SMTP. There is therefore
no server address for an agent to repoint and no credential to misuse.

DELIVERY LADDER. Every message is addressed as mail; the rung is chosen here, at
delivery time, and is never recorded in the address or the contact list:

    rung 1  recipient's mailbox is on this host   -> direct Maildir write
    rung 2  peer broker on a private network      -> not implemented (seam below)
    rung 3  anything else                         -> outbound relay (Phase 6)

Rung 1 is implemented. The others raise a specific, logged error rather than
silently succeeding — a transport that reports delivery it did not perform is the
failure this whole subsystem is built to avoid.
"""
from __future__ import annotations

import json
import os
import re
import socket
import socketserver
import stat
import struct
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .audit import AuditLog
from .contacts import ContactBook, ContactListError
from .models import Message, new_id, _now_iso
from .trust import TrustClass, LOCAL_SUBMISSION
from .crypto import verify
from .store import deliver, ensure_maildir, read_all as _store_read_all, find as _store_find

DEFAULT_SOCKET = "/run/amail/broker.sock"

#: Shapes the broker itself mints. Anything claiming to be an identifier must
#: look like one — otherwise the field is a kilobyte-scale channel wearing an
#: identifier's name.
_ID_RE = re.compile(r"^msg-\d+-[0-9a-f]{12}$")
_THR_RE = re.compile(r"^thr-\d+-[0-9a-f]{12}$")

#: Bounds on genuinely submitter-owned fields. Not correctness limits — blast
#: radius limits.
MAX_SUBJECT = 998
MAX_BODY = 1 << 18      # 256 KiB
MAX_RECIPIENTS = 64     # ContactBook is consulted per recipient
#: An Ed25519 signature is 64 bytes, ~88 base64 characters. Generous for future
#: algorithms, small enough that the field cannot become a covert channel
#: wearing a cryptographic name.
#:
#: It must also be BELOW the 998-character header ceiling _hdr() applies. Set at
#: 1024 it was unreachable — every oversize signature was already truncated by
#: the header cap, so this bound enforced nothing and its test passed by way of
#: a mechanism it was not written to check. A limit that a sibling always
#: reaches first is not a limit; it is a comment.
MAX_SIGNATURE = 512

#: Longest the JOINED recipient list may be. serialize() writes `To:` as a
#: single header value, so a longer list is silently shortened on the way to
#: disk — and the canonical signing form, modelling that same truncation,
#: collided for any two lists sharing this prefix.
_MAX_TO_HEADER = 998

#: Headers a sender may NOT assert about authentication. RFC 8601 §5 requires an
#: ADMD to strip incoming Authentication-Results bearing its own authserv-id,
#: because otherwise a sender forges one and readers draw false conclusions.
#: This list is broader: amail evaluates at its own boundary and never consumes
#: any upstream verdict, so every one of these is an inbound claim to discard.
STRIPPED_INBOUND_HEADERS = (
    "authentication-results", "arc-authentication-results", "arc-message-signature",
    "arc-seal", "x-amail-trust",
)


def strip_inbound_headers(message: Message) -> List[str]:
    """Discard every upstream authentication claim carried by an inbound message.

    An Authentication-Results header is ordinary text; anything able to send mail
    can write one. RFC 8601 §5 requires an ADMD to strip incoming ones bearing
    its own authserv-id for exactly that reason, and amail goes further: it
    consumes no upstream verdict at all, so every header in the list is an
    inbound claim to drop rather than to evaluate.

    Returns the names it actually cleared, so a caller can record that a sender
    tried — an attempt to assert a verdict is itself worth knowing about.
    """
    cleared: List[str] = []
    for name in STRIPPED_INBOUND_HEADERS:
        attr = name.replace("x-amail-", "").replace("-", "_")
        if getattr(message, attr, None) is not None:
            setattr(message, attr, None)
            cleared.append(name)
    return cleared


def peer_uid(conn: socket.socket) -> int:
    """The uid the kernel recorded for the connected process.

    One implementation, used both to authenticate a submission and to meter
    connections, so the two can never disagree about who is calling.
    """
    raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                          struct.calcsize("3I"))
    # ucred fields are unsigned; reading them signed turns a high uid negative.
    # It failed closed, but a lookup should not depend on that.
    _pid, uid, _gid = struct.unpack("3I", raw)
    return uid

#: The trust classification, as data rather than prose. canonicalize() asserts
#: its union covers every Message field, so a field added later fails loudly
#: instead of silently defaulting to trusted.
MINTED = frozenset({"message_id", "date", "trust"})
CHECKED = frozenset({"sender"})
BOUND = frozenset({"thread_id", "parent"})
PASSED = frozenset({"subject", "body", "to", "signature"})
_CLASSIFIED_FIELDS = MINTED | CHECKED | BOUND | PASSED


class DeliveryError(RuntimeError):
    """Transport could not deliver. Never swallowed into a success."""


@dataclass
class BrokerConfig:
    """Everything the broker needs. Paths, not secrets — the credential is read
    from disk at send time so it never sits in a config object that might be
    logged or serialised into an error."""

    domain: str
    agent_homes: Dict[str, Path] = field(default_factory=dict)
    contacts_path: Optional[Path] = None
    audit_path: Optional[Path] = None
    socket_path: Path = Path(DEFAULT_SOCKET)
    credentials_path: Optional[Path] = None

    #: uid -> agent name. THE authentication table. The socket is world-writable,
    #: so the only thing distinguishing one submitter from another is the kernel's
    #: view of who is on the other end. A submitted `sender` field is a claim; this
    #: mapping is the fact. An empty mapping means nobody can be authenticated and
    #: every submission is refused — see Broker.identify().
    agent_uids: Dict[int, str] = field(default_factory=dict)

    def address_for(self, agent: str) -> str:
        return f"{agent}@{self.domain}"

    def agent_for(self, address: str) -> Optional[str]:
        """Local agent owning this address, or None if it is not ours."""
        addr = address.strip().lower()
        local, _, dom = addr.partition("@")
        if dom != self.domain.lower():
            return None
        return local if local in self.agent_homes else None


class Broker:
    def __init__(self, config: BrokerConfig):
        self.config = config
        self.contacts = ContactBook(config.contacts_path) if config.contacts_path else None
        self.audit = AuditLog(config.audit_path) if config.audit_path else None

    # ---------------------------------------------------------------- enforcement

    def _check(self, sender: str, recipients: List[str]) -> List[str]:
        """Return refusal reasons. Empty means every recipient is permitted.

        Checked BEFORE any transport is selected, so a refused message never
        reaches a code path that could deliver it.
        """
        if self.contacts is None:
            return ["no contact list configured; refusing to send"]
        reasons: List[str] = []
        for r in recipients:
            why = self.contacts.refuse_reason(sender, r)
            if why:
                reasons.append(why)
        return reasons

    # ------------------------------------------------------------------ delivery

    def _rung(self, recipient: str) -> str:
        return "local" if self.config.agent_for(recipient) else "relay"

    def _deliver_one(self, recipient: str, message: Message) -> Tuple[str, str]:
        """Deliver to one recipient. Returns (rung, classification).

        THE CLASSIFICATION IS RETURNED, not left on the message. It used to be
        written to the shared Message and read back after the loop, so the
        single audit record carried whatever the LAST delivery happened to leave
        there — and the submitter chose which verdict got recorded by ordering
        the `to` list. A compromised agent suppressed its own SUSPECT from the
        broker-owned record by appending one allowlisted keyless recipient.

        Returning it means a caller cannot read a stale value, because there is
        no shared value to go stale.
        """
        agent = self.config.agent_for(recipient)
        if agent:
            # Classified against THIS recipient's contact book, immediately
            # before the write. Two recipients may declare different keys for
            # the same sender, so the answer is per mailbox, not per message.
            trust = self.classify_inbound(message, agent).value
            message.trust = trust
            deliver(self.config.agent_homes[agent], message)
            return "local", trust
        raise DeliveryError(
            f"no transport for '{recipient}': rung 1 (local) does not apply and "
            "remote delivery is not configured. Refusing to report success for a "
            "message that was not sent."
        )

    # -------------------------------------------------------------------- submit

    def canonicalize(self, sender: str, message: Message, home: Optional[Path]) -> List[str]:
        """Rebuild every field the submitter does not own. Returns refusal reasons.

        THIS EXISTS BECAUSE FIXING FIELDS ONE AT A TIME DOES NOT CONVERGE. Three
        audit rounds each found a different submitter-controlled field on the same
        path — the envelope sender, then the From header, then subject/thread_id/
        parent/message_id/date — and each fix addressed the field it was shown
        while leaving its siblings alone.

        So the model is inverted, the way _hdr() was inverted to defer to the
        parser's own definition of a line. Enumerate what the broker MINTS and
        what it VALIDATES; everything not in those two sets is hostile by
        construction. A field added to Message later is untrusted by default
        rather than trusted until an auditor notices it.

            MINTED  message_id, date        - always replaced, never accepted
            CHECKED sender                  - must equal the authenticated identity
            BOUND   thread_id, parent       - must be broker-shaped, and parent
                                              must name a message this sender can
                                              actually see
            PASSED  subject, body, to       - genuinely the submitter's, bounded

        On the residual: a permitted correspondent can still quote hostile text
        into a message it is allowed to send. That is inherent to correspondence
        and cannot be removed without breaking replies. What is removed is the
        several-kilobyte covert channel in fields that are supposed to be
        identifiers.
        """
        # The enumeration is ASSERTED, not described. Round 4 demonstrated that
        # adding one field to Message delivered 4,000 attacker bytes with ok=True
        # and the suite still green — the docstring's "untrusted by default" was
        # false, because the actual default was PASS. A claim in prose cannot
        # notice a new field; this can.
        unclassified = set(Message.__dataclass_fields__) - _CLASSIFIED_FIELDS
        if unclassified:
            raise AssertionError(
                f"Message fields {sorted(unclassified)} are not classified in "
                "canonicalize(). Add each to MINTED/CHECKED/BOUND/PASSED and "
                "handle it, or it reaches storage untrusted."
            )

        reasons: List[str] = []

        # CHECKED
        expected = self.config.address_for(sender)
        if message.sender and message.sender.strip() != expected:
            # BYTE-IDENTICAL, not case-insensitively equal.
            #
            # This used to accept a case variant and then REWRITE the field to
            # the broker's spelling — and `sender` is signature-covered, so the
            # signature had committed to the old bytes. The realised effect was
            # authorship denial through configuration: MACF_AMAIL_DOMAIN set to
            # `Example.Test` against a broker configured `example.test` made
            # every message that agent sent arrive SUSPECT at every
            # correspondent holding its key, while the CLI printed "delivered".
            # No error anywhere.
            #
            # Refusing turns a silent, permanent, invisible failure into one
            # loud message at the first send. The spec excludes message_id and
            # date from signature coverage precisely BECAUSE the broker rewrites
            # them; the same reasoning had not been applied to the field the
            # broker was also quietly rewriting.
            reasons.append(f"message From '{message.sender}' does not match the "
                           f"authenticated sender '{expected}' exactly. The From "
                           "field is covered by the signature, so the broker "
                           "cannot correct it without invalidating authorship.")
        message.sender = expected

        # MINTED — a submitter-chosen message_id can shadow another message in
        # store.find(), splice threads, and collide audit records.
        message.message_id = new_id("msg")
        message.date = _now_iso()
        # `trust` is MINTED and never accepted, which is what makes the label
        # worth anything. A submitter that could set it would write "attested"
        # onto its own forgery, and every reader downstream would believe it.
        #
        # IT IS CLASSIFIED BY THE SAME CLASSIFIER AS INBOUND MAIL, and getting
        # this wrong was the worst defect in v1.1. The local path used to mint
        # ATTESTED unconditionally, on the argument that SO_PEERCRED proves
        # authorship more strongly than a signature does. That argument is true
        # about AUTHORSHIP and it is not what the label says: the badge reads
        # "signed by this correspondent", and it was being shown for messages
        # with no signature at all, and for messages carrying a signature that
        # demonstrably did not verify.
        #
        # Two consequences made it indefensible. The spec's promise that a
        # compromised agent stripping its own signature makes its own mail
        # unverified — self-harm, not attack — was FALSE, because that agent
        # still delivered mail labelled as signed to every correspondent on the
        # host. And the two v1.1 mechanisms disagreed on identical bytes:
        # classify_inbound() said SUSPECT where canonicalize() said ATTESTED.
        #
        # So the classifier runs on both paths and ATTESTED means one thing
        # everywhere: a signature verified against a key the recipient declared.
        # The kernel-established fact is not discarded — it goes to the audit
        # log, which is broker-owned, rather than into a label whose whole job is
        # to tell a READER what they themselves could re-check.
        #
        # Set to None HERE, and minted per recipient in _deliver_one(). The
        # classification depends on whose contact book is asked — two recipients
        # may declare different keys for the same sender, so one value on a
        # shared message object cannot be correct for both. What canonicalize()
        # owns is destroying the submitter's claim; what delivery owns is
        # replacing it with the answer for that mailbox.
        message.trust = None

        # PASSED — `signature` is the sender's own claim about its own message
        # and is carried unchanged. It is PASSED rather than CHECKED on purpose:
        # the broker cannot verify an outbound signature (it holds no private
        # key, by design) and the recipient is the party who must. Its size is
        # bounded because an unbounded "signature" is an unbounded channel
        # wearing a cryptographic name — the same defect round 3 found in the
        # identifier fields.
        if message.signature is not None:
            message.signature = str(message.signature)[:MAX_SIGNATURE]

        # BOUND — identifiers must look like identifiers. Free text here is a
        # ~2 KB channel wearing an id's name.
        if message.parent is not None:
            if not _ID_RE.match(message.parent or ""):
                reasons.append("parent is not a valid message identifier")
            elif home is not None:
                from .store import find as _find
                if _find(home, message.parent) is None:
                    reasons.append(
                        "parent names a message this sender cannot see; a reply "
                        "must continue a thread the sender actually received")
        if message.thread_id and not _THR_RE.match(message.thread_id):
            reasons.append("thread_id is not a valid thread identifier")

        # PASSED, but bounded.
        if len(message.subject or "") > MAX_SUBJECT:
            reasons.append(f"subject exceeds {MAX_SUBJECT} characters")
        if len(message.body or "") > MAX_BODY:
            reasons.append(f"body exceeds {MAX_BODY} characters")
        if len(message.to) > MAX_RECIPIENTS:
            reasons.append(f"more than {MAX_RECIPIENTS} recipients")
        # By JOINED LENGTH too, and by comma. serialize() writes `To:` as ONE
        # header value capped at 998, so a longer list silently loses its tail
        # on the way to disk, and an address containing a comma splits into two
        # different addresses when read back. Either makes the stored recipients
        # differ from the signed ones — and `to` is signature-covered, so the
        # broker must refuse rather than correct, for the same reason it now
        # refuses a case-variant `sender` instead of rewriting it.
        if len(", ".join(message.to or [])) > _MAX_TO_HEADER:
            reasons.append(
                f"recipient list exceeds {_MAX_TO_HEADER} characters when joined; "
                "it would be silently shortened in storage")
        if any("," in (a or "") for a in (message.to or [])):
            reasons.append("a recipient address contains a comma, which is the "
                           "recipient separator and would split it in storage")

        return reasons

    def submit(self, sender: str, message: Message) -> Dict[str, Any]:
        """Enforce, then deliver. The only way mail leaves an agent."""
        sender_home = self.config.agent_homes.get(sender)
        bad = self.canonicalize(sender, message, sender_home)
        if bad:
            if self.audit:
                self.audit.refused(sender=sender, recipients=message.to,
                                   reason="; ".join(bad), message_id=message.message_id)
            return {"ok": False, "refused": bad, "message_id": message.message_id}

        if not message.to:
            # A message with no recipients previously returned ok with no audit
            # record at all — a submission that happened and left no trace.
            reason = "no recipients"
            if self.audit:
                self.audit.refused(sender=sender, recipients=[], reason=reason,
                                   message_id=message.message_id)
            return {"ok": False, "refused": [reason], "message_id": message.message_id}

        refusals = self._check(sender, message.to)
        if refusals:
            if self.audit:
                self.audit.refused(sender=sender, recipients=message.to,
                                   reason="; ".join(refusals), message_id=message.message_id)
            # Partially-permitted is refused outright rather than partially sent:
            # a caller told "delivered" about some recipients and not others has
            # to reconcile that, and will get it wrong.
            return {"ok": False, "refused": refusals, "message_id": message.message_id}

        delivered, failures = [], []
        for r in message.to:
            try:
                rung, trust = self._deliver_one(r, message)
                delivered.append({"recipient": r, "rung": rung, "trust": trust})
            except Exception as e:  # noqa: BLE001
                # Catch EVERYTHING, not just DeliveryError. An OSError escaping
                # here skipped the audit block below, so mail already delivered to
                # earlier recipients left NO RECORD while the sender was told the
                # send failed. Disk-full alone triggered it. The audit block must
                # be unreachable-proof: whatever happens, what was delivered gets
                # written down.
                failures.append({"recipient": r, "error": f"{type(e).__name__}: {e}"})

        if self.audit:
            if delivered:
                self.audit.allowed(sender=sender, recipients=[d["recipient"] for d in delivered],
                                   message_id=message.message_id,
                                   rung=",".join(sorted({d["rung"] for d in delivered})),
                                   # PER RECIPIENT, because one value cannot be
                                   # correct for a delivery where recipients
                                   # classify differently — and reading a single
                                   # shared value let the submitter choose which
                                   # verdict was recorded, by list order.
                                   trust={d["recipient"]: d["trust"] for d in delivered},
                                   # What the KERNEL established. No reader of the
                                   # stored message can re-derive it, so it has
                                   # nowhere to live but a broker-owned record.
                                   authorship=f"so_peercred:{sender}")
            for f in failures:
                self.audit.error(context="delivery", detail=f"{f['recipient']}: {f['error']}")

        return {
            "ok": not failures,
            "message_id": message.message_id,
            "thread_id": message.thread_id,
            "delivered": delivered,
            "failures": failures,
        }

    # ------------------------------------------------------------------- inbound

    def _bound_fields(self, message: Message) -> List[str]:
        """Apply every blast-radius bound. Returns the fields actually edited.

        Called BEFORE classification on the inbound path, so the label always
        describes the bytes that get stored rather than the bytes that arrived.

        The recipient bound is by JOINED LENGTH as well as by count, and that is
        not fussiness. `serialize()` writes `To:` as one header value through
        _hdr(), which truncates at 998 — so a list longer than that silently
        lost its tail on the way to disk, and the canonical signing form,
        modelling the same truncation, produced BYTE-IDENTICAL payloads for any
        two recipient lists sharing a 998-character prefix. One captured
        signature covered a message addressed elsewhere. MAX_RECIPIENTS alone
        did not prevent it: 64 ordinary addresses join to well over 998
        characters. Bounding the joined length here means the stored `To:` is
        never silently shortened, so the collision cannot arise.
        """
        edited: List[str] = []
        if len(message.subject or "") > MAX_SUBJECT:
            message.subject = (message.subject or "")[:MAX_SUBJECT]
            edited.append("subject")
        if len(message.body or "") > MAX_BODY:
            message.body = (message.body or "")[:MAX_BODY]
            edited.append("body")
        if message.signature is not None and len(str(message.signature)) > MAX_SIGNATURE:
            message.signature = str(message.signature)[:MAX_SIGNATURE]
            edited.append("signature")
        to = list(message.to or [])
        if len(to) > MAX_RECIPIENTS:
            to, = (to[:MAX_RECIPIENTS],)
            edited.append("to")
        while to and len(", ".join(to)) > _MAX_TO_HEADER:
            to.pop()
            if "to" not in edited:
                edited.append("to")
        message.to = to
        return edited

    def classify_inbound(self, message: Message, agent: str,
                         domain_authenticated: bool = False) -> TrustClass:
        """What has actually been established about where this came from.

        `domain_authenticated` is supplied by the receiving MTA boundary — OUR
        boundary, never a header in the message. An Authentication-Results
        header is ordinary text that anything able to send mail can write, so
        consuming one would be taking identity from the payload: the exact
        defect five audit rounds removed from the local socket, reappearing one
        surface over. The parameter is a fact the caller established, not a
        claim the message made.

        Ordering matters. A verified signature outranks domain authentication
        because it proves the CORRESPONDENT and domain authentication proves
        only the DOMAIN — and the message that reads as a trusted human over an
        attacker-controlled address passes DMARC cleanly, because the attacker's
        domain genuinely is the attacker's domain.
        """
        keys = self.contacts.keys_for(agent, message.sender) if self.contacts else []
        if message.signature and keys:
            if verify(message, message.signature, keys):
                return TrustClass.ATTESTED
            # A signature that fails is not the same as no signature. Someone
            # went to the trouble of attaching one and it did not check out.
            # Collapsing this into UNVERIFIED discards the only evidence that
            # separates "we could not tell" from "we looked, and it did not add
            # up" — and the second is the one worth waking someone for.
            return TrustClass.SUSPECT
        if message.signature and not keys:
            # Signed by a correspondent who has declared no key. Nothing can be
            # concluded, so nothing is: this is not SUSPECT (no check failed)
            # and it is certainly not ATTESTED.
            return TrustClass.DOMAIN_AUTH if domain_authenticated else TrustClass.UNVERIFIED
        if keys and not message.signature:
            # A correspondent who publishes a key and then sends unsigned mail
            # is the shape of an impersonation: the attacker has the address but
            # not the key, so the cheapest move is to simply omit the signature
            # and hope nobody checks. Declaring a key is a commitment to using
            # one, and mail that breaks the commitment is worth flagging.
            return TrustClass.SUSPECT
        return TrustClass.DOMAIN_AUTH if domain_authenticated else TrustClass.UNVERIFIED

    def accept_inbound(self, message: Message, recipient: str) -> Dict[str, Any]:
        """Deliver inbound mail, or quarantine it when the sender is unlisted.

        An allowlisted sender is an AUTHORIZATION fact, not an authenticity or
        safety one. Nothing here establishes that a message is genuinely from
        whom it claims, and message bodies remain data rather than instructions.
        """
        from .store import quarantine
        from .store import read_all as store_read_all
        agent = self.config.agent_for(recipient)
        if not agent:
            raise DeliveryError(f"'{recipient}' is not a local mailbox")
        home = self.config.agent_homes[agent]

        # Canonicalise INBOUND too. This is the other path that writes a Message
        # to storage, and the one where the message is genuinely hostile rather
        # than merely untrusted. Without it a remote sender chose message_id
        # (shadowing a real message in find()), date (controlling reader
        # ordering), and kilobytes of free text in the identifier fields — and a
        # remote-chosen message_id then satisfied the outbound "parent must be
        # visible" check. The inversion was applied to one path and not its twin,
        # which is the same sibling-blindness the earlier rounds kept finding.
        # STRIP UPSTREAM AUTHENTICATION CLAIMS AT INGRESS.
        #
        # The spec makes this a MUST and it previously had ZERO call sites: the
        # constant was defined, a policy requirement was written around it, and
        # nothing invoked it. Today the guarantee happened to hold by
        # construction, because Message has no field for these headers — but a
        # property of the current data model is not a control, and §5.3 already
        # permits an implementation to retain transport headers for forensics.
        # The moment one does, the requirement is silently absent.
        strip_inbound_headers(message)

        remote_sender = message.sender
        message.message_id = new_id("msg")
        message.date = _now_iso()

        # BOUND EVERY SIGNATURE-COVERED FIELD *BEFORE* THE LABEL IS MINTED.
        #
        # This ordering is the whole finding, and the comment that used to sit
        # here argued for the opposite with a reason that sounded right:
        # "classify against the message AS RECEIVED, because a truncated body
        # legitimately fails verification and classifying afterwards would
        # report SUSPECT for our own edit."
        #
        # It produced a lie. The label was minted over the received content and
        # the STORED content was then truncated, so a message could read
        # `attested` while the bytes on disk did not verify — 5 of 10 realistic
        # inputs, including a body one byte over the cap and any send to 65
        # recipients. A reader saw a correspondent's verified badge over a
        # prefix of what they wrote, with any trailing retraction removed.
        #
        # The error was preferring OUR feelings about the sender to the reader's
        # ability to check. If we edit the message, the signature no longer
        # covers what we stored, and the honest label is the one that says so.
        # Truncation is now recorded in the audit trail, so an investigator can
        # still tell "the sender lied" from "we edited it".
        #
        # The invariant this establishes, which is what the tests assert:
        #     verify(deserialize(stored_bytes)) == (stored.trust == ATTESTED)
        truncated = self._bound_fields(message)
        message.trust = self.classify_inbound(message, agent).value
        # AUTHORIZE FIRST, THEN DO THE EXPENSIVE WORK.
        #
        # The visibility checks below each scan and deserialise the recipient's
        # whole mailbox. Running them before the contact decision made an
        # UNLISTED sender — whose message is bound for quarantine and will never
        # be threaded at all — pay 2 x O(mailbox) per message, measured at 4000
        # deserialisations against a 2000-message mailbox. The victim's mailbox
        # grows as mail lands, so the cost per hostile message rises with the
        # traffic the attacker has already sent. Nothing that only matters for
        # DELIVERED mail may run before we know the mail will be delivered.
        permitted = self.contacts.permits(agent, message.sender) if self.contacts else False
        if not permitted:
            # Identifiers are dropped rather than preserved: quarantined mail is
            # hostile by assumption, and a reader inspecting it should not find
            # it threaded against a real conversation.
            message.parent, message.thread_id = None, new_id("thr")
            reason = f"sender '{message.sender}' is not in the contact list for '{agent}'"
            quarantine(home, message, reason)
            if self.audit:
                self.audit.inbound(sender=message.sender, recipient=recipient,
                                   message_id=message.message_id,
                                   decision="quarantined", reason=reason,
                                   trust=message.trust)
            return {"ok": True, "decision": "quarantined", "reason": reason}

        # SHAPE IS NOT VISIBILITY, and the outbound path already knows that.
        #
        # Checking that `parent` merely LOOKS like an identifier let a remote
        # sender graft a message onto a conversation it was never part of: the
        # reader's client threads it under that parent, so it inherits the
        # apparent standing of the exchange above it. Outbound requires the
        # parent to be visible in the recipient's own mailbox; inbound checked
        # only the regex. Same laundering an earlier round closed on the submit
        # path, still open on its twin — which is the asymmetry that keeps
        # recurring, so it is now closed on both.
        #
        # ONE scan, not two. store_find() and store_thread() each deserialise the
        # entire mailbox, so asking both questions separately doubled the cost of
        # every delivered message for no additional guarantee.
        existing = store_read_all(home) if (message.parent or message.thread_id) else []
        if message.parent is not None:
            visible = any(m.message_id == message.parent for m in existing)
            if not _ID_RE.match(message.parent or "") or not visible:
                message.parent = None
        if message.thread_id and not _THR_RE.match(message.thread_id):
            message.thread_id = new_id("thr")
        elif message.thread_id and message.parent is None:
            # A well-formed thread_id with no visible parent is an assertion of
            # membership in a conversation this sender has shown no part of. It
            # gets its own thread rather than the one it named.
            if any(m.thread_id == message.thread_id for m in existing):
                message.thread_id = new_id("thr")
        message.sender = remote_sender

        deliver(home, message)
        if self.audit:
            self.audit.inbound(sender=message.sender, recipient=recipient,
                               message_id=message.message_id, decision="delivered",
                               trust=message.trust,
                               # So an investigator can tell "the sender lied"
                               # apart from "we edited it and the signature
                               # stopped covering what we stored".
                               reason=(f"broker truncated: {','.join(truncated)}"
                                       if truncated else None))
        return {"ok": True, "decision": "delivered"}

    # -------------------------------------------------------------- credentials

    # ---- reads -----------------------------------------------------------
    #
    # THE MAILBOX IS DERIVED FROM THE KERNEL IDENTITY, NEVER FROM THE REQUEST.
    #
    # Neither method below accepts a home, a path, or an agent name. That is the
    # whole security content of putting reads behind the broker: if a read
    # request could name the mailbox it wanted, an agent would read any peer's
    # mail by asking for it, and the authorization layer would be decoration.
    # The submission path already refuses a payload-claimed identity for exactly
    # this reason (§ handle); reads inherit the same rule by construction,
    # because there is no parameter through which to claim one.
    #
    # These exist so the CLI has a path that is not `import store`. A read that
    # bypasses the broker leaves no audit trace and answers to no allowlist —
    # the framework's own tooling was the first thing doing it.

    def _own_mailbox(self, agent: str) -> Path:
        """The requesting agent's own mailbox, or a refusal.

        Fails closed on an unmapped agent, matching `identify`: a default here
        would hand a caller somebody else's mail.
        """
        home = self.config.agent_homes.get(agent)
        if home is None:
            raise PermissionError(
                f"'{agent}' has no provisioned mailbox; refusing the read. "
                "Reaching the socket is not authorization."
            )
        return home

    def list_messages(self, agent: str, thread: Optional[str] = None) -> Dict[str, Any]:
        """Every message in the requesting agent's own mailbox."""
        home = self._own_mailbox(agent)
        msgs = _store_read_all(home)
        if thread:
            msgs = [m for m in msgs if m.thread_id == thread]
        return {"ok": True, "messages": [m.to_dict() for m in msgs]}

    def read_message(self, agent: str, message_id: str) -> Dict[str, Any]:
        """One message from the requesting agent's own mailbox."""
        home = self._own_mailbox(agent)
        msg = _store_find(home, message_id)
        if msg is None:
            # Not found and not-yours are the same answer on purpose: a
            # distinguishable "exists but not yours" turns the broker into an
            # oracle for other agents' message ids.
            return {"ok": False, "error": "no such message"}
        return {"ok": True, "message": msg.to_dict()}

    def identify(self, conn: socket.socket) -> str:
        """Authenticate the connecting process from kernel-supplied credentials.

        SO_PEERCRED returns the pid/uid/gid the kernel recorded at connect time.
        The peer cannot influence it, which is what makes a world-writable socket
        safe to expose: reaching the socket is not identity, and identity is not
        something the request gets to assert.

        Fails closed on every path. An unmapped uid is refused rather than given a
        default agent, because a default here would hand an unknown caller
        somebody's contact list.
        """
        try:
            uid = peer_uid(conn)
        except (OSError, AttributeError, struct.error) as e:
            raise PermissionError(
                f"cannot determine peer credentials ({e}); refusing to accept a "
                "submission from an unidentifiable process"
            ) from e

        agent = self.config.agent_uids.get(uid)
        if not agent:
            raise PermissionError(
                f"uid {uid} is not a provisioned agent; refusing submission. "
                "Reaching the socket is not authorization."
            )
        return agent

    def assert_credential_custody(self) -> None:
        """Refuse to run if the transport credential is exposed.

        THIS EXISTS BECAUSE THE CHECK BELOW WAS PREVIOUSLY NEVER CALLED. It was
        written, unit-tested with negative controls, and then invoked by nothing
        but its own tests — a guarantee that was verified in the abstract and
        enforced nowhere. Starting the broker is the moment the guarantee has to
        hold, so the check belongs on that path.
        """
        if self.credential_readable_by_others():
            raise PermissionError(
                f"credential {self.config.credentials_path} is readable by group "
                "or other. The security property depends on agents being unable to "
                "read it. Refusing to start; chmod 600 and retry."
            )
        # The contact list is re-read on every decision, so an agent that can
        # WRITE it grants itself any recipient instantly — the allowlist would
        # become advisory in the same way an agent-side check is. Guarding the
        # credential while leaving the policy file writable protects the key to a
        # door and leaves the wall down.
        cp = self.config.contacts_path
        if cp and Path(cp).exists():
            mode = Path(cp).stat().st_mode
            if mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise PermissionError(
                    f"contact list {cp} is writable by group or other. It is "
                    "re-read per decision, so anyone who can write it can grant "
                    "themselves any recipient. Refusing to start; chmod 644 or 600."
                )

        # THE DIRECTORY, NOT ONLY THE FILE.
        #
        # Checking the file's mode validates the wrong object. Replacing a file
        # needs write permission on the DIRECTORY, not on the file: an agent who
        # can write the containing directory calls os.replace() and swaps in a
        # contact list granting itself every recipient, while the original file
        # sat at a blameless 0644 and passed this check. Round 7 demonstrated the
        # swap end to end — refused before, delivered after, custody check green
        # throughout. A guard that inspects an object the attacker never has to
        # touch does not merely miss the attack, it certifies against it.
        # THE FILE'S OWNER, NOT ONLY ITS MODE.
        #
        # The mode check asks "can group or other write this?" and never asks
        # who owns it. A contact list OWNED BY AN AGENT at mode 0644 passes —
        # the owner needs no group or other write bit to rewrite their own file,
        # and the list is re-read per decision, so that is a self-grant of any
        # recipient. Round 7 fixed file-versus-directory and round 8 found the
        # same asymmetry one level shallower, which is the pattern this campaign
        # keeps producing: the fix was applied where it was demonstrated.
        for label, target in (("credential", self.config.credentials_path),
                              ("contact list", self.config.contacts_path)):
            if not target or not Path(target).exists():
                continue
            owner = Path(target).stat().st_uid
            if owner != os.getuid():
                raise PermissionError(
                    f"the {label} ({target}) is owned by uid {owner}, not by the "
                    f"broker (uid {os.getuid()}). Its owner can rewrite it at any "
                    "time regardless of its mode. Refusing to start."
                )

        # THE AUDIT DIRECTORY TOO.
        #
        # Round 7 guarded the directories holding the credential and the contact
        # list, and left out the one holding the audit log — which the spec makes
        # mandatory and whose integrity is explicitly in scope. An agent able to
        # write it can delete the record outright, or plant a FIFO at the lock
        # path and wedge every submission on the host. Guarding two of the three
        # config directories is the sibling-blindness this campaign has now found
        # in seven consecutive rounds.
        for label, target in (("credential", self.config.credentials_path),
                              ("contact list", self.config.contacts_path),
                              ("audit log", self.config.audit_path)):
            if not target:
                continue
            parent = Path(target).parent
            if not parent.exists():
                continue
            st = parent.stat()
            if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise PermissionError(
                    f"the directory holding the {label} ({parent}) is writable by "
                    "group or other. Anyone who can write that directory can "
                    "replace the file inside it regardless of the file's own mode. "
                    "Refusing to start; chmod 755 the directory."
                )
            if st.st_uid != os.getuid():
                raise PermissionError(
                    f"the directory holding the {label} ({parent}) is owned by uid "
                    f"{st.st_uid}, not by the broker (uid {os.getuid()}). Its owner "
                    "can replace the file at any time. Refusing to start; move the "
                    "configuration into a broker-owned directory."
                )

    def credential_readable_by_others(self) -> bool:
        """True if any non-owner can read the credential file.

        Exposed as a method so the guarantee is testable rather than asserted.
        The security property depends on this being False; a comment claiming it
        proves nothing.
        """
        p = self.config.credentials_path
        if not p or not Path(p).exists():
            return False
        mode = Path(p).stat().st_mode
        return bool(mode & (stat.S_IRGRP | stat.S_IROTH))


# ---------------------------------------------------------------------- server

#: Largest submission accepted, in bytes. Without a cap, readline() buffers until
#: memory runs out, and any local process can do it.
MAX_REQUEST_BYTES = 1 << 20  # 1 MiB

#: Idle connections are dropped. Without this a handful of open-and-wait
#: connections pin threads and file descriptors indefinitely.
CONNECTION_TIMEOUT = 30.0


class _Handler(socketserver.StreamRequestHandler):
    timeout = CONNECTION_TIMEOUT

    def handle(self) -> None:
        broker: Broker = self.server.broker  # type: ignore[attr-defined]
        resp: Dict[str, Any]
        try:
            # IDENTITY COMES FROM THE KERNEL, NOT THE PAYLOAD.
            #
            # The socket is world-writable, so any local process can connect. If
            # the submitter's identity were taken from the request body, an agent
            # could name a peer and inherit that peer's contact list — the
            # reachable set would become the union of everyone's contacts, and the
            # audit log would blame the impersonated agent. SO_PEERCRED is supplied
            # by the kernel about the connected process and cannot be forged by it.
            sender = broker.identify(self.connection)

            # A TOTAL deadline, not a per-recv one. socket timeout resets on
            # every byte received, so a one-byte-per-second trickle holds a
            # thread forever while never exceeding it. Availability is a security
            # property when one process can starve every other agent's mail.
            deadline = time.monotonic() + CONNECTION_TIMEOUT
            self.connection.settimeout(CONNECTION_TIMEOUT)
            raw = b""
            while not raw.endswith(b"\n"):
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"request not completed within {CONNECTION_TIMEOUT}s")
                chunk = self.connection.recv(65536)
                if not chunk:
                    break
                raw += chunk
                if len(raw) > MAX_REQUEST_BYTES:
                    raise ValueError(f"request exceeds {MAX_REQUEST_BYTES} bytes")
            if not raw:
                return
            req = json.loads(raw.decode("utf-8"))
            claimed = req.get("sender")
            if claimed is not None and claimed != sender:
                # Refused rather than silently corrected: a client that believes
                # it is someone else has a bug or an intention, and both deserve
                # a record.
                if broker.audit:
                    broker.audit.refused(
                        sender=sender, recipients=[],
                        reason=f"identity mismatch: peer is '{sender}', claimed '{claimed}'")
                raise PermissionError(
                    f"submitted as '{claimed}' but the connecting process is '{sender}'")

            # OPERATION DISPATCH. `op` is absent in every client written before
            # reads existed, and absent means "submit" — so the wire stays
            # compatible with a client that only ever learned to send, and the
            # submission path is unchanged for it.
            #
            # Note what the read operations do NOT take: a home, a path, or an
            # agent name. `sender` here is the kernel-established identity, and
            # it is the only thing that selects a mailbox.
            op = req.get("op", "submit")
            if op == "submit":
                msg = Message.from_dict(req["message"])
                resp = broker.submit(sender, msg)
            elif op == "list":
                resp = broker.list_messages(sender, thread=req.get("thread"))
            elif op == "read":
                resp = broker.read_message(sender, req["message_id"])
            else:
                # Named rather than ignored: a client asking for an operation
                # this broker does not have is a version skew or an intention,
                # and silently treating it as a submission would be worse than
                # either.
                raise ValueError(f"unknown operation '{op}'")
        except Exception as e:  # noqa: BLE001 - a broker that dies on one bad
            # request stops serving every agent; answer with the error instead.
            resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            if broker.audit:
                # NAME THE SUBMITTER. §3.3 requires every submission record carry
                # the sending identity; an unhandled-exception refusal wrote one
                # with no sender and no recipients at all. The kernel-established
                # identity is in scope right here and was simply not written —
                # so the one record an investigator would reach for was the one
                # that said nothing about who.
                broker.audit.error(context="request",
                                   detail=f"{type(e).__name__}: {e}",
                                   sender=sender if "sender" in dir() else None)
        try:
            self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))
        except OSError as e:
            # The peer may have hung up. Log it rather than letting the write
            # throw out of handle() unrecorded — an outage with no trace is the
            # gap the audit log exists to close.
            if broker.audit:
                broker.audit.error(context="response", detail=str(e))


#: Total connections served at once. Beyond this the broker refuses immediately
#: rather than spawning another thread.
MAX_CONCURRENT_CONNECTIONS = 64

#: In-flight connections permitted to a single uid. This is the bound that
#: matters: the total cap alone lets ONE agent occupy every slot and starve
#: every other agent, which is the same "availability is a security property"
#: argument the read loop already makes about slow trickles.
MAX_CONNECTIONS_PER_UID = 8

#: Overload refusals are audited at most this often per uid. Without the
#: interval, the record of the flood becomes a second flood — an attacker who
#: cannot exhaust memory would exhaust the disk through the log instead.
OVERLOAD_AUDIT_INTERVAL = 60.0


class _Server(socketserver.ThreadingUnixStreamServer):
    """Concurrency-metered threading server.

    ThreadingMixIn spawns one unbounded thread per accepted connection. With a
    world-writable socket that is a denial-of-service primitive available to any
    agent that can reach it: round 6 drove the broker from 20 MB to 996 MB RSS
    with 500 held connections from a SINGLE uid, and the broker is the only path
    mail can leave any agent, so killing it silences the whole host.

    Metering happens in process_request, which runs on the accept thread BEFORE
    a worker exists — refusing an over-quota connection therefore costs no
    thread and no buffer.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self._meter_lock = threading.Lock()
        self._inflight: Dict[Any, Optional[int]] = {}
        self._per_uid: Dict[int, int] = {}
        self._overload_audited: Dict[Optional[int], float] = {}
        super().__init__(*args, **kwargs)

    def _acquire(self, request: Any, uid: Optional[int]) -> bool:
        with self._meter_lock:
            if len(self._inflight) >= MAX_CONCURRENT_CONNECTIONS:
                return False
            # `None` gets a bucket like everyone else. The comment used to claim
            # unidentifiable peers were "metered as one anonymous bucket rather
            # than waved through" — they were metered as SIXTY-FOUR, because the
            # per-uid bound was skipped entirely for None and only the global cap
            # applied. Anonymous peers could therefore fill every slot and lock
            # out every real agent. They will be refused by identify() anyway,
            # so the bound costs nothing legitimate.
            if self._per_uid.get(uid, 0) >= MAX_CONNECTIONS_PER_UID:
                return False
            self._inflight[request] = uid
            self._per_uid[uid] = self._per_uid.get(uid, 0) + 1
            return True

    def _release(self, request: Any) -> None:
        with self._meter_lock:
            if request not in self._inflight:
                return
            uid = self._inflight.pop(request)
            remaining = self._per_uid.get(uid, 0) - 1
            if remaining > 0:
                self._per_uid[uid] = remaining
            else:
                self._per_uid.pop(uid, None)

    def _audit_overload(self, uid: Optional[int]) -> None:
        now = time.monotonic()
        with self._meter_lock:
            if now - self._overload_audited.get(uid, 0.0) < OVERLOAD_AUDIT_INTERVAL:
                return
            self._overload_audited[uid] = now
            depth = len(self._inflight)
            per_uid = self._per_uid.get(uid, 0) if uid is not None else 0
        broker = getattr(self, "broker", None)
        if broker is not None and broker.audit:
            # Recorded, because a refusal nobody can see is indistinguishable
            # from an outage — the exact gap the audit log exists to close.
            broker.audit.error(
                context="overload",
                detail=(f"connection refused: uid={uid} in-flight={depth} "
                        f"uid-in-flight={per_uid} "
                        f"limits=({MAX_CONCURRENT_CONNECTIONS},{MAX_CONNECTIONS_PER_UID}); "
                        f"further refusals for this uid suppressed for "
                        f"{OVERLOAD_AUDIT_INTERVAL:.0f}s"))

    def process_request(self, request, client_address):  # type: ignore[override]
        try:
            uid: Optional[int] = peer_uid(request)
        except (OSError, AttributeError, struct.error):
            # Unidentifiable peers are metered as one anonymous bucket rather
            # than waved through: identify() will refuse them anyway, but not
            # before a thread exists to do the refusing.
            uid = None
        if not self._acquire(request, uid):
            self._audit_overload(uid)
            # SAY WHY. The spec requires an agent be able to tell that its
            # message was refused AND why; an overload used to close the socket
            # silently, and the client's generic handler then reported "a
            # submission over the broker's size limit is the usual cause" —
            # which is false, and sends whoever is debugging it to the wrong
            # place. Best-effort and non-blocking: this runs on the accept
            # thread, so it must never wait on a peer that has stopped reading.
            try:
                request.setblocking(False)
                request.sendall((json.dumps({
                    "ok": False,
                    "error": (f"broker at capacity: no more than "
                              f"{MAX_CONNECTIONS_PER_UID} concurrent connections "
                              f"per agent ({MAX_CONCURRENT_CONNECTIONS} total). "
                              "The message was NOT sent. Retry."),
                }) + "\n").encode("utf-8"))
            except OSError:
                pass
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def shutdown_request(self, request):  # type: ignore[override]
        # Called exactly once per accepted connection on every path — after the
        # handler thread finishes, and directly when the connection was refused
        # above. Releasing here rather than in the handler keeps the count
        # correct even when handle() raises.
        self._release(request)
        super().shutdown_request(request)


def serve(broker: Broker) -> _Server:
    """Bind the submission socket and start serving.

    The socket is group/world writable so any agent may submit; that is safe
    precisely because submission is not authority. Everything an agent could do
    by reaching this socket is checked against its contact list on the other side.
    """
    # Enforce the guarantee at the moment it starts mattering.
    broker.assert_credential_custody()
    if not broker.config.agent_uids:
        raise PermissionError(
            "no agent_uids configured: with a world-writable socket and no uid "
            "mapping, no submitter can be authenticated and every submission "
            "would be refused. Refusing to start rather than serve a socket that "
            "cannot identify anyone.")
    path = Path(broker.config.socket_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    server = _Server(str(path), _Handler)
    server.broker = broker  # type: ignore[attr-defined]
    os.chmod(path, 0o666)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
