"""The delivery adapter: the agent becomes a third sink.

Detections already reach the event log and the operator. This adds the agent --
the party that could not otherwise have known, because the agent cannot ask about
what it does not know happened.

Edge-triggered on ARRIVAL, never level-triggered on STATE. A condition that is
true and remains true produces ONE notice, not one per interval. The level-
triggered form is not a lesser version of this; it converts a single fact into
unbounded noise and is indistinguishable, to its recipient, from a broken
notifier. This project has shipped that defect and been paged 36 times in nine
hours for it.

Nothing here sits in the synchronous path of an agent's work. The adapter is
ADVISORY and fails OPEN -- a notifier's death must never become the agent's
stall. Note the scope: the incarnation check inside `session.verify_incarnation`
is an AUTHORIZATION check and fails CLOSED. One component, two doctrines, kept
apart deliberately, because a component that is both cannot state a coherent one.
"""
import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..agent_events_log import append_event
from . import liveness, masking
from .notice import Notice
from .session import (
    find_credential_path,
    find_socket,
    read_credential,
    read_session_info,
    resolve_target,
    verify_incarnation,
)

DEDUP_NAME = "macf_notify_delivered.json"
DEDUP_RETAIN = 512
CONNECT_TIMEOUT_S = 3.0

DELIVERED = "delivered"
DEFERRED = "deferred"
SUPPRESSED_DUPLICATE = "suppressed_duplicate"
SUPPRESSED_MASKED = "suppressed_masked"
REFUSED_INCARNATION = "refused_incarnation"
REFUSED_NO_CREDENTIAL = "refused_no_credential"
REFUSED_NO_SOCKET = "refused_no_socket"
FAILED_TRANSPORT = "failed_transport"


@dataclass(frozen=True)
class DeliveryResult:
    outcome: str
    pid: int
    arrival_id: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome == DELIVERED


def dedup_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(runtime) / DEDUP_NAME


def _load_seen() -> list:
    path = dedup_path()
    if not path.exists():
        return []
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: dedup store unreadable (treating as empty, may redeliver): {e}", file=sys.stderr)
        return []
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"⚠️ MACF: dedup store malformed (treating as empty, may redeliver): {e}", file=sys.stderr)
        return []
    if not isinstance(data, list):
        print("⚠️ MACF: dedup store is not a list (treating as empty, may redeliver)", file=sys.stderr)
        return []
    return data


def _record_seen(arrival_id: str) -> None:
    seen = _load_seen()
    if arrival_id in seen:
        return
    seen.append(arrival_id)
    # Bounded: an unbounded dedup store is a slow leak whose failure arrives
    # months later as an unexplained disk problem.
    seen = seen[-DEDUP_RETAIN:]
    path = dedup_path()
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(seen, fh)
        os.replace(tmp, path)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"⚠️ MACF: dedup store write failed (a redelivery is now possible): {e}", file=sys.stderr)


def dedup_key(arrival_id: str, session_id: Optional[str]) -> str:
    """THE CONVERSATION IS THE AGENT, NOT THE PROCESS.

    Keying dedup on the arrival alone was wrong in a way that only appears when
    two processes serve one conversation: the first delivery would suppress the
    second, so the target was chosen by whichever pid the enumeration reached
    first -- an invisible choice, made by directory order.

    Keying it per-PID is wrong in the opposite direction: two processes sharing a
    conversation would each be told, and the agent would act twice on one arrival,
    which is precisely what idempotency exists to prevent.

    So the key is (arrival, conversation). A session id is required; without one
    the caller is addressing a process rather than an agent, and that is recorded
    in the key rather than papered over.

    KNOWN BOUND, and it is not fixable from here. The client MUTATES a session's
    conversation id in place when a session is resumed -- the id changes under a
    process that never restarted. So this key is stable for a conversation, not
    for a process lifetime, and a resume can make an already-delivered arrival
    look undelivered. The failure is a REDELIVERY, not a drop, which is the
    survivable direction: the notice licenses one store read, and a second read
    of an unchanged store yields "nothing happened".

    Documented rather than worked around, because every workaround available here
    would substitute an identity the client does not agree with -- and an identity
    only we believe in is worse than one that occasionally changes.
    """
    return f"{arrival_id}@{session_id or 'unknown-conversation'}"


def already_delivered(arrival_id: str, session_id: Optional[str] = None) -> bool:
    return dedup_key(arrival_id, session_id) in _load_seen()


