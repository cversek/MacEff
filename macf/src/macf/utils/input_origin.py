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

A channel counts as the operator only by its exact name, among those the agent
declares as the operator's. One is never the operator, whoever reads it: the
MacEff channel, through which the persistent layer delivers notices. Both
producers ask ``operator_channel`` of the source they found.
"""

import re
import sys
import time
from pathlib import Path
from typing import FrozenSet, Optional

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


# What the client writes after a slash command it runs itself: the command's output, as
# a row of its own. It is the client speaking, so it is never anyone's typing.
LOCAL_COMMAND_OUTPUT_OPENINGS = ("<local-command-stdout>", "<local-command-stderr>")

# How the client records a slash command it ran, as a second row beside the typed text,
# a few milliseconds later. One keystroke, two rows, so each takes its own arrival.
COMMAND_ROW_OPENING = "<command-name>"


# A wake carries only the persistent layer's own words and message identifiers
# (MIS-0002-R77), and it opens with these. Keys typed into the session's input
# box are recorded as typing whoever typed them, so the opening is what tells a
# wake from the operator (MIS-0002-R106), and it is read before any origin
# record. Someone who types the words themselves reads as away, which errs
# toward the agent being more careful.
WAKE_OPENING = "[maceff:wake]"

# The event a keystroke the framework sends is recorded as, before it is sent.
KEYS_SENT_EVENT = "keys_sent"

# The event a producer records when it takes a framework keystroke as the input that
# arrived, so that a record names one arrival per producer, not every input with its text.
KEYS_MATCHED_EVENT = "keys_matched"

# How long a record names what arrives: long enough for keys typed during a
# turn to be delivered when the turn ends. A record names one arrival per
# producer, so someone who types the same text after the framework's keys have
# arrived reads as themselves. Only an input that arrives before the framework's
# own can take its record, which errs toward the agent being more careful.
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


def opens_with_local_command_output(text: str) -> bool:
    """True when ``text`` is the output the client writes for a slash command it ran."""
    return text.lstrip().startswith(LOCAL_COMMAND_OUTPUT_OPENINGS)


def opens_with_command_row(text: str) -> bool:
    """True when ``text`` is the client's record of a slash command, beside the typed row."""
    return text.lstrip().startswith(COMMAND_ROW_OPENING)


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


def typed_by_framework(text: str, now: Optional[float] = None, *, consumer: str = "",
                       consume: bool = True) -> Optional[str]:
    """The kind of keystroke the framework recorded for ``text`` within the window, or None.

    The client records whatever reaches its input box as typing, so a
    framework keystroke is known only by the record its sender made first.
    The event log is read newest first, stopping at the window's edge.

    Each record names one arrival for each ``consumer``, a producer of the
    operator's activity: the first input with its text that the consumer reads
    takes the oldest record still open, and says so with a ``keys_matched``
    event. So the operator typing the same text afterwards reads as the
    operator, not as the framework again. ``consume=False`` looks without
    taking, for a copy the consumer will read again once it is delivered.
    """
    wanted = text.strip()
    if not wanted:
        return None
    from macf.agent_events_log import append_event, read_events
    cutoff = (time.time() if now is None else now) - KEYS_SENT_WINDOW_SECONDS
    sends, taken = {}, set()
    for event in read_events(limit=None, reverse=True):
        stamp = event.get("timestamp")
        if isinstance(stamp, (int, float)) and stamp < cutoff:
            break
        data = event.get("data") or {}
        if str(data.get("text", "")).strip() != wanted:
            continue
        if event.get("event") == KEYS_SENT_EVENT:
            sends[stamp] = str(data.get("kind") or "keys")
        elif event.get("event") == KEYS_MATCHED_EVENT and data.get("consumer") == consumer:
            taken.add(data.get("send_ts"))
    still_open = sorted(ts for ts in sends if ts not in taken and isinstance(ts, (int, float)))
    if not still_open:
        return None
    kind = sends[still_open[0]]
    if consume:
        try:
            append_event(KEYS_MATCHED_EVENT, {"text": wanted, "kind": kind, "consumer": consumer,
                                              "send_ts": still_open[0]})
        except (OSError, ValueError) as e:
            print(f"⚠️ MACF: could not record that a framework keystroke arrived, so its text "
                  f"typed again within the window will read as the framework's: {e}", file=sys.stderr)
    return kind


