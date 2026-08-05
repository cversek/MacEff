"""amail message model.

Implements the message format the amail policy specifies. Read that policy
before changing anything here — several choices below look arbitrary and are not.

The one worth restating: there are NO SEQUENCE NUMBERS. Ordering a thread by a
counter requires every sender to know the current maximum, which requires seeing
every participant's messages at send time. The delivery model cannot supply that,
and the previous convention's two participants diverged on it inside a
four-message exchange. Identity is locally generated; order is derived.
"""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Longest a single header value may be. Not a correctness limit — a blast
#: radius one. An unbounded subject becomes an unbounded line in every reader.
_MAX_HEADER = 998  # RFC 5322 line-length ceiling


def _hdr(value: Any) -> str:
    """Make a value safe to interpolate into a header line.

    Strips CR and LF, which are the header/body delimiters — a value containing
    either can forge headers and terminate the header block early. Tabs and other
    control characters are folded to spaces so a value cannot smuggle structure
    past a naive parser. Truncated to the RFC line ceiling.

    Applied at SERIALIZATION rather than on assignment, deliberately: the in-memory
    object may legitimately hold whatever a sender typed, and it is only when that
    value is written into a line-delimited format that the delimiter matters.
    """
    s = "" if value is None else str(value)
    s = s.replace("\r", " ").replace("\n", " ")
    s = "".join(" " if (ord(c) < 32 or ord(c) == 127) else c for c in s)
    return s[:_MAX_HEADER]


def new_id(prefix: str) -> str:
    """A locally-generated identifier that needs no coordination to be unique.

    Time prefix so identifiers sort roughly chronologically for a human reading
    a directory listing; random suffix so two agents generating in the same
    second cannot collide. Neither participant has to ask the other anything.
    """
    return f"{prefix}-{int(time.time())}-{secrets.token_hex(6)}"


@dataclass
class Message:
    """One amail message.

    `to` is a list because a message may be addressed to several correspondents;
    the broker checks each against the sender's contact list independently, so a
    partially-permitted message is refused rather than partially delivered.
    """

    sender: str
    to: list
    subject: str
    body: str
    message_id: str = field(default_factory=lambda: new_id("msg"))
    thread_id: str = ""
    parent: Optional[str] = None
    date: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if isinstance(self.to, str):
            self.to = [self.to]
        # A message that opens a thread mints its identifier. A reply carries the
        # one it was given, unchanged — the thread is named by whoever opened it
        # and is never renamed.
        if not self.thread_id:
            self.thread_id = new_id("thr")

    def reply(self, sender: str, body: str, subject: Optional[str] = None) -> "Message":
        """Build a reply that joins this thread rather than opening a parallel one."""
        return Message(
            sender=sender,
            to=[self.sender],
            subject=subject if subject is not None else self.subject,
            body=body,
            thread_id=self.thread_id,
            parent=self.message_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Message":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def serialize(self) -> str:
        """RFC-5322-shaped headers, then a blank line, then the body.

        Readable by an ordinary mail client, which is the point of storing in a
        Maildir at all. Transport headers are deliberately absent: they belong to
        the journey, not the message.

        EVERY header value is passed through _hdr(). A newline inside any field
        ends the header block early, so an attacker-chosen subject could inject
        arbitrary headers and a blank line — making the rest of their text the
        body a mail client renders, and orphaning the real one. Interpolating
        untrusted values into a line-delimited format is the same class of bug as
        SQL injection, and the fix is the same: neutralise the delimiter.
        """
        headers = [
            f"Message-ID: {_hdr(self.message_id)}",
            f"Thread-ID: {_hdr(self.thread_id)}",
            f"Date: {_hdr(self.date)}",
            f"From: {_hdr(self.sender)}",
            f"To: {_hdr(', '.join(self.to))}",
            f"Subject: {_hdr(self.subject)}",
        ]
        if self.parent:
            headers.append(f"In-Reply-To: {_hdr(self.parent)}")
        return "\n".join(headers) + "\n\n" + self.body + "\n"

    @classmethod
    def deserialize(cls, raw: str) -> "Message":
        head, _, body = raw.partition("\n\n")
        h: Dict[str, str] = {}
        for line in head.splitlines():
            k, _, v = line.partition(":")
            h[k.strip().lower()] = v.strip()
        return cls(
            sender=h.get("from", ""),
            to=[a.strip() for a in h.get("to", "").split(",") if a.strip()],
            subject=h.get("subject", ""),
            body=body.rstrip("\n"),
            message_id=h.get("message-id", ""),
            thread_id=h.get("thread-id", ""),
            parent=h.get("in-reply-to") or None,
            date=h.get("date", ""),
        )

    def sort_key(self):
        """Deterministic ordering without coordination.

        (date, message_id) — the message id breaks ties, so two messages written
        in the same second still order identically for every reader.
        """
        return (self.date, self.message_id)
