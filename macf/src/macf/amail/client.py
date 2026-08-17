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


def list_messages(socket_path: Path, thread: Optional[str] = None,
                  timeout: float = 10.0) -> Dict[str, Any]:
    """The caller's own mailbox, as the broker sees it.

    Note the absent parameter: there is no way to ask for a mailbox. Which one
    is read follows from the kernel-supplied identity of this process, so this
    function cannot be pointed at a peer's mail even by a caller that wants to.
    """
    req: Dict[str, Any] = {"op": "list"}
    if thread:
        req["thread"] = thread
    return _roundtrip(req, socket_path, timeout,
                      "No messages were listed.")


def read_message(message_id: str, socket_path: Path,
                 timeout: float = 10.0) -> Dict[str, Any]:
    """One message from the caller's own mailbox, by id."""
    return _roundtrip({"op": "read", "message_id": message_id},
                      socket_path, timeout,
                      "The message was not read.")


def read_internet(ref: str, socket_path: Path,
                  timeout: float = 10.0) -> Dict[str, Any]:
    """One internet message (raw + provenance sidecar), by delivery name or
    content-sha prefix. Same absent parameter as every read: whose mailbox
    follows from kernel identity, not from anything this function accepts."""
    return _roundtrip({"op": "read_internet", "ref": ref},
                      socket_path, timeout,
                      "The message was not read.")


def status(socket_path: Path, timeout: float = 10.0) -> Dict[str, Any]:
    """The caller's mailbox counts, including the one it cannot compute
    itself: quarantined mail lives where the refused party cannot edit it,
    so its count only exists on the far side of the socket."""
    return _roundtrip({"op": "status"}, socket_path, timeout,
                      "No status was returned.")
