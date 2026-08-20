"""Agent-side submission client.

Deliberately thin, and deliberately powerless. It speaks to the broker's local
socket and does NOT check the contact list itself — not because checking would be
harmful, but because a check here would be theatre. The agent controls this code;
anything it enforces, the agent can remove. The real check happens on the far side
of the socket, in a process the agent cannot edit.

That asymmetry is the point of the whole design, so this module stays honest about
having no authority.
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .models import Message, _now_iso


class BrokerUnavailable(RuntimeError):
    """The broker could not be reached. Never degrade to sending directly."""


def _roundtrip(req: Dict[str, Any], socket_path: Path, timeout: float,
               closed_hint: str) -> Dict[str, Any]:
    """One request, one response, no fallback — shared by every operation.

    Every call the client can make goes through this function, so the
    no-fallback rule is stated once and cannot be forgotten by whichever
    operation is added next. `closed_hint` names the likeliest cause when the
    broker hangs up mid-write, which differs by operation.
    """
    path = str(socket_path)
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(path)
    except OSError as e:
        raise BrokerUnavailable(
            f"cannot reach the amail broker at {path}: {e}. "
            "Mail is not sent. There is no fallback transport by design."
        ) from e
    try:
        payload = json.dumps(req) + "\n"
        try:
            s.sendall(payload.encode("utf-8"))
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
        except OSError as e:
            # The broker closing the connection mid-write is a REFUSAL — an
            # oversize submission is the ordinary cause. Letting BrokenPipeError
            # escape reported a transport crash for what was the size guard
            # working correctly, and the two need to be told apart.
            raise BrokerUnavailable(
                f"the broker closed the connection while the request was being "
                f"sent ({e}). {closed_hint}"
            ) from e
    finally:
        s.close()
    if not buf.strip():
        raise BrokerUnavailable("broker closed the connection without answering")
    return json.loads(buf.decode("utf-8"))


def submit(sender: str, message: Message, socket_path: Path,
           timeout: float = 10.0) -> Dict[str, Any]:
    """Hand a message to the broker and return its verdict.

    On failure this raises rather than falling back to any other transport. A
    client that "helpfully" delivers by another route when the broker is down
    would route around the only thing enforcing the contact list.
    """
    return _roundtrip(
        {"sender": sender, "message": message.to_dict()},
        socket_path, timeout,
        "The message was NOT sent. A submission over the broker's size limit "
        "is the usual cause.",
    )


#: The submission states a sent copy's annotation can carry. Deliberately NOT
#: the disposition vocabulary: these are what the AGENT observed of its own
#: attempt, and the broker's `submitted`/`delivered`/`bounced` are what the
#: BROKER observed of the message's fate. Two observers, two vocabularies —
#: collapsing them would let one side's silence read as the other's verdict.
COMPOSED = "composed"        # written, never yet handed to the broker
ATTEMPTED = "attempted"      # handed over; no answer received (crash, outage)
SUBMITTED = "submitted"      # the broker answered and accepted it
REFUSED = "refused"          # the broker answered and refused it


def send_with_custody(home: Path, sender: str, message: Message,
                      socket_path: Path, timeout: float = 10.0) -> Dict[str, Any]:
    """Compose, KEEP A COPY, then submit — in that order, and the order is the point.

    Spec O5c.6 "the-sent-copy-is-written-before-submission". Writing after the
    broker answers loses the record of anything that died mid-flight, which is
    precisely the case a sender most needs evidence of. So the copy exists
    before the attempt, and the annotation records how far the attempt got.

    The three writes are not ceremony. Each one is the state a crash at that
    instant would leave behind:

        composed   -> the process died before it ever reached the socket
        attempted  -> it died with the request in flight; the broker may or may
                      not have acted, and NOTHING here may claim to know which
        submitted  -> the broker answered

    `attempted` is written BEFORE the call rather than after it, because a state
    written after the call cannot describe a failure of the call.

    The content hash covers `signing_payload()` — the same bytes a signature
    covers — rather than the serialized message. Spec O5c.7 asks for the exact
    submitted bytes OR a NAMED CANONICAL SUBSET, and the subset is required
    here: the broker RE-MINTS message_id and date (a submitter-chosen id shadows
    a real message and a submitter-chosen date controls the reader's ordering),
    so stored bytes and submitted bytes can never be equal and a raw comparison
    would report mismatch on every message ever sent. `signing_payload` already
    excludes exactly those two fields, for exactly this reason, and already has
    a round-trip property test — so this reuses the codebase's one definition of
    "what the message IS" instead of coining a second one that could drift.
    """
    import hashlib
    from . import store
    from .crypto import signing_payload

    content_sha256 = hashlib.sha256(signing_payload(message)).hexdigest()

    sent_path = store.deliver_sent(home, message)
    name = sent_path.name
    meta = {
        "state": COMPOSED,
        "composed_at": _now_iso(),
        "content_sha256": content_sha256,
        # The id the AGENT minted. The broker will mint its own, and recording
        # both is what lets the two records be joined afterwards.
        "local_message_id": message.message_id,
        "broker_message_id": None,
        "to": list(message.to),
    }
    store.write_sent_sidecar(home, name, meta)

    meta["state"] = ATTEMPTED
    meta["attempted_at"] = _now_iso()
    store.write_sent_sidecar(home, name, meta)

    try:
        result = submit(sender, message, socket_path, timeout)
    except BrokerUnavailable:
        # The annotation stays at `attempted` on purpose. We do not know whether
        # the broker acted, and writing `refused` here would be the client
        # asserting a broker decision it never heard — the same invention the
        # disposition store exists to prevent, committed on the other side.
        raise

    meta["state"] = SUBMITTED if result.get("ok") else REFUSED
    meta["answered_at"] = _now_iso()
    meta["broker_message_id"] = result.get("message_id")
    if not result.get("ok"):
        meta["refused"] = result.get("refused") or []
    store.write_sent_sidecar(home, name, meta)

    result["sent_copy"] = str(sent_path)
    result["content_sha256"] = content_sha256
    return result


def reconcile_sent(home: Path, dispositions_dir: Optional[Path]) -> Dict[str, Any]:
    """The AGENT-SIDE half of conservation, over the copies the agent owns.

    Spec O5d.6a "composed-never-submitted-is-reconciled-agent-side". The broker's
    ledger starts at submission and structurally cannot see a message composed
    and never submitted — O5c.6 blesses that class as correct and expected — so
    counting it there would report a shortfall for correct behaviour, and
    counting it nowhere loses it. It is counted here, where it is visible.

    The rule, and it is the whole check:

        state `composed`  -> a disposition record MUST NOT exist. Expected,
                             never a shortfall.
        state `submitted` -> a disposition record MUST exist.
        state `attempted` -> UNRESOLVED, and named as such rather than sorted
                             into either bucket. This is the residual edge of
                             spec O13.10 "the-outbound-ledger's-left-edge": the
                             submission may have died before the broker's first
                             look, or after it, and neither side can tell.

    `unresolved` is reported separately BECAUSE it is the honest answer. Folding
    it into either column would make the ledger balance by deciding a question
    the system cannot answer, which is worse than an imbalance — an imbalance
    prompts a look, and a false balance prevents one.
    """
    from . import store

    out: Dict[str, Any] = {"ok": True, "composed": 0, "submitted": 0,
                           "unresolved": [], "missing_disposition": [],
                           "unexpected_disposition": [], "unannotated": []}
    for entry in store.read_sent_with_state(home):
        side = entry.get("sidecar")
        if side is None:
            # No annotation at all. Distinct from `composed`, and it means this
            # copy predates the annotation or its sidecar was lost — either way
            # it cannot be reconciled, and saying so beats guessing.
            out["unannotated"].append(entry["name"])
            continue
        state = side.get("state")
        mid = side.get("broker_message_id") or side.get("local_message_id")
        record = sent_disposition(dispositions_dir, mid) if dispositions_dir else None

        if state == COMPOSED:
            out["composed"] += 1
            if record is not None:
                out["unexpected_disposition"].append(mid)
        elif state in (SUBMITTED, REFUSED):
            out["submitted"] += 1
            if record is None:
                out["missing_disposition"].append(mid)
        elif state == ATTEMPTED:
            out["unresolved"].append(mid)

    out["ok"] = not (out["missing_disposition"] or out["unexpected_disposition"])
    return out


# There are deliberately no list/read wrappers here. Access follows custody:
# delivered mail — bundles and internet alike — is the agent's own permanent
# record, read directly from its store (`macf.amail.store`). The socket reaches
# only the broker's stores; the wrappers that once served delivered mail across
# that boundary were the KNOWN-DEVIATION the spec's conformance table carried,
# realigned when the unprivileged broker made them impossible to execute.


def ingest(home: Path, pickup_box: Path, contacts_path: Optional[Path] = None,
           agent: str = "") -> list:
    """Execute the custody transfer: move handed-off mail from the broker's
    pickup box into the caller's OWN store, as the caller.

    This is the step that makes the pickup-box model work without any
    privileged component: the broker (unprivileged) hands off into a box
    only this agent's group can read; the agent ingests as itself, so
    ownership of the permanent record is correct by construction. The
    content hash is re-verified against the sidecar before the box entry is
    removed — removal only after the ingested copy exists (the same
    completion-before-deletion rule the broker applies at the spool).

    Returns one result dict per pickup entry, including failures — an entry
    that cannot be ingested stays in the box, visibly, with its reason.
    """
    import hashlib
    from . import store

    results = []
    if not pickup_box.is_dir():
        return results
    for amsg in sorted(pickup_box.glob("*.amsg")):
        results.append(_ingest_bundle(home, amsg, contacts_path, agent))
    for eml in sorted(pickup_box.glob("*.eml")):
        sidecar = eml.with_suffix(".json")
        entry = {"name": eml.name}
        try:
            raw = eml.read_bytes()
            meta = json.loads(sidecar.read_text())
        except (OSError, json.JSONDecodeError) as e:
            entry.update(ingested=False, reason=f"unreadable pair: {e}")
            results.append(entry)
            continue
        actual = hashlib.sha256(raw).hexdigest()
        if meta.get("raw_sha256") != actual:
            entry.update(ingested=False,
                         reason=f"hash mismatch (sidecar {str(meta.get('raw_sha256'))[:12]}, "
                                f"bytes {actual[:12]}); left in box")
            results.append(entry)
            continue
        delivered = store.deliver_raw(home, raw, json.dumps(meta, indent=1))
        try:
            eml.unlink()
            sidecar.unlink()
        except OSError as e:
            # Ingested but not removed: the copy exists and a duplicate
            # ingest is prevented next round by... nothing yet — so say it
            # loudly instead of pretending.
            print(f"⚠️ MACF: pickup entry {eml.name} ingested but not "
                  f"removable ({e}); it will re-ingest as a duplicate next "
                  f"round unless removed", file=sys.stderr)
        entry.update(ingested=True, path=str(delivered), sha256=actual)
        results.append(entry)
    return results



def _ingest_bundle(home: Path, amsg: Path, contacts_path, agent: str) -> dict:
    """Custody transfer for an agent message, including the signature verdict.

    VERIFICATION HAPPENS HERE, not at read time, for three reasons the battery
    made concrete. Read-time verification lives on the path the suite never
    exercises — the same path that hid a phantom listing and a thread id minted
    from the clock. Ingest is exercised. Second, it must keep working with the
    broker stopped, so the keys come from the contacts file on disk, read
    directly, never a broker round-trip: the file is broker-OWNED and
    agent-readable, so an agent can read the keys it has been given and cannot
    rewrite them. Third, custody transfers once, so the trust fact is
    established at the boundary and recorded, rather than recomputed on every
    glance.

    The verdict never collapses to a boolean. A declared key can change, so the
    raw message and its signature are preserved and re-verification stays
    possible; and keys_for()'s three states stay distinct, because "no key
    declared" is not "declared and failed" is not "verified".
    """
    import hashlib
    from . import store
    from .models import Message
    from .trust import TrustClass

    sidecar = amsg.with_suffix(".json")
    entry = {"name": amsg.name, "kind": "bundle"}
    try:
        payload = amsg.read_bytes()
        meta = json.loads(sidecar.read_text())
    except (OSError, json.JSONDecodeError) as e:
        entry.update(ingested=False, reason=f"unreadable pair: {e}")
        return entry
    actual = hashlib.sha256(payload).hexdigest()
    if meta.get("raw_sha256") != actual:
        entry.update(ingested=False,
                     reason=f"hash mismatch (sidecar {str(meta.get('raw_sha256'))[:12]}, "
                            f"bytes {actual[:12]}); left in box")
        return entry
    try:
        message = Message.deserialize(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        entry.update(ingested=False, reason=f"undeserializable message: {e}")
        return entry

    verdict = _verify_at_ingest(message, contacts_path, agent)
    message.trust = verdict["trust"]
    meta["ingest_verification"] = verdict
    # Disagreement with the broker's own read is information, not noise: it is
    # what a stale or compromised broker looks like from the recipient's side.
    broker_trust = meta.get("broker_trust")
    if broker_trust and broker_trust != verdict["trust"]:
        print(f"⚠️ MACF: trust disagreement on {message.message_id}: broker said "
              f"{broker_trust!r}, own keys say {verdict['trust']!r} "
              f"({verdict['reason']})", file=sys.stderr)
        meta["ingest_verification"]["disagrees_with_broker"] = broker_trust

    delivered = store.deliver(home, message)
    store.write_bundle_sidecar(home, delivered.name, json.dumps(meta, indent=1))
    try:
        amsg.unlink()
        sidecar.unlink()
    except OSError as e:
        print(f"⚠️ MACF: pickup entry {amsg.name} ingested but not removable "
              f"({e}); it will re-ingest as a duplicate next round unless "
              f"removed", file=sys.stderr)
    entry.update(ingested=True, path=str(delivered), sha256=actual,
                 trust=verdict["trust"])
    return entry


def _verify_at_ingest(message, contacts_path, agent: str) -> dict:
    """The recipient's own signature verdict. Three states, never flattened."""
    from .trust import TrustClass
    from .crypto import verify

    if not contacts_path or not agent:
        return {"trust": TrustClass.UNVERIFIED.value, "keys_declared": None,
                "reason": "no local contact book available to this recipient; "
                          "no verification attempted"}
    try:
        from .contacts import ContactBook
        keys = ContactBook(Path(contacts_path)).keys_for(agent, message.sender)
    except (OSError, ValueError) as e:
        return {"trust": TrustClass.UNVERIFIED.value, "keys_declared": None,
                "reason": f"contact book unreadable ({e}); no verification attempted"}

    if message.signature and keys:
        if verify(message, message.signature, keys):
            return {"trust": TrustClass.ATTESTED.value, "keys_declared": len(keys),
                    "reason": "signature verified against a declared key"}
        return {"trust": TrustClass.SUSPECT.value, "keys_declared": len(keys),
                "reason": "signature present and did NOT verify against any "
                          "declared key"}
    if message.signature and not keys:
        return {"trust": TrustClass.UNVERIFIED.value, "keys_declared": 0,
                "reason": "signed, but this recipient declares no key for the "
                          "sender; nothing can be concluded"}
    if keys and not message.signature:
        return {"trust": TrustClass.SUSPECT.value, "keys_declared": len(keys),
                "reason": "sender declares a key and sent no signature; "
                          "breaking that commitment is the shape of impersonation"}
    return {"trust": TrustClass.UNVERIFIED.value, "keys_declared": 0,
            "reason": "unsigned, and no key declared for the sender"}



def read_sent(home: Path) -> list:
    """This agent's own copies of what it sent. Filesystem, no broker."""
    from . import store
    return store.read_sent(home)


#: Outcomes ranked LEAST-SUCCESSFUL FIRST. The order is the whole content of
#: spec O5d.8b "message-level-view-is-the-least-successful-outcome": the derived
#: view is the minimum over the per-recipient outcomes, so any recipient bounced
#: makes the message bounced, and `delivered` requires that every recipient
#: reached it.
#:
#: Least-successful rather than most-successful because a sender needs to know
#: that SOMETHING failed. A summary reporting success while a recipient bounced
#: is the silent-delivery failure the disposition store exists to prevent, one
#: level up.
#:
#: The refusals sort below the transport outcomes because they mean nothing was
#: attempted at all. `abandoned` (in flight past its age bound) sorts above
#: `bounced` because a bounce is a definite negative and an abandonment is an
#: unknown — and the unknown must not masquerade as the definite fact.
_OUTCOME_RANK = {
    "denied": 0,
    "gate-refused": 1,
    "rate-refused": 2,
    "bounced": 3,
    "abandoned": 4,
    "submitted": 5,
    "deferred": 6,
    "delivered": 7,
}


def derive_message_state(record: Dict[str, Any]) -> Optional[str]:
    """The message-level view, DERIVED from the per-recipient records.

    Spec O5d.8 "message-level-view-is-derived-never-stored": it is computed on
    every read and never written down, because a stored copy can drift from the
    records it summarises. Spec O5d.8b
    "message-level-view-is-the-least-successful-outcome" fixes HOW, so that two
    implementations
    cannot compute different balances from identical traffic.

    Returns None when there is nothing to derive from — which is distinct from
    every state in the vocabulary and MUST NOT be read as `delivered`.

    An UNKNOWN state in the record makes the whole derivation UNKNOWN rather
    than being skipped. Skipping it would let a state this version does not
    recognise silently improve the summary: a future `quarantined` would be
    dropped, and a message with one bounce and one unrecognised outcome would
    derive `bounced` while the truth was worse. Refusing to derive is the
    honest answer to "I do not know what one of these means".
    """
    per = (record or {}).get("recipients") or {}
    worst: Optional[str] = None
    for _addr, entry in per.items():
        history = entry.get("history") or []
        if not history:
            continue
        state = history[-1].get("state")
        if state not in _OUTCOME_RANK:
            print(f"⚠️ MACF: disposition carries unrecognised state {state!r}; "
                  "the message-level view is UNKNOWN rather than derived from "
                  "the states this version happens to know", file=sys.stderr)
            return None
        if worst is None or _OUTCOME_RANK[state] < _OUTCOME_RANK[worst]:
            worst = state
    return worst


def sent_disposition(dispositions_dir: Path, message_id: str) -> Optional[Dict[str, Any]]:
    """What became of a message this agent sent, or None if nothing recorded.

    Read from the BROKER's store by filesystem, deliberately -- not over the
    socket. The fate of a message must remain knowable when the broker is not
    running, for the same reason the sent copy itself must: a record that needs
    a service to be read is not a record. The broker owns the file so the agent
    cannot forge its own delivery confirmations; the agent reads it so it can
    always answer "did that leave?".

    None is a REAL answer and distinct from a bad one: it means nothing has been
    recorded for this id yet. A caller that treats it as "delivered" has invented
    the silent success this whole store exists to prevent.
    """
    f = Path(dispositions_dir) / f"{message_id}.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: disposition record for {message_id} is unreadable "
              f"({e}); treating as UNKNOWN, not as delivered", file=sys.stderr)
        return None


def list_delivered_internet(home: Path) -> list:
    """Internet deliveries in the caller's OWN mailbox, read directly.

    Direct by design, not by convenience: delivered mail is the agent's
    permanent record — custody transferred at delivery, authorization
    already decided and recorded by the broker — so its access path is the
    filesystem, like every other artifact the agent owns. The socket is the
    access path to the BROKER's stores (spool, quarantine, counts), where
    content has not yet been authorized for this agent.
    """
    from . import store
    return store.read_internet(home)


def read_delivered_internet(home: Path, ref: str):
    """(raw bytes, sidecar) for one delivered internet message in the
    caller's own mailbox, by delivery name or content-sha prefix; None when
    absent. Same custody reasoning as list_delivered_internet."""
    from . import store
    return store.find_internet(home, ref)


def status(socket_path: Path, timeout: float = 10.0) -> Dict[str, Any]:
    """The caller's mailbox counts, including the one it cannot compute
    itself: quarantined mail lives where the refused party cannot edit it,
    so its count only exists on the far side of the socket."""
    return _roundtrip({"op": "status"}, socket_path, timeout,
                      "No status was returned.")
