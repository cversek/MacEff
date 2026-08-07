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


def submit(sender: str, message: Message, socket_path: Path,
           timeout: float = 10.0) -> Dict[str, Any]:
    """Hand a message to the broker and return its verdict.

    On failure this raises rather than falling back to any other transport. A
    client that "helpfully" delivers by another route when the broker is down
    would route around the only thing enforcing the contact list.
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
        payload = json.dumps({"sender": sender, "message": message.to_dict()}) + "\n"
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
                f"the broker closed the connection while the message was being "
                f"sent ({e}). The message was NOT sent. A submission over the "
                f"broker's size limit is the usual cause."
            ) from e
    finally:
        s.close()
    if not buf.strip():
        raise BrokerUnavailable("broker closed the connection without answering")
    return json.loads(buf.decode("utf-8"))
