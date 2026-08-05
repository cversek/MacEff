"""Maildir delivery — the authoritative local store.

A standard Maildir in the agent's home, deliberately NOT under the framework's
artifact tree: an account may be provisioned without that tree entirely, and mail
inside it would make correspondence a framework-only capability.

Delivery uses the Maildir tmp/->new/ rename, which is the whole reason Maildir
exists: a reader scanning new/ never observes a half-written file, because rename
within a filesystem is atomic. Writing straight into new/ would race every reader.
"""
from __future__ import annotations

import itertools
import os
import socket
import threading
import time
from pathlib import Path
from typing import List, Optional

from .models import Message

SUBDIRS = ("tmp", "new", "cur")


def maildir_for(home: Path) -> Path:
    return Path(home) / "Maildir"


def ensure_maildir(home: Path) -> Path:
    d = maildir_for(home)
    for sub in SUBDIRS:
        (d / sub).mkdir(mode=0o700, parents=True, exist_ok=True)
    d.chmod(0o700)
    return d


_counter = itertools.count()
_counter_lock = threading.Lock()


def _unique_name() -> str:
    """Maildir's uniqueness convention: time.pid_counter.host.

    The counter is NOT decorative. Maildir names are second-granular, so without
    it two deliveries inside the same second collide — and because delivery ends
    in a rename, the second silently OVERWRITES the first. Mail disappears with no
    error anywhere. A broker delivering a thread writes several messages in well
    under a second, so this is the common case rather than a rare race.

    Locked because the broker serves agents on threads; two threads reading the
    same counter value would reintroduce exactly the collision.
    """
    with _counter_lock:
        seq = next(_counter)
    return f"{int(time.time())}.{os.getpid()}_{seq}.{socket.gethostname()}"


def deliver(home: Path, message: Message) -> Path:
    """Write a message into the recipient's Maildir. Returns the final path.

    Called by the BROKER, never by a peer agent — which is why no agent needs
    read or write access to another agent's mailbox. That access requirement was
    the actual blocker the previous convention hit, and widening permissions to
    solve it would have been the wrong direction.
    """
    d = ensure_maildir(home)
    name = _unique_name()
    tmp = d / "tmp" / name
    tmp.write_text(message.serialize())
    tmp.chmod(0o600)
    final = d / "new" / name
    os.rename(tmp, final)  # atomic within the filesystem; readers see all or nothing
    return final


def read_all(home: Path, include_seen: bool = True) -> List[Message]:
    """Every message in the mailbox, ordered per the policy's sort key.

    Order comes from (date, message_id) — not from filenames, not from a counter,
    and not from directory listing order, which is unspecified.
    """
    d = maildir_for(home)
    if not d.exists():
        return []
    boxes = ["new"] + (["cur"] if include_seen else [])
    out: List[Message] = []
    for box in boxes:
        p = d / box
        if not p.is_dir():
            continue
        for f in p.iterdir():
            if not f.is_file():
                continue
            try:
                out.append(Message.deserialize(f.read_text()))
            except (OSError, ValueError):
                # A malformed file is skipped rather than fatal: one bad message
                # must not make the whole mailbox unreadable.
                continue
    return sorted(out, key=lambda m: m.sort_key())


def thread(home: Path, thread_id: str) -> List[Message]:
    return [m for m in read_all(home) if m.thread_id == thread_id]


def find(home: Path, message_id: str) -> Optional[Message]:
    for m in read_all(home):
        if m.message_id == message_id:
            return m
    return None


def quarantine(home: Path, message: Message, reason: str) -> Path:
    """Retain mail from an unlisted sender without delivering it to the inbox.

    Retained rather than rejected: rejecting at the transport boundary reveals
    which addresses exist, and legitimately forwarded mail can arrive from an
    unexpected envelope sender. Quarantine keeps the evidence and keeps the
    decision reversible.
    """
    q = maildir_for(home) / "quarantine"
    q.mkdir(mode=0o700, parents=True, exist_ok=True)
    p = q / _unique_name()
    p.write_text(f"X-Amail-Quarantine-Reason: {reason}\n" + message.serialize())
    p.chmod(0o600)
    return p
