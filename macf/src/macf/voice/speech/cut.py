"""What the operator heard of the agent's speech when a key cut it off (MIS-0008 R27, R55).

A key the operator presses while the agent talks opens a recording, and the speech stops mid
sentence (R29). The operator heard part of what the agent meant to say. So the agent is told, with
the words actually played before the cut and the words that weren't, and it knows what to repeat.

HOW THE WORDS ARE KNOWN. Whole sentences played to the end are known exactly. For the sentence
cut, the worker knows how long it had played. An engine that reports when each word ends gives the
words before that time exactly ("measured"). One that doesn't, as the Kokoro engine doesn't, gets
an estimate: the sentence's speech is spread over its words by their length, and a word counts as
heard only once its estimated end has played ("estimated"). The record says which, so the agent
doesn't take an estimate for a measurement.

WHERE IT GOES. The worker writes one record, in the agent's own home, of the latest cut. The
agent's daemon attaches it to the next utterance it delivers, which is usually what the interrupting
key was pressed to say. If none comes, the prompt hook shows it once. Either way it is told once.
These are the agent's own words, never the operator's, so they may sit in the agent's home.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import NamedTuple, Optional, Sequence

from macf.voice import state

#: The silence the engine's audio starts and ends with (``backends.soften``): no word plays in it.
LEAD_IN_S = 0.12
LEAD_OUT_S = 0.05
#: How long a cut stays worth telling. One told past this would read as news about the present.
TELL_WITHIN_S = 600.0
#: The longest stretch of words a record keeps of each side.
MAX_CHARS = 600


def cut_path(home: Path) -> Path:
    return state.voice_dir(home) / "speech_cut.json"


def dropped_path(home: Path) -> Path:
    """Messages dropped unspoken because another agent held the speaker, kept apart from cuts so neither
    overwrites the other before it is told."""
    return state.voice_dir(home) / "speech_dropped.json"


class Split(NamedTuple):
    """One cut sentence, split at the cut, and whether the split was measured or estimated."""

    heard: str
    unheard: str
    how: str


def heard_in_sentence(sentence: str, played_s: float, duration_s: float,
                      word_ends: Optional[Sequence[float]] = None) -> Split:
    """The words of ``sentence`` heard after ``played_s`` seconds of its ``duration_s``, and the rest,
    with how that was known."""
    words = sentence.split()
    if word_ends is not None and len(word_ends) == len(words):
        n = sum(1 for end in word_ends if end <= played_s)
        return Split(" ".join(words[:n]), " ".join(words[n:]), "measured")
    speech_s = max(duration_s - LEAD_IN_S - LEAD_OUT_S, 1e-6)
    fraction = (played_s - LEAD_IN_S) / speech_s
    # Each word's end as a share of the sentence as written, spaces between words included.
    total = len(" ".join(words)) or 1
    n, ends_at = 0, -1
    for w in words:
        ends_at += len(w) + 1
        if ends_at / total <= fraction + 1e-9:      # a word ending exactly at the cut was heard
            n += 1
        else:
            break
    return Split(" ".join(words[:n]), " ".join(words[n:]), "estimated")


def _clip_end(text: str) -> str:
    """The last MAX_CHARS of what was heard: the part just before the cut matters most."""
    return text if len(text) <= MAX_CHARS else "…" + text[-MAX_CHARS:].lstrip()


def _clip_start(text: str) -> str:
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS].rstrip() + "…"


def record(home: Path, played: Sequence[str], cut_sentence: str, played_s: float, duration_s: float,
           unplayed: Sequence[str], *, word_ends: Optional[Sequence[float]] = None, why: str = "recording",
           now: Optional[float] = None) -> dict:
    """Write the latest cut: sentences played whole, the words heard of the one cut, and everything not
    heard. Replaces any earlier record, written whole so a reader never sees half of one."""
    heard_part, unheard_part, how = heard_in_sentence(cut_sentence, played_s, duration_s, word_ends)
    heard = " ".join([*played, heard_part]).strip()
    unheard = " ".join([unheard_part, *unplayed]).strip()
    entry = {"at": now if now is not None else time.time(), "why": why, "how": how,
             "heard": _clip_end(heard), "unheard": _clip_start(unheard), "told": False}
    path = cut_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry))
    os.replace(tmp, path)
    return entry


def _write(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry))
    os.replace(tmp, path)


def record_dropped(home: Path, text: str, waited_s: float, now: Optional[float] = None) -> dict:
    """Note a message dropped unspoken after waiting ``waited_s`` for another agent's speech. Drops not
    yet told add up in one record, so the agent learns of all of them at once."""
    now = now if now is not None else time.time()
    path = dropped_path(home)
    try:
        entry = json.loads(path.read_text())
    except FileNotFoundError:
        entry = {}  # noqa: MACEFF003 - no record yet is the normal state
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: voice: the record of dropped speech can't be read, so it starts again: {e}",
              file=sys.stderr)
        entry = {}
    if entry.get("told", True) or now - float(entry.get("at", 0)) > TELL_WITHIN_S:
        entry = {"count": 0, "unheard": ""}
    unheard = " / ".join(t for t in (entry["unheard"], " ".join(text.split())) if t)
    entry = {"at": now, "why": "dropped", "waited_s": waited_s, "count": entry["count"] + 1,
             "unheard": _clip_start(unheard), "told": False}
    _write(path, entry)
    return entry


def take_untold(home: Path, now: Optional[float] = None, path: Optional[Path] = None) -> Optional[dict]:
    """The latest cut (or, with ``path``, that record), if it hasn't been told and is recent; marked told
    as it is taken, so it is told once. None otherwise."""
    path = path or cut_path(home)
    try:
        entry = json.loads(path.read_text())
    except FileNotFoundError:
        return None  # noqa: MACEFF003 - no record file is the normal state: no cut has happened, so nothing is owed
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: voice: the record of a speech cut can't be read, so it isn't told: {e}", file=sys.stderr)
        return None
    if entry.get("told") or (now or time.time()) - float(entry.get("at", 0)) > TELL_WITHIN_S:
        return None
    entry["told"] = True
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry))
    os.replace(tmp, path)
    return entry


def describe(entry: dict) -> str:
    """One line for the agent: what the operator heard, and what they didn't."""
    how = "estimated from timing" if entry.get("how") == "estimated" else "measured"
    heard = entry.get("heard") or "nothing"
    unheard = entry.get("unheard") or "nothing"
    return (f"Your speech was cut off by the operator's key ({how}). They heard: \"{heard}\". "
            f"They did not hear: \"{unheard}\".")


def describe_dropped(entry: dict) -> str:
    """One line for the agent: what it said that was never played."""
    n = int(entry.get("count", 1))
    what = "One of your spoken messages wasn't" if n == 1 else f"{n} of your spoken messages weren't"
    return (f"{what} played: another agent held the speaker for {float(entry.get('waited_s', 0)):g} s, "
            f"so it was dropped. The operator did not hear: \"{entry.get('unheard') or 'nothing'}\".")


def prompt_line(home: Path, now: Optional[float] = None) -> str:
    """For the prompt hook: a cut no utterance carried, and any speech dropped unspoken, each told once;
    empty otherwise."""
    lines = []
    entry = take_untold(home, now)
    if entry:
        lines.append(f"✂️ {describe(entry)}")
    dropped = take_untold(home, now, path=dropped_path(home))
    if dropped:
        lines.append(f"🔇 {describe_dropped(dropped)}")
    return "\n".join(lines)


__all__ = ["cut_path", "describe", "describe_dropped", "dropped_path", "heard_in_sentence", "prompt_line",
           "record", "record_dropped", "take_untold"]
