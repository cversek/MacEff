"""Emit what changed since a hook last spoke, not the whole block again.

A hook block is mostly the same from one emission to the next: the day, the
context weather, the model, the version, a due duty restated on every prompt.
Repeating it costs the agent tokens, since additionalContext stays in the
conversation, and costs every reader attention, because a block that is 90%
unchanged trains the eye to skip it, which is how the one changed line gets
missed.

Each emission's computed body is written to the event log as a
``hook_emission`` event and the next emission of the same hook is diffed
against it. Keeping the previous body in the log rather than a state file gives
the two guarantees that matter for free:

- **Recovery sees everything.** Reads are cycle-scoped, so the first emission
  after a compaction finds no previous body and renders the full block, which
  is what an agent that no longer holds the old one needs.
- **Nothing is lost.** The log keeps every full body; the diff is only how it
  is presented.

The full block is also sent on a hook's first emission in a session, when the
last one is older than ``hooks.full_every_mins``, and always when
``hooks.output`` is ``full``.

The agent's copy is plain text with markers. The operator's copy is the same
diff in colour: a hook's systemMessage is shown in the terminal and never sent
to the model, so colour costs no tokens there. ``NO_COLOR`` turns it off.
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

EMISSION_EVENT = "hook_emission"

# A "Key: value" line is shown as changed in place when its value moves, rather
# than as one line removed and another added.
_KEYED = re.compile(r"^([^:]{1,40}):\s")

ADDED, REMOVED, CHANGED = "+", "−", "~"

_ANSI = {
    ADDED: "\033[32m",     # green
    REMOVED: "\033[2;31m",  # dim red
    CHANGED: "\033[33m",   # yellow
    "header": "\033[2m",   # dim
}
_RESET = "\033[0m"


@dataclass
class Emission:
    """What to send, and whether it was the full block."""
    agent: str
    operator: str
    full: bool


def _setting_output_mode() -> str:
    from macf.config import resolve_setting
    mode, _ = resolve_setting("MACF_HOOK_OUTPUT", "hooks.output", "diff")
    return str(mode).strip().lower()


def _setting_full_every_mins() -> int:
    from macf.config import resolve_setting
    mins, _ = resolve_setting("MACF_HOOK_FULL_EVERY_MINS", "hooks.full_every_mins", 30, coerce=int)
    return mins


def body_lines(block: str, volatile: Sequence[str]) -> List[str]:
    """The lines of a block that are compared between emissions.

    The first line is the block's own header, which the diff replaces. Blank
    lines carry nothing, and ``volatile`` lines (the clock, the breadcrumb, the
    token counts) change every time by design and are carried by the diff
    header instead.
    """
    lines = block.splitlines()[1:]
    return [line for line in lines if line.strip() and not line.startswith(tuple(volatile))]


def diff_body(prev: Sequence[str], cur: Sequence[str]) -> Tuple[List[Tuple[str, str]], int]:
    """Changed lines between two bodies, and how many were unchanged.

    Returns ``(entries, unchanged)`` where each entry is ``(kind, line)`` with
    kind one of ADDED, REMOVED or CHANGED. Current lines come first, in their
    own order; lines that disappeared follow.
    """
    prev_set = set(prev)
    cur_set = set(cur)
    prev_by_key = {}
    for line in prev:
        m = _KEYED.match(line)
        if m:
            prev_by_key.setdefault(m.group(1), line)

    entries: List[Tuple[str, str]] = []
    unchanged = 0
    matched_keys = set()
    for line in cur:
        if line in prev_set:
            unchanged += 1
            continue
        m = _KEYED.match(line)
        if m and m.group(1) in prev_by_key:
            matched_keys.add(m.group(1))
            entries.append((CHANGED, line))
        else:
            entries.append((ADDED, line))
    for line in prev:
        if line in cur_set:
            continue
        m = _KEYED.match(line)
        if m and m.group(1) in matched_keys:
            continue
        entries.append((REMOVED, line))
    return entries, unchanged


def _color_enabled() -> bool:
    return not os.environ.get("NO_COLOR")


def render(header: str, entries: Sequence[Tuple[str, str]], unchanged: int, color: bool) -> str:
    """One header line, then one line per change."""
    tail = f" · {unchanged} unchanged" if unchanged else ""
    if color:
        out = [f"{_ANSI['header']}{header}{tail}{_RESET}"]
        out += [f"{_ANSI[kind]}{kind} {line}{_RESET}" for kind, line in entries]
    else:
        out = [f"{header}{tail}"]
        out += [f"{kind} {line}" for kind, line in entries]
    return "\n".join(out)


def last_body(hook: str, session_id: str, since_epoch: float) -> Optional[List[str]]:
    """The body this hook last emitted in this session and cycle, if recent.

    The scan is cycle-scoped and stops at the first event older than
    ``since_epoch``, so a miss means exactly "nothing from this hook in this
    session, this cycle, since then", and a miss can only ever produce the full
    block.
    """
    from macf.agent_events_log import read_events

    prefix = (session_id or "")[:8]
    for event in read_events(reverse=True):
        ts = event.get("timestamp")
        if isinstance(ts, (int, float)) and ts < since_epoch:
            return None
        if event.get("event") != EMISSION_EVENT:
            continue
        data = event.get("data", {})
        if data.get("hook") != hook or not str(data.get("session_id", "")).startswith(prefix):
            continue
        body = data.get("body")
        return list(body) if isinstance(body, list) else None
    return None


def emit(hook: str, session_id: str, block: str, header: str, volatile: Sequence[str]) -> Emission:
    """Decide full or diff for this emission, record it, and render both copies.

    ``block`` is the full block exactly as it would have been sent before;
    ``header`` is the one line that stands in for it when only the changes are
    sent, and must carry anything the reader needs every time (clock,
    breadcrumb, context level).
    """
    from macf.agent_events_log import append_event

    body = body_lines(block, volatile)
    prev = None
    if _setting_output_mode() != "full" and session_id:
        try:
            prev = last_body(hook, session_id, time.time() - _setting_full_every_mins() * 60)
        except (OSError, ValueError) as e:
            print(f"⚠️ MACF: previous {hook} emission unreadable, sending the full block: {e}",
                  file=sys.stderr)

    full = prev is None
    append_event(EMISSION_EVENT, {"hook": hook, "session_id": session_id or "", "body": body, "full": full})
    if full:
        return Emission(agent=block, operator=block, full=True)

    entries, unchanged = diff_body(prev, body)
    return Emission(
        agent=render(header, entries, unchanged, color=False),
        operator=render(header, entries, unchanged, color=_color_enabled()),
        full=False,
    )
