"""Remote Control disconnects, read from the session's own transcript (#883).

When Remote Control drops, the session goes quiet for anyone away from its terminal. Claude Code
writes each disconnect into the transcript as a ``system`` record with subtype ``informational``:
``Remote Control disconnected — <reason> — run /login`` (or ``— run /remote-control to
reconnect``), or with no remedy at all when the session was ended from another device (code
4090). It writes nothing when Remote Control comes back.

So the detector below records two things: a disconnect, with its reason and the command that
fixes it, and the moment that command was run in the session. The second is the best the
transcript can say. It is not a confirmed reconnect, and the event says so in its name.

What clears which kind:

- a login disconnect (the OAuth token is unavailable, the refresh failed, the login expired)
  clears only when ``/login`` reports ``Login successful``, since ``/remote-control`` can't
  restore a login;
- a network disconnect, or a session ended elsewhere, clears when ``/remote-control`` is run, or
  when a login succeeds, which re-establishes Remote Control too (observed 2026-11-03).

The outside watch reads these events and alerts by its own path (``macf.pd.watch``), because the
channel that broke is the one the operator would have used.
"""
import re
from datetime import datetime
from typing import Dict, Optional

from .daemon import Detection

#: The events this detector records.
EVENT_DISCONNECTED = "remote_control_disconnected"
EVENT_REMEDIED = "remote_control_remedied"

#: How the client begins every disconnect record. The separator is an em dash with spaces.
PREFIX = "Remote Control disconnected"
_SEPARATOR = " — "
_REMEDY = re.compile(r"^run (/login|/remote-control)\b")
#: A session ended or deleted from another device or app: the client names the code, no remedy.
_ENDED = re.compile(r"\(code 4090\)|ended or archived|no longer reports this session")

#: Records closer together than this are one disconnect: the client wrote two a second apart on
#: 2026-09-25. Further apart, the later one shows Remote Control had come back in between, since
#: only a connection can drop, and the client records no reconnect.
SAME_DISCONNECT_S = 60.0

_LOGIN_OK = "<local-command-stdout>Login successful</local-command-stdout>"
_REMOTE_CONTROL_COMMAND = "<command-name>/remote-control</command-name>"


def classify(text: str) -> Optional[Dict[str, Optional[str]]]:
    """A disconnect record's text as ``{kind, remedy, reason}``, or None when it isn't one.

    ``kind`` is ``login``, ``network``, ``ended`` or ``unknown``; ``remedy`` the command the
    record names, ``/remote-control`` for an ended session, or None when nothing says which."""
    if not isinstance(text, str) or not text.startswith(PREFIX + _SEPARATOR):
        return None
    parts = text[len(PREFIX + _SEPARATOR):].split(_SEPARATOR)
    remedy = None
    if len(parts) > 1:
        named = _REMEDY.match(parts[-1].strip())
        if named:
            remedy = named.group(1)
            parts = parts[:-1]
    reason = _SEPARATOR.join(parts).strip()
    if remedy == "/login":
        kind = "login"
    elif _ENDED.search(reason):
        kind, remedy = "ended", "/remote-control"
    elif remedy == "/remote-control":
        kind = "network"
    else:
        kind = "unknown"
    return {"kind": kind, "remedy": remedy, "reason": reason}


def _when(entry: dict) -> Optional[float]:
    raw = entry.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None  # noqa: MACEFF003 - an unreadable stamp: the record is judged by its kind alone


def _content(entry: dict) -> str:
    """A record's text: a system record's ``content``, or a user record's message when it is a string."""
    if entry.get("type") == "system":
        content = entry.get("content")
    elif entry.get("type") == "user":
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
    else:
        return ""
    return content if isinstance(content, str) else ""


class RemoteControlWatch:
    """Whether the session's Remote Control is disconnected, from the transcript as each line
    arrives. A detector, so it sees each line once, and it returns a Detection only when the
    state changes: a disconnect opens, its kind changes, or its remedy is run."""

    def __init__(self, card: Optional[str]) -> None:
        self.card = card
        self._open: Optional[Dict[str, Optional[str]]] = None
        self._last_record_at: Optional[float] = None

    def state(self) -> Optional[Dict[str, Optional[str]]]:
        """The open disconnect, ``{kind, remedy, reason}``, or None."""
        return self._open

    def __call__(self, entry: dict) -> Optional[Detection]:
        text = _content(entry)
        if not text:
            return None
        if entry.get("type") == "system" and entry.get("subtype") == "informational":
            found = classify(text)
            if found is None:
                return None
            when, last = _when(entry), self._last_record_at
            self._last_record_at = when
            apart = when is not None and last is not None and when - last > SAME_DISCONNECT_S
            if self._open is not None and self._open["kind"] == found["kind"] and not apart:
                return None   # the same disconnect: the client wrote two records a second apart on 09-25
            # Open and well apart: it had come back unrecorded, and this is a new disconnect.
            after_reconnect = self._open is not None and apart
            self._open = found
            return Detection(EVENT_DISCONNECTED, {"agent": self.card, **found, "said": text[:300],
                                                  "after_unrecorded_reconnect": after_reconnect,
                                                  "timestamp": entry.get("timestamp", ""),
                                                  "detector": "transcript_monitor"})
        if self._open is None:
            return None
        if _LOGIN_OK in text:
            via = "/login"
        elif _REMOTE_CONTROL_COMMAND in text and self._open["kind"] != "login":
            via = "/remote-control"
        else:
            return None
        self._open = None
        return Detection(EVENT_REMEDIED, {"agent": self.card, "via": via,
                                          "timestamp": entry.get("timestamp", ""),
                                          "detector": "transcript_monitor"})
