"""The jobs a session has scheduled with CronCreate and not cancelled (cversek/MacEff#854).

A session with a scheduled job answers ``/exit`` with a dialog ("Background work is running"),
and an injected ``/exit`` then waits on it until a person picks an option. The client keeps such
jobs in memory, so the session's transcript is the record. Observed there: a CronCreate result
carries ``toolUseResult`` ``{id, humanSchedule, recurring, durable, nextFireAt}``, and a
CronDelete result ``{id}`` with the text "Cancelled job <id>.". A recurring job expires after
seven days, and a one-shot job is gone once it has fired. A job is NOT gone when the client
restarts: a session resumed with ``-c`` gets its jobs back (seen on a seat whose job outlived a
supervisor restart), so the client's start is no bound here.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

#: A recurring job expires after this long, as the client says when it schedules one.
RECURRING_LIFETIME_S = 7 * 24 * 3600


@dataclass(frozen=True)
class Job:
    id: str
    schedule: str
    recurring: bool
    created: float


def _when(entry: dict) -> Optional[float]:
    raw = entry.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None  # noqa: MACEFF003 - an unreadable stamp is no time: the read goes on past it


def _cancels(entry: dict) -> bool:
    """Whether a tool result is CronDelete's: its text, not only its shape, since other tools'
    results can be ``{id}`` alone."""
    content = (entry.get("message") or {}).get("content")
    texts = [c.get("content") for c in content if isinstance(c, dict)] if isinstance(content, list) else []
    return any(isinstance(t, str) and t.startswith("Cancelled job ") for t in texts)


def live_jobs(transcript: Path, since: Optional[float] = None, now: Optional[float] = None) -> List[Job]:
    """The jobs scheduled in ``transcript`` after ``since`` that are still pending at ``now``: not
    cancelled, a recurring one not expired, a one-shot one not yet due. Read newest first, and
    only as far back as the seven days a recurring job lives (or ``since``, if later)."""
    from macf.utils.streaming import iter_lines_reverse
    now = time.time() if now is None else now
    floor = max(since or 0.0, now - RECURRING_LIFETIME_S)
    cancelled, live = set(), []
    for line in iter_lines_reverse(transcript):
        if '"toolUseResult"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:  # noqa: S112 - the live transcript's newest line can be cut mid-write; a line that doesn't parse can't be the one sought, and a warning would fire on most hook calls
            continue
        when = _when(entry)
        if when is not None and when < floor:
            break
        result = entry.get("toolUseResult")
        if not isinstance(result, dict) or not isinstance(result.get("id"), str):
            continue
        if set(result) == {"id"} and _cancels(entry):             # CronDelete
            cancelled.add(result["id"])
        elif "humanSchedule" in result and result["id"] not in cancelled:   # CronCreate
            recurring = bool(result.get("recurring"))
            due = result.get("nextFireAt")
            if not recurring and isinstance(due, (int, float)) and due / 1000 <= now:
                continue                                           # a one-shot job that has fired
            live.append(Job(result["id"], str(result.get("humanSchedule", "")), recurring, when or now))
    return list(reversed(live))
