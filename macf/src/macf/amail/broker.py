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
from typing import Any, Dict, List, Optional

from .audit import AuditLog
from .contacts import ContactBook, ContactListError
from .models import Message, new_id, _now_iso
from .store import deliver, ensure_maildir

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

    def _deliver_one(self, recipient: str, message: Message) -> str:
        agent = self.config.agent_for(recipient)
        if agent:
            deliver(self.config.agent_homes[agent], message)
            return "local"
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
        reasons: List[str] = []

        # CHECKED
        expected = self.config.address_for(sender)
        if message.sender and message.sender.strip().lower() != expected.lower():
            reasons.append(f"message From '{message.sender}' does not match the "
                           f"authenticated sender '{expected}'")
        message.sender = expected

        # MINTED — a submitter-chosen message_id can shadow another message in
        # store.find(), splice threads, and collide audit records.
        message.message_id = new_id("msg")
        message.date = _now_iso()

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
                delivered.append({"recipient": r, "rung": self._deliver_one(r, message)})
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
                                   rung=",".join(sorted({d["rung"] for d in delivered})))
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

    def accept_inbound(self, message: Message, recipient: str) -> Dict[str, Any]:
        """Deliver inbound mail, or quarantine it when the sender is unlisted.

        An allowlisted sender is an AUTHORIZATION fact, not an authenticity or
        safety one. Nothing here establishes that a message is genuinely from
        whom it claims, and message bodies remain data rather than instructions.
        """
        from .store import quarantine
        agent = self.config.agent_for(recipient)
        if not agent:
            raise DeliveryError(f"'{recipient}' is not a local mailbox")
        home = self.config.agent_homes[agent]
        permitted = self.contacts.permits(agent, message.sender) if self.contacts else False
        if permitted:
            deliver(home, message)
            if self.audit:
                self.audit.inbound(sender=message.sender, recipient=recipient,
                                   message_id=message.message_id, decision="delivered")
            return {"ok": True, "decision": "delivered"}
        reason = f"sender '{message.sender}' is not in the contact list for '{agent}'"
        quarantine(home, message, reason)
        if self.audit:
            self.audit.inbound(sender=message.sender, recipient=recipient,
                               message_id=message.message_id,
                               decision="quarantined", reason=reason)
        return {"ok": True, "decision": "quarantined", "reason": reason}

    # -------------------------------------------------------------- credentials

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
            raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                  struct.calcsize("3I"))
            # ucred fields are unsigned; reading them signed turns a high uid
            # negative. It failed closed, but a lookup should not depend on that.
            _pid, uid, _gid = struct.unpack("3I", raw)
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

            msg = Message.from_dict(req["message"])
            resp = broker.submit(sender, msg)
        except Exception as e:  # noqa: BLE001 - a broker that dies on one bad
            # request stops serving every agent; answer with the error instead.
            resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            if broker.audit:
                broker.audit.error(context="request", detail=f"{type(e).__name__}: {e}")
        try:
            self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))
        except OSError as e:
            # The peer may have hung up. Log it rather than letting the write
            # throw out of handle() unrecorded — an outage with no trace is the
            # gap the audit log exists to close.
            if broker.audit:
                broker.audit.error(context="response", detail=str(e))


class _Server(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True
    daemon_threads = True


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
