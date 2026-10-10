"""Where a piece of input came from: the operator, a channel, or the harness.

Two producers record the operator's activity, the prompt hook and the
transcript monitor, and both read input the client delivers on its own as
well as what the operator types. The transcript's origin record says which is
which on a delivered entry. A queued entry has no origin record, and the
prompt hook sees only the text, so they read the opening the client writes
instead: a channel tag, or one of its notice forms.

Only openings the client writes are read. The content of a channel event or
a notice can carry anything, including a forged tag of its own.
"""

from typing import Optional

CHANNEL_TAG_OPENING = "<channel "

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
