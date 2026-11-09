"""The jobs a session has scheduled with CronCreate and not cancelled (cversek/MacEff#854).

A session with a scheduled job answers ``/exit`` with a dialog ("Background work is running"),
and an injected ``/exit`` then waits on it until a person picks an option. The client keeps such
jobs in memory only, so the session's transcript is the record. Observed there: a CronCreate
result carries ``toolUseResult`` ``{id, humanSchedule, recurring, durable, nextFireAt}``, and a
CronDelete result ``{id}`` alone. A job dies with the client process, a recurring one expires
after seven days, and a one-shot job is gone once it has fired.
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


def live_jobs(transcript: Path, since: Optional[float] = None, now: Optional[float] = None) -> List[Job]:
    """The jobs scheduled in ``transcript`` after ``since`` (the client's start) that are still
    pending at ``now``: not cancelled, a recurring one not expired, a one-shot one not yet due.
    Read newest first, and only as far back as either bound reaches."""
    from macf.utils.streaming import iter_lines_reverse
    now = time.time() if now is None else now
    floor = max(since or 0.0, now - RECURRING_LIFETIME_S)
    cancelled, live = set(), []
    for line in iter_lines_reverse(transcript):
        if '"toolUseResult"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        when = _when(entry)
        if when is not None and when < floor:
            break
        result = entry.get("toolUseResult")
        if not isinstance(result, dict) or not isinstance(result.get("id"), str):
            continue
        if set(result) == {"id"}:                                  # CronDelete: {id}
            cancelled.add(result["id"])
        elif "humanSchedule" in result and result["id"] not in cancelled:   # CronCreate
            recurring = bool(result.get("recurring"))
            due = result.get("nextFireAt")
            if not recurring and isinstance(due, (int, float)) and due / 1000 <= now:
                continue                                           # a one-shot job that has fired
            live.append(Job(result["id"], str(result.get("humanSchedule", "")), recurring, when or now))
    return list(reversed(live))


def client_start() -> Optional[float]:
    """When the Claude Code client this process runs under started, or None when it doesn't run
    under one (an `inject` sent from outside the session)."""
    from macf.notify.session import proc_start
    from macf.pd.core import start_epoch
    from macf.pd.cutover import inside_session
    pid = inside_session()
    return start_epoch(proc_start(pid)) if pid else None
