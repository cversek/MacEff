"""Taking an observation act: check it against the observed agent's own log, then append it there.

``acts`` decides whether an act is allowed and builds its event, and appends nothing. This
module is the path that takes the act: it folds the current state from the observed
agent's own event log, asks ``acts`` for the event, and appends that event to the same
log (MIS-0002-R90 (observation_acts_MUST_be_events)). The state is never kept anywhere
else, so the next act, the stream and the per-call line all read what was written here.

The log is the one ``macf.agent_events_log`` resolves for the running agent, so these
functions run as the observed agent, on its own log. The state is read from the current
cycle; the compaction carry re-asserts open observations at the boundary, so a cycle is
enough, as it is for the per-call line.

An event that cannot be written is an act not taken. ``invite`` raises rather than hand
back a secret for an invitation the log does not hold, since the stream would refuse it.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from macf.agent_events_log import append_event, read_events

from . import acts

#: The rows a fold of the acts reads.
ACT_EVENTS = (acts.EVENT_INVITE, acts.EVENT_PAUSE, acts.EVENT_RESUME, acts.EVENT_END)


class RecordFailed(OSError):
    """The act was allowed but its event could not be appended, so it was not taken."""


def current() -> Dict[str, acts.Observation]:
    """The observations the agent's own log folds to now."""
    return acts.fold(read_events(reverse=False, only=ACT_EVENTS))


def _append(event: dict) -> dict:
    if not append_event(event["event"], event["data"]):
        raise RecordFailed(f"{event['event']} for {event['data'].get('onlooker')} was not written to the event log")
    return event


def invite(observed: str, onlooker: str, stream_from: int, *,
           container_of: Callable[[str], Optional[str]], lease_until: Optional[float] = None,
           now: Optional[float] = None) -> acts.Invitation:
    """Invite ``onlooker`` and record the invitation. Returns it; its secret goes to the
    onlooker's own channel and is never written here."""
    inv = acts.invite(observed, onlooker, stream_from, current(), container_of=container_of,
                      lease_until=lease_until, now=now)
    _append(inv.event)
    return inv


def pause(onlooker: str, *, at: int) -> dict:
    """Pause ``onlooker``'s stream at transcript offset ``at`` and record the pause."""
    return _append(acts.pause(onlooker, current(), at=at))


def resume(onlooker: str, *, at: int) -> dict:
    """Resume ``onlooker``'s stream at transcript offset ``at`` and record the resume."""
    return _append(acts.resume(onlooker, current(), at=at))


def end(onlooker: str, ended_by: str) -> dict:
    """End ``onlooker``'s observation and record the ending. ``ended_by`` is established by
    the caller from the transport the request arrived on, never from the request."""
    return _append(acts.end(onlooker, ended_by, current()))


def sweep(now: float, events: Optional[List[dict]] = None) -> List[dict]:
    """Record the ending owed for each lease that has run out by ``now`` (MIS-0002-R89).

    The state is the current cycle's, unless ``events`` is given: the compaction carry passes
    the window it folds, the cycle just closed, since by then the boundary is written and the
    current cycle no longer holds the invitation whose ending is owed."""
    state = acts.fold(events) if events is not None else current()
    return [_append(ev) for ev in acts.expired(state, now)]