#: How far back a box's text is looked for among the framework's keystrokes. Unsent text
#: sits in a box for as long as nobody submits it (half a day, on Oct 24), so this is far
#: wider than the window in which a keystroke names its arrival.
BOX_TEXT_WINDOW_SECONDS = 24 * 60 * 60


def framework_typed_box_text(box: str, now: Optional[float] = None) -> Optional[str]:
    """The kind of the framework keystroke that typed ``box``, the text an input box holds, or
    None when no keystroke in the window accounts for it.

    The box's text counts as the framework's when it is the start of a ``keys_sent`` record's
    text, with every run of whitespace made one space: the screen joins a wrapped line's rows
    with a space, and Ctrl-U removes text from the end. Text a person added before or after
    the framework's keys is no record's start, so it is never the framework's. Nothing is
    taken: this only looks.
    """
    wanted = " ".join(box.split())
    if not wanted:
        return None
    from macf.agent_events_log import read_events
    cutoff = (time.time() if now is None else now) - BOX_TEXT_WINDOW_SECONDS
    # A box keeps its text across a compaction, so the whole log is read back to the cutoff.
    for event in read_events(reverse=True, scope="all", only=[KEYS_SENT_EVENT]):
        stamp = event.get("timestamp")
        if isinstance(stamp, (int, float)) and stamp < cutoff:
            break
        if event.get("event") != KEYS_SENT_EVENT:
            continue
        data = event.get("data") or {}
        if data.get("kind") == "clear_input":
            continue                     # the Ctrl-U a clearing records types no text
        if " ".join(str(data.get("text", "")).split()).startswith(wanted):
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


#: Each declaration read, by path: its modification time and the names it lists. The
#: transcript monitor asks for every row it reads.
_DECLARED: dict = {}


def declared_operator_channels(agent_home: Optional[Path] = None) -> Optional[FrozenSet[str]]:
    """The channel names the agent's declaration lists as the operator's, or None while it
    lists none: no declaration, ``operator_channels`` absent, or a declaration that can't
    be read, which is said on stderr because the primal daemon refuses it too."""
    from macf.pd.interface import Declaration, declaration_path
    if agent_home is None:
        from macf.utils.paths import find_agent_home
        agent_home = find_agent_home()
    path = declaration_path(agent_home)
    if not path.exists():
        return None    # nothing declared yet
    try:
        mtime = path.stat().st_mtime_ns
    except OSError as e:
        print(f"⚠️ MACF: the declaration at {path} can't be read, so no channel counts as the "
              f"operator's: {e}", file=sys.stderr)
        return None
    cached = _DECLARED.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        listed = Declaration.model_validate_json(path.read_text()).operator_channels
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: the declaration at {path} can't be read, so no channel counts as the "
              f"operator's: {e}", file=sys.stderr)
        listed = None
    names = frozenset(listed) if listed is not None else None
    _DECLARED[path] = (mtime, names)
    return names


def operator_channel(source: Optional[str], agent_home: Optional[Path] = None) -> bool:
    """True when a channel's events count as the operator's activity
    (MIS-0002-R107 (hooks_MUST_tell_channels_apart_by_name)).

    The MacEff channel never does. Otherwise the exact name must be one the agent's
    declaration lists in ``operator_channels``. An agent that lists none, or has no
    declaration, has no operator channel: a wrong "absent" makes it more careful than it had
    to be, and a wrong "present" lets it act as if someone were there.
    """
    if from_maceff_channel(source):
        return False
    declared = declared_operator_channels(agent_home)
    return bool(source) and declared is not None and source in declared