def _emit(event: str, payload: dict) -> None:
    """Self-observability. Every delivery, suppression and failure.

    Scope of this virtue, stated because it does not survive a change of role:
    self-report is redundant instrumentation for a component that only NOTIFIES.
    It would be self-attestation for one that also edits what the agent receives.
    """
    try:
        append_event(event, payload)
    except (OSError, ValueError, TypeError) as e:
        print(f"⚠️ MACF: notify event logging failed: {e}", file=sys.stderr)


def _flush_deferred(pid: int, mask) -> list:
    """Deliver everything this conversation deferred, ONCE each.

    `force=True` on the way back in, because these notices already passed the
    mask once and were held rather than refused. Re-deciding them would let the
    section that held them hold them again, which is how "deferred" quietly
    becomes "never".
    """
    released = mask.release()
    if not released:
        return []
    results = []
    for held in released:
        results.append(deliver(pid, held, force=True))
    _emit("notify_released", {
        "pid": pid,
        "count": len(released),
        "delivered": sum(1 for r in results if r.ok),
    })
    return results


def release_deferred(pid: int, session_id: Optional[str] = None) -> list:
    """Flush a conversation's held notices without waiting for a new arrival.

    The opportunistic flush inside `deliver` only runs when something else
    arrives. If a critical section lapses and nothing arrives afterwards, the
    held notices would wait indefinitely -- delivered eventually is the promise,
    and "eventually" cannot mean "when unrelated traffic happens". A caller that
    polls (the daemon) uses this so the release depends on the EXPIRY rather
    than on luck.

    Honours the section: called while one is still active, it releases nothing.
    """
    if session_id is None:
        info = read_session_info(pid)
        session_id = info.session_id if info else None
    mask = masking.load(session_id)
    if mask.critical is not None and mask.critical.active():
        return []
    return _flush_deferred(pid, mask)


def deliver(pid: int, notice: Notice, force: bool = False) -> DeliveryResult:
    """Wake one session with one notice. Idempotent on `notice.arrival_id`."""
    arrival_id = notice.arrival_id
    info = read_session_info(pid)
    session_id = info.session_id if info else None

    if not force and already_delivered(arrival_id, session_id):
        _emit("notify_suppressed", {
            "pid": pid, "arrival_id": arrival_id,
            "session_id": session_id, "reason": "duplicate",
        })
        return DeliveryResult(SUPPRESSED_DUPLICATE, pid, arrival_id, "already delivered to this conversation")

    # THE MASK IS ENFORCED HERE, not merely computed somewhere the agent can
    # read. It is consulted BEFORE the credential is touched: an agent inside a
    # declared critical section should not have its credential read, its socket
    # opened, or anything sent -- and deferring needs none of those, so a notice
    # can be held for a session that is momentarily unreachable rather than lost
    # because it was.
    #
    # `force` bypasses this. That is the release path re-entering, and a held
    # notice must not be re-held by the same section that held it.
    mask = masking.load(session_id)
    if not force:
        decision = mask.decide(notice)
        if decision.defer:
            held = mask.defer(notice)
            _emit("notify_deferred", {
                "pid": pid, "arrival_id": arrival_id, "session_id": session_id,
                "source": notice.source, "reason": decision.reason,
                # Whether the HOLD itself succeeded. A deferral that failed to
                # persist is a DROP, and it must not be reported as a deferral.
                "held": held,
            })
            if not held:
                print(
                    f"⚠️ MACF: notice {arrival_id} could not be held and is now LOST "
                    f"(deferral is not a drop, but a failed write is)",
                    file=sys.stderr,
                )
            return DeliveryResult(DEFERRED, pid, arrival_id, decision.reason)
        if decision.suppress:
            _emit("notify_suppressed", {
                "pid": pid, "arrival_id": arrival_id,
                "session_id": session_id, "reason": decision.reason,
            })
            return DeliveryResult(SUPPRESSED_MASKED, pid, arrival_id, decision.reason)

        # Allowed, so no section is holding anything back: whatever this
        # conversation deferred earlier is owed to it NOW, before the notice
        # that happened to arrive next. `release` clears the queue before
        # returning, so the nested deliver() below finds nothing to flush and
        # this cannot recurse.
        _flush_deferred(pid, mask)

    cred_path = find_credential_path(pid)
    if cred_path is None:
        _emit("notify_refused", {"pid": pid, "arrival_id": arrival_id, "reason": "no_credential"})
        return DeliveryResult(REFUSED_NO_CREDENTIAL, pid, arrival_id, "no credential file for this pid")

    credential = read_credential(cred_path)
    if credential is None:
        _emit("notify_refused", {"pid": pid, "arrival_id": arrival_id, "reason": "credential_unusable"})
        return DeliveryResult(REFUSED_NO_CREDENTIAL, pid, arrival_id, "credential unreadable or malformed")

    # AUTHORIZATION check -- fails closed, before anything is sent.
    if not verify_incarnation(pid, credential.declared_start):
        _emit("notify_refused", {"pid": pid, "arrival_id": arrival_id, "reason": "incarnation_mismatch"})
        return DeliveryResult(REFUSED_INCARNATION, pid, arrival_id, "stale credential or recycled pid")

    sock_path = find_socket(pid)
    if sock_path is None:
        _emit("notify_refused", {"pid": pid, "arrival_id": arrival_id, "reason": "no_socket"})
        return DeliveryResult(REFUSED_NO_SOCKET, pid, arrival_id, "no session socket")

    text = notice.render()
    payload = "\n".join([
        json.dumps({"type": "auth", "token": credential.token}),
        json.dumps({"type": "user", "message": {"role": "user", "content": text}}),
    ]) + "\n"

    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.settimeout(CONNECT_TIMEOUT_S)
        conn.connect(str(sock_path))
        conn.sendall(payload.encode("utf-8"))
    except (socket.timeout, socket.error, ConnectionError, OSError) as e:
        # ADVISORY path: fail open. The agent keeps working; it just was not told.
        print(f"⚠️ MACF: wake delivery failed for pid {pid} (agent not notified): {e}", file=sys.stderr)
        _emit("notify_failed", {"pid": pid, "arrival_id": arrival_id, "error": str(e), "error_type": type(e).__name__})
        return DeliveryResult(FAILED_TRANSPORT, pid, arrival_id, str(e))
    finally:
        try:
            conn.close()
        except OSError as e:
            print(f"⚠️ MACF: socket close failed after delivery: {e}", file=sys.stderr)

    _record_seen(dedup_key(arrival_id, session_id))
    _emit("notify_delivered", {
        "session_id": session_id,
        "pid": pid,
        "arrival_id": arrival_id,
        "source": notice.source,
        # The rendered LENGTH, never the rendered text and never the credential.
        "bytes": len(text),
        "count_hint": notice.count,
    })
    return DeliveryResult(DELIVERED, pid, arrival_id, f"{len(text)} bytes")


