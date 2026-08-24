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
from . import liveness
from .notice import Notice
from .session import (
    find_credential_path,
    find_socket,
    read_credential,
    verify_incarnation,
)

DEDUP_NAME = "macf_notify_delivered.json"
DEDUP_RETAIN = 512
CONNECT_TIMEOUT_S = 3.0

DELIVERED = "delivered"
SUPPRESSED_DUPLICATE = "suppressed_duplicate"
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


def already_delivered(arrival_id: str) -> bool:
    return arrival_id in _load_seen()


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


def deliver(pid: int, notice: Notice, force: bool = False) -> DeliveryResult:
    """Wake one session with one notice. Idempotent on `notice.arrival_id`."""
    arrival_id = notice.arrival_id

    if not force and already_delivered(arrival_id):
        _emit("notify_suppressed", {"pid": pid, "arrival_id": arrival_id, "reason": "duplicate"})
        return DeliveryResult(SUPPRESSED_DUPLICATE, pid, arrival_id, "already delivered")

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

    _record_seen(arrival_id)
    _emit("notify_delivered", {
        "pid": pid,
        "arrival_id": arrival_id,
        "source": notice.source,
        # The rendered LENGTH, never the rendered text and never the credential.
        "bytes": len(text),
        "count_hint": notice.count,
    })
    return DeliveryResult(DELIVERED, pid, arrival_id, f"{len(text)} bytes")


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
