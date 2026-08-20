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

import contextlib
import hashlib
import json
import os
import re
import socket
import socketserver
import stat
import sys
import struct
import threading
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .audit import AuditLog
from .contacts import ContactBook, ContactListError
from .models import Message, new_id, _now_iso
from .trust import TrustClass, LOCAL_SUBMISSION
from .crypto import verify
from .store import deliver, ensure_maildir
from . import store

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


#: One advisory lock per disposition store, keyed by directory. The threading
#: lock covers handler threads inside one broker (this server is multi-threaded
#: by design); the file lock covers separate broker processes. Two kinds of
#: concurrent writer, two locks — the same pair the audit log settled on after
#: its rotation was measured losing 42 of 50 records under ordinary concurrency.
_DISPOSITION_LOCKS: Dict[str, threading.Lock] = {}
_DISPOSITION_LOCKS_GUARD = threading.Lock()


@contextlib.contextmanager
def _disposition_lock(record: Path):
    """Serialise the read-modify-write of one disposition store.

    Spec O5d.10 "disposition-appends-are-safe-under-concurrent-writers". The
    lock spans BOTH the read and the write: locking them separately leaves
    exactly the window it is meant to close, since the loss happens between
    them rather than inside either one.

    The lock file is per DIRECTORY rather than per record. A per-record lock
    would serialise nothing useful and would litter the store with one lock file
    per message, which the retention sweep would then have to learn to ignore.
    """
    d = record.parent
    key = str(d)
    with _DISPOSITION_LOCKS_GUARD:
        tlock = _DISPOSITION_LOCKS.setdefault(key, threading.Lock())
    with tlock:
        if fcntl is None:  # pragma: no cover - non-POSIX
            yield
            return
        lockfile = d / ".dispositions.lock"
        with open(lockfile, "a+b") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

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

    #: Broker-owned quarantine for refused INTERNET mail (the inbound module
    #: writes it). Optional: a deployment without internet inbound has none,
    #: and status_counts then reports zero quarantined rather than failing.
    inbound_quarantine: Optional[Path] = None

    #: Broker-owned disposition records: what became of each SUBMITTED message.
    #: Agent-READABLE (0644) and broker-written, the same shape as the contacts
    #: file. The sender's own copy of what it composed is immutable and lives in
    #: the agent's store; the FATE of that message is mutable (submitted ->
    #: deferred -> bounced) and is established by components the agent cannot
    #: see, so it lives where its writer lives and crosses to the agent by READ.
    #: Without it an agent holds a sent copy and cannot tell whether it left,
    #: which is the outbound face of a silent drop.
    dispositions_dir: Optional[Path] = None

    #: Broker-owned pickup boxes (handoff_dir/<agent>/): accepted mail waits
    #: here until the recipient ingests it into its own store. Optional for
    #: the same reason as the quarantine.
    inbound_handoff: Optional[Path] = None

    #: The pre-send OPSEC scrub, ON the submission path (spec O5e.1
    #: "the-gate-must-accept-a-composed-message"). It lives at the BROKER
    #: rather than in the client for the same reason every other check does:
    #: a scrub in code the agent can edit is documentation.
    #:
    #: `None` means NO GATE, and that is a deployment state rather than a
    #: default to be assumed safe -- submit() says so out loud on every send,
    #: because a gate that is silently absent is exactly the specified-but-
    #: absent trap this subsystem keeps finding.
    opsec_scan: Optional[Any] = None

    #: What to do with a part that could not be read as text (spec O5e.6
    #: "fail-closed-applies-to-the-scan-not-the-message"). The deployment
    #: chooses; what is forbidden is the third option, where an unscanned part
    #: silently counts as scanned.
    refuse_unscanned: bool = True

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

    def quarantine_refused(self, agent: str, message: Message, reason: str) -> Path:
        """Retain refused mail in the BROKER's quarantine, with its reason.

        Retained rather than rejected: rejecting at the transport boundary
        reveals which addresses exist, and legitimately forwarded mail can
        arrive from an unexpected envelope sender. Quarantine keeps the
        evidence and keeps the decision reversible — but it keeps it where the
        REFUSED party cannot edit it, which is why this is broker-owned rather
        than a directory inside the recipient's home.
        """
        if self.config.inbound_quarantine is None:
            raise DeliveryError(
                "no quarantine directory configured: there is nowhere to retain "
                "refused mail where the refused party cannot edit it. Refusing "
                "rather than dropping the evidence.")
        q = Path(self.config.inbound_quarantine)
        q.mkdir(mode=0o700, parents=True, exist_ok=True)
        stem = f"{int(time.time())}-{message.message_id}"
        (q / f"{stem}.amsg").write_text(message.serialize())
        (q / f"{stem}.json").write_text(json.dumps({
            "kind": "bundle",
            "quarantined_at": _now_iso(),
            "message_id": message.message_id,
            "sender": message.sender,
            "recipient": self.config.address_for(agent),
            "authorization": {"outcome": "deny", "reason": reason},
        }, indent=1))
        return q / f"{stem}.amsg"

    def record_disposition(self, agent: str, message_id: str, state: str,
                           detail: str = "", *,
                           recipients: Optional[List[str]] = None,
                           content_sha256: Optional[str] = None) -> Optional[Path]:
        """Write what became of a submitted message. Broker-owned, agent-readable.

        PER RECIPIENT, not per message — spec O5d.8 "disposition-is-per-recipient".
        Transport outcomes are per-recipient by nature (delivered to one, bounced
        for another), so a single per-message history cannot represent them. The
        message-level view is DERIVED from these records rather than stored
        beside them, where the two could drift.

        Message-LEVEL refusals (`denied`, `rate-refused`, `gate-refused`) are
        decisions about the submission as a unit, so they are written against
        EVERY named recipient with the same value — spec O5d.8a
        "message-level-refusal-writes-a-record-for-every-recipient". Recording
        them only against the offending recipients would leave the permitted ones
        with no record at all, and the derived view would have nothing to read.

        Within each recipient the states are APPENDED as a history rather than
        overwritten — spec O5d.4 "disposition-is-a-history-not-a-last-value" —
        because they are a SEQUENCE and the last one alone loses the story. A
        bounce after three deferrals is a different fact from an immediate
        bounce, and only a sequence tells them apart.

        `content_sha256` is the hash of the submitted content, kept here because
        this is the one broker-owned store the agent can already read — spec
        O5c.7a "the-hash-lives-where-its-verifier-can-reach-it". No new store and
        no new access path. Written once and never rewritten: a hash that changes
        is not evidence of anything.

        Returns None when no disposition store is configured, and says so on
        stderr rather than silently doing nothing: a deployment that submits mail
        while recording no fate has rebuilt the silent drop on the sending side.
        """
        if self.config.dispositions_dir is None:
            print("⚠️ MACF: no disposition store configured; the fate of "
                  f"{message_id} is unrecorded and the sender cannot learn it",
                  file=sys.stderr)
            return None
        if not recipients:
            # A fate belongs to a message-recipient PAIR — spec O5d.8c
            # "conservation-unit-is-the-message-recipient-pair". With no
            # recipient there is no pair, so there is nothing whose fate this
            # would be, and inventing a placeholder would put a row in the
            # conservation ledger that can never reach a terminal state.
            print(f"⚠️ MACF: no recipients given for {message_id}; nothing to "
                  "record a disposition against", file=sys.stderr)
            return None

        d = Path(self.config.dispositions_dir)
        d.mkdir(mode=0o755, parents=True, exist_ok=True)
        f = d / f"{message_id}.json"
        at = _now_iso()

        # THE LOCK SPANS READ AND WRITE — spec O5d.10
        # "disposition-appends-are-safe-under-concurrent-writers".
        with _disposition_lock(f):
            # THREE STATES, KEPT DISTINCT. The version this replaces collapsed
            # them into one `except (OSError, ValueError): history = []`, which
            # is not a fallback but EVIDENCE DESTRUCTION: a record that exists
            # and cannot be parsed was silently replaced by an empty one, and
            # the next write committed that emptiness to disk. It did so inside
            # the function whose whole purpose is to preserve what became of a
            # message — the audit log's own rotation defect, reproduced one
            # subsystem later, which is exactly what O5d.10
            # "disposition-appends-are-safe-under-concurrent-writers" forbids.
            try:
                rec = json.loads(f.read_text())
            except FileNotFoundError:
                # EXPECTED, and the only one of the three that is: this is the
                # first fate recorded for this message. Not a failure, so not a
                # warning — a warning here would train readers to ignore the
                # other two.
                rec = {}
            except (OSError, json.JSONDecodeError, ValueError) as e:
                # The record EXISTS and could not be read. Whatever it held is
                # evidence, and overwriting it destroys the only copy. Warn,
                # log, and let the caller decide — per the warn-and-reraise rule
                # for utility functions. A submission that fails loudly beats a
                # delivery nobody can account for, which is the same trade the
                # audit log makes when it runs out of descriptors.
                print(f"⚠️ MACF: disposition record {f.name} exists and cannot "
                      f"be read ({e}); REFUSING to overwrite it — the prior "
                      f"history is the evidence this store exists to keep",
                      file=sys.stderr)
                try:
                    from macf.agent_events_log import append_event
                    append_event("error", {
                        "source": "amail.broker.record_disposition",
                        "error": str(e), "error_type": type(e).__name__,
                        "message_id": message_id,
                        "fallback": "none; raised to caller rather than "
                                    "overwriting an unreadable record",
                    })
                except (ImportError, OSError, ValueError) as log_e:
                    print(f"⚠️ MACF: event logging also failed: {log_e}",
                          file=sys.stderr)
                raise

            rec.setdefault("message_id", message_id)
            rec.setdefault("agent", agent)
            if content_sha256 and not rec.get("content_sha256"):
                rec["content_sha256"] = content_sha256
            per = rec.setdefault("recipients", {})
            for r in recipients:
                per.setdefault(r, {"history": []})["history"].append(
                    {"state": state, "detail": detail, "at": at})

            tmp = f.with_name(f.name + ".tmp")
            tmp.write_text(json.dumps(rec, indent=1))
            # World-readable on purpose: the SENDER must be able to read the
            # fate of its own mail with no broker running, and a fate is not a
            # secret. Set before the rename so no reader ever observes 0600.
            tmp.chmod(0o644)
            # Atomic replace rather than write-in-place: a concurrent READER
            # holds no lock (the agent reads this by filesystem, deliberately),
            # so it must never observe a half-written record.
            os.replace(tmp, f)
        return f

    def _scrub(self, message: Message) -> Optional[str]:
        """Run the pre-send gate. Returns a refusal reason, or None to pass.

        THE ABSENCE OF A GATE IS ANNOUNCED, not defaulted to safe. A deployment
        with `opsec_scan=None` sends unscrubbed, which is a legitimate choice
        for a closed fleet and an alarming one anywhere else -- and the only
        thing separating those two cases is whether anyone knows. Silence here
        would make an unconfigured gate indistinguishable from a passing one,
        which is the specified-but-absent trap in its purest form.

        THE GATE'S OWN FAILURE IS A REFUSAL. If the scanner raises, this
        refuses the message rather than passing it: a gate that fails open is
        not a gate, and an exception is exactly the case where the temptation
        to continue is strongest because everything else about the send worked.
        """
        scan = getattr(self.config, "opsec_scan", None)
        if scan is None:
            print(f"⚠️ MACF: no pre-send scrub configured; {message.message_id} "
                  f"is being sent UNSCANNED", file=sys.stderr)
            return None
        try:
            result = scan(message)
        except Exception as e:  # noqa: BLE001 - see docstring: fail closed
            print(f"⚠️ MACF: the pre-send scrub raised ({type(e).__name__}: {e}); "
                  f"refusing {message.message_id} rather than sending unscanned",
                  file=sys.stderr)
            return f"scrub failed to run ({type(e).__name__})"

        if getattr(result, "findings", None):
            # The reason names CATEGORIES and quotes nothing: a refusal message
            # travels into logs and notices, which are themselves outward-facing.
            return result.reason()
        if getattr(result, "unscanned", None) and self.config.refuse_unscanned:
            return result.reason()
        return None

    def _record_fate(self, sender: str, message: Message, state: str,
                     detail: str = "", recipients: Optional[List[str]] = None) -> None:
        """Record a fate without letting the recording break the send.

        Called from the live submission path, so its failure modes matter as
        much as its success. Two rules, and they pull in opposite directions:

        A missing disposition store is already announced by record_disposition
        and must not abort a delivery that has otherwise happened — refusing
        the send would make an unconfigured store worse than a broken one.

        But an UNREADABLE EXISTING RECORD raises (it refuses to overwrite
        evidence), and swallowing that here would put the silence straight back
        in: the send would report success while the fate went unrecorded and
        nobody learned. So it is caught, announced, and carried on the RESULT
        rather than dropped — the caller can see that the mail moved and its
        fate did not get written down, which is a state worth knowing about and
        not one worth failing a completed delivery over.
        """
        try:
            self.record_disposition(
                sender, message.message_id, state, detail,
                recipients=recipients if recipients is not None else list(message.to),
                content_sha256=self._content_sha256(message))
        except (OSError, ValueError) as e:
            print(f"⚠️ MACF: the fate of {message.message_id} could not be "
                  f"recorded ({e}); the mail moved and the record did not",
                  file=sys.stderr)
            if self.audit:
                self.audit.error(context="disposition",
                                 detail=f"{message.message_id}: {e}")

    @staticmethod
    def _content_sha256(message: Message) -> Optional[str]:
        """Hash of the NAMED CANONICAL SUBSET, not of the serialized message.

        Spec O5c.7 "the-broker-records-the-hash-of-the-submitted-content" asks
        for the exact submitted bytes OR a named subset. The subset is required
        here rather than preferred: canonicalize() RE-MINTS message_id and date,
        so the agent's stored bytes and the submitted bytes can never be equal
        and a raw comparison would report mismatch on every message ever sent.

        `signing_payload` is that subset, and it already excludes exactly those
        two fields for exactly this reason — the broker re-mints on inbound too,
        and covering them would have made every stored message unverifiable
        after ingress. Reusing it means there is ONE definition of "what the
        message is" rather than two that can drift.
        """
        try:
            from .crypto import signing_payload
            return hashlib.sha256(signing_payload(message)).hexdigest()
        except (ImportError, ValueError, TypeError) as e:
            print(f"⚠️ MACF: could not compute the content hash for "
                  f"{message.message_id} ({e}); the disposition is recorded "
                  f"without it, so the sender's copy is unverifiable",
                  file=sys.stderr)
            return None

    def hand_off(self, agent: str, message: Message, trust: str) -> Path:
        """Hand a delivered message into the recipient's pickup box.

        UNIFIED DELIVERY. This replaced a direct write into the recipient's
        Maildir — the broker reaching across a uid boundary into a home it does
        not own. That worked only because the broker ran as root, and the
        pickup-box model had already deleted the same operation from the
        INTERNET path; agent mail kept it for months because nothing exercised
        the path. One mechanism now: the broker writes only its own stores, the
        recipient ingests into its own, and no component on the mail path holds
        privilege.

        The sidecar carries the broker's AUTHORIZATION judgement, which is the
        broker's to make and the recipient's to consume: only the broker holds
        contact books, and only it may say a sender is a contact of this
        recipient. The recipient can edit the sidecar once it owns it — but the
        authoritative copy is the audit record, so that only fools itself, and
        an agent lying to itself is not a security boundary. If a sidecar
        classification ever crosses an AGENT boundary that stops being true and
        it becomes forgeable input; see the spec's handoff section.

        The signature verdict is deliberately NOT decided here — the recipient
        verifies at ingest with the keys it holds. This classification is the
        broker's view, recorded so the two can be compared.
        """
        if self.config.inbound_handoff is None:
            raise DeliveryError(
                "no handoff directory configured: delivery is by pickup box and "
                "there is nowhere to hand this message. Refusing rather than "
                "reporting a delivery that did not happen.")
        box = Path(self.config.inbound_handoff) / agent
        box.mkdir(mode=0o2770, parents=True, exist_ok=True)
        payload = message.serialize().encode("utf-8")
        stem = f"{int(time.time())}-{message.message_id}"
        sidecar = {
            "kind": "bundle",
            "handed_off_at": _now_iso(),
            "message_id": message.message_id,
            "sender": message.sender,
            "recipient": self.config.address_for(agent),
            "raw_sha256": hashlib.sha256(payload).hexdigest(),
            "authorization": {
                "outcome": "deliver-pull",
                "reason": f"contact of '{agent}'",
            },
            # The broker's own read, for comparison against the recipient's.
            # Disagreement is information, not noise: it is what a compromised
            # or stale broker looks like from the recipient's side.
            "broker_trust": trust,
        }
        base = box / stem
        # Sidecar first, message second, mirroring the inbound handoff: a
        # message without its sidecar is an unexplained artifact, while a
        # sidecar without its message is a visibly interrupted delivery.
        base.with_suffix(".json").write_text(json.dumps(sidecar, indent=1))
        base.with_suffix(".json").chmod(0o640)
        base.with_suffix(".amsg").write_bytes(payload)
        base.with_suffix(".amsg").chmod(0o640)
        return base.with_suffix(".amsg")

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
            # before the handoff. Two recipients may declare different keys for
            # the same sender, so the answer is per mailbox, not per message.
            trust = self.classify_inbound(message, agent).value
            message.trust = trust
            self.hand_off(agent, message, trust)
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
            # A DENY IS TERMINAL AND IS COUNTED — spec O5d.7
            # "terminal-dispositions-are-enumerated-and-closed". Recorded against
            # EVERY named recipient, because the refusal is a decision about the
            # submission as a unit and a permitted recipient left with no record
            # would leave the derived view with nothing to read.
            self._record_fate(sender, message, "denied", "; ".join(refusals))
            # Partially-permitted is refused outright rather than partially sent:
            # a caller told "delivered" about some recipients and not others has
            # to reconcile that, and will get it wrong.
            return {"ok": False, "refused": refusals, "message_id": message.message_id}

        # THE PRE-SEND GATE, at the last point before anything is delivered
        # (spec O5e.1). Placed AFTER authorization so a refused destination
        # never reaches it, and BEFORE transport so nothing leaves unscanned.
        gate = self._scrub(message)
        if gate is not None:
            if self.audit:
                self.audit.refused(sender=sender, recipients=message.to,
                                   reason=f"pre-send gate: {gate}",
                                   message_id=message.message_id)
            self._record_fate(sender, message, "gate-refused", gate)
            return {"ok": False, "refused": [f"pre-send gate: {gate}"],
                    "message_id": message.message_id}

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

        # THE FATE, RECORDED PER RECIPIENT, on the live path rather than in a
        # helper nothing calls. Delivered and failed recipients are recorded
        # separately because that difference is the entire reason the store is
        # per-recipient — spec O5d.8 "disposition-is-per-recipient".
        if delivered:
            self._record_fate(sender, message, "delivered",
                              recipients=[d["recipient"] for d in delivered])
        for f in failures:
            self._record_fate(sender, message, "bounced", f["error"],
                              recipients=[f["recipient"]])

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

        NOT YET INTEGRATED -- READ THIS BEFORE TRUSTING ITS TEST COVERAGE.
        Nothing in production calls this. There is no inbound path yet: that is
        the transport decision and the round trip, neither of which has run. Its
        several dozen passing tests therefore establish that the classification
        LOGIC behaves, and establish nothing whatever about it being reached,
        ordered correctly against delivery, or fed real messages.

        The hazard is the impression, not the code: a well-tested control reads
        as a live one. Whoever builds the inbound receiver is the first person
        who can make this true, and should treat the coverage as a starting
        point rather than a warrant. The guard sweep in the test suite carries a
        matching exemption that must be deleted at that moment.
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
            # BROKER-OWNED quarantine, not the agent's. Refused evidence must
            # live where the refused party cannot edit it, and the agent owns
            # its home — the same reason the internet path quarantines
            # broker-side. This also removes the last cross-uid write.
            self.quarantine_refused(agent, message, reason)
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

        # Same unified path: inbound peer mail is handed off, not written
        # across the boundary. `home` is retained above only to read the
        # recipient's existing threads for the parent/thread checks.
        self.hand_off(agent, message, message.trust or "")
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

    def status_counts(self, agent: str) -> Dict[str, Any]:
        """Counts of the BROKER's stores scoped to this agent — nothing else.

        Quarantined mail is broker-owned (spool-not-store's cousin: refused
        evidence lives where the refused party cannot edit it), so its count
        must come through the socket or the agent cannot distinguish an
        empty inbox from an inbox with three refusals — the exact ambiguity
        the specification forbids building. The pickup-box count is the same
        story one step earlier: accepted mail awaiting the custody transfer.

        What is deliberately NOT here: counts of the agent's own store
        (delivered bundles, delivered internet mail). Access follows custody
        — the filesystem is the access path to the agent's store, and the
        agent counts its own record itself. The unprivileged deployment
        enforces this physically: the broker's uid cannot read agent homes,
        which is how the old messages/internet counts here died — as an
        EACCES, not a design essay.
        """
        if agent not in self.config.agent_homes:
            # Fails closed on an unmapped agent, matching `identify`. The
            # refusal is audited by the request handler, which records it with
            # the kernel-established identity attached.
            raise PermissionError(
                f"'{agent}' has no provisioned mailbox; refusing the read. "
                "Reaching the socket is not authorization."
            )
        quarantined = 0
        qdir = self.config.inbound_quarantine
        if qdir is not None and qdir.is_dir():
            own_addr = self.config.address_for(agent).lower()
            for sc in qdir.glob("*.json"):
                try:
                    meta = json.loads(sc.read_text())
                except (OSError, ValueError):
                    # Damaged quarantine metadata still counts: it is a
                    # refusal artifact, and dropping it from the count
                    # rebuilds the silent-drop ambiguity one layer up.
                    quarantined += 1
                    continue
                to = str(meta.get("observed", {}).get("envelope_to", "")).lower()
                if to == own_addr:
                    quarantined += 1
        pending_pickup = 0
        hdir = self.config.inbound_handoff
        if hdir is not None and (hdir / agent).is_dir():
            pending_pickup = len(list((hdir / agent).glob("*.eml")))
        counts = {
            "quarantined": quarantined,
            "pending_pickup": pending_pickup,
        }
        if self.audit:
            # audit.read's schema is deliberately fixed; the total is the
            # auditable fact, the breakdown is in the response.
            self.audit.read(agent=agent, operation="status",
                            count=sum(counts.values()))
        return {"ok": True, **counts}

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
            # other operations existed, and absent means "submit" — so the wire
            # stays compatible with a client that only ever learned to send, and
            # the submission path is unchanged for it.
            #
            # Note what `status` does NOT take: a home, a path, or an agent
            # name. `sender` here is the kernel-established identity, and it is
            # the only thing that selects whose broker-store counts come back.
            #
            # There are deliberately no bundle list/read operations. Access
            # follows custody: delivered mail is the agent's own permanent
            # record, read directly from its store — the socket reaches only
            # the broker's stores. The old ops served delivered mail across
            # that boundary, and the unprivileged deployment could not execute
            # them anyway (the broker's uid cannot read agent homes).
            op = req.get("op", "submit")
            if op == "submit":
                msg = Message.from_dict(req["message"])
                resp = broker.submit(sender, msg)
            elif op == "status":
                resp = broker.status_counts(sender)
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