def deliver_to_conversation(session_id: str, notice: Notice) -> DeliveryResult:
    """Address an AGENT rather than a process, resolving the target and surfacing
    any ambiguity instead of silently picking.

    A conversation served by two live processes is a runtime fault, not a routing
    preference. This does not hide it: the ambiguity is emitted as its own event
    and recorded in the liveness record the agent can read, because an agent may
    not decline to be told about itself.
    """
    chosen, candidates = resolve_target(session_id)
    if chosen is None:
        _emit("notify_refused", {
            "session_id": session_id, "arrival_id": notice.arrival_id,
            "reason": "no_live_process_for_conversation",
        })
        return DeliveryResult(REFUSED_NO_SOCKET, -1, notice.arrival_id, "no live process serves this conversation")

    if len(candidates) > 1:
        _emit("notify_target_ambiguous", {
            "session_id": session_id,
            "candidate_pids": [c.pid for c in candidates],
            "chosen_pid": chosen.pid,
            "rule": "newest-proc-start (HEURISTIC, unmeasured)",
        })

    return deliver(chosen.pid, notice)


def deliver_and_publish(pid: int, notice: Notice, cadence_s: float = liveness.DEFAULT_CADENCE_S) -> DeliveryResult:
    """Deliver, then refresh liveness in the SAME change that grants the capability.

    Publishing afterwards, as a follow-up, is how a component ends up able to
    speak to an agent while unable to say whether it is there.
    """
    result = deliver(pid, notice)
    current = liveness.read()
    liveness.publish(
        cadence_s=cadence_s,
        last_delivery_at=time.time() if result.ok else current.last_delivery_at,
        deliveries=current.deliveries + (1 if result.ok else 0),
        suppressions=current.suppressions + (1 if result.outcome == SUPPRESSED_DUPLICATE else 0),
        failures=current.failures + (1 if result.outcome in (FAILED_TRANSPORT,) else 0),
    )
    return result
