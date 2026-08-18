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
from pathlib import Path
from typing import Any, Dict, Optional

from .models import Message


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
            import sys
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
        import sys as _sys
        print(f"⚠️ MACF: trust disagreement on {message.message_id}: broker said "
              f"{broker_trust!r}, own keys say {verdict['trust']!r} "
              f"({verdict['reason']})", file=_sys.stderr)
        meta["ingest_verification"]["disagrees_with_broker"] = broker_trust

    delivered = store.deliver(home, message)
    store.write_bundle_sidecar(home, delivered.name, json.dumps(meta, indent=1))
    try:
        amsg.unlink()
        sidecar.unlink()
    except OSError as e:
        import sys as _sys
        print(f"⚠️ MACF: pickup entry {amsg.name} ingested but not removable "
              f"({e}); it will re-ingest as a duplicate next round unless "
              f"removed", file=_sys.stderr)
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
