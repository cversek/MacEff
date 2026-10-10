"""Where a piece of input came from: the operator, a channel, the harness, a wake, or the framework.

Two producers record the operator's activity, the prompt hook and the
transcript monitor, and both read input the client delivers on its own as
well as what the operator types. The transcript's origin record says which is
which on a delivered entry. A queued entry has no origin record, and the
prompt hook sees only the text, so they read the opening the client writes
instead: a channel tag, or one of its notice forms.

Only openings the client writes are read, and the one the persistent layer
writes on a wake. The content of a channel event or a notice can carry
anything, including a forged tag of its own. Keys the framework types carry
no opening at all, since a slash command has to open with "/", so the
framework records them as it sends them, and that record is read instead.

One channel is never the operator, whoever reads it: the MacEff channel,
through which the persistent layer delivers notices. Both producers ask
``from_maceff_channel`` of the source they found.
"""

import re
import time
from typing import Optional

CHANNEL_TAG_OPENING = "<channel "

# The MacEff channel's name as the client writes it, both in the source of the
# tag that opens a channel event and in a delivered entry's origin record:
# plugin:<plugin>:<server>.
MACEFF_CHANNEL_SOURCE = "plugin:maceff-channel:maceff"

# Origin kinds on a user entry that are not the operator acting: a background
# task's completion notice, and a message from another session.
HARNESS_ORIGIN_KINDS = frozenset({"task-notification", "peer"})

# How the client opens the same input where no origin record is kept. A queued
# copy carries the client's own tag, without the words its delivery adds: a
# message from another session opens with its cross-session tag, and a
# subagent's hand-back with its agent-message tag.
HARNESS_NOTICE_OPENINGS = (
    "<task-notification>",
    "Another Claude session sent a message:",
    "<cross-session-message ",
    "<agent-message ",
)


# A wake carries only the persistent layer's own words and message identifiers
# (MIS-0002-R77), and it opens with these. Keys typed into the session's input
# box are recorded as typing whoever typed them, so the opening is what tells a
# wake from the operator (MIS-0002-R106), and it is read before any origin
# record. Someone who types the words themselves reads as away, which errs
# toward the agent being more careful.
WAKE_OPENING = "[maceff:wake]"

# The event a keystroke the framework sends is recorded as, before it is sent.
KEYS_SENT_EVENT = "keys_sent"

# How long a record names what arrives: long enough for keys typed during a
# turn to be delivered when the turn ends. Someone who types the same text
# themselves within it reads as away, which errs toward the agent being more
# careful.
KEYS_SENT_WINDOW_SECONDS = 10 * 60

_COMMAND = re.compile(r"<command-name>(.*?)</command-name>.*?<command-args>(.*?)</command-args>", re.S)


def entry_text(content) -> str:
    """Best-effort plain text from a transcript message's ``content`` (a string or blocks)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p).strip()
    return ""


def opening_channel_source(text: str) -> Optional[str]:
    """The source named by the channel tag that opens ``text``, or None.

    The client writes that tag and sets its ``source`` from the channel's
    configured name. A tag that opens the text but does not start with
    ``source`` gives "": a channel, name unknown.
    """
    stripped = text.lstrip()
    if not stripped.startswith(CHANNEL_TAG_OPENING):
        return None
    tag = stripped.split(">", 1)[0]
    prefix = CHANNEL_TAG_OPENING + 'source="'
    if not tag.startswith(prefix):
        return ""
    return tag[len(prefix):].split('"', 1)[0]


def opens_with_harness_notice(text: str) -> bool:
    """True when ``text`` opens the way the client opens input it delivers itself."""
    return text.lstrip().startswith(HARNESS_NOTICE_OPENINGS)


def opens_with_wake(text: str) -> bool:
    """True when ``text`` opens with the persistent layer's wake words (MIS-0002-R106)."""
    return text.lstrip().startswith(WAKE_OPENING)


def typed_text(content) -> str:
    """An entry's text as it was typed: a slash command's name and arguments, else its text."""
    text = entry_text(content)
    command = _COMMAND.match(text)
    if command:
        return f"{command.group(1).strip()} {command.group(2).strip()}".strip()
    return text


def typed_by_framework(text: str, now: Optional[float] = None) -> Optional[str]:
    """The kind of keystroke the framework recorded for ``text`` within the window, or None.

    The client records whatever reaches its input box as typing, so a
    framework keystroke is known only by the record its sender made first.
    The event log is read newest first, stopping at the window's edge.
    """
    wanted = text.strip()
    if not wanted:
        return None
    from macf.agent_events_log import read_events
    cutoff = (time.time() if now is None else now) - KEYS_SENT_WINDOW_SECONDS
    for event in read_events(limit=None, reverse=True):
        stamp = event.get("timestamp")
        if isinstance(stamp, (int, float)) and stamp < cutoff:
            return None
        if event.get("event") != KEYS_SENT_EVENT:
            continue
        data = event.get("data") or {}
        if str(data.get("text", "")).strip() == wanted:
            return str(data.get("kind") or "keys")
    return None


def from_maceff_channel(source: Optional[str]) -> bool:
    """True when a channel source, from an origin record or an opening tag, is the MacEff channel.

    Its notices are the persistent layer speaking, never the operator, so they
    MUST NOT count as the operator's activity (MIS-0002-R106
    (wake_MUST-NOT_count_as_operator_activity)). The name is the one the
    transport sets (MIS-0002-R107 (hooks_MUST_tell_channels_apart_by_name)).
    """
    return source == MACEFF_CHANNEL_SOURCE
