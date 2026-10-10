"""Observation acts as events, and the state they fold into.

Every invitation, pause, resume and ending is an event in the observed agent's own log
(MIS-0002-R90 (observation_acts_MUST_be_events)); the current state is never stored
anywhere else, so it is whatever the log says. Each function here checks one act and
returns the event to append; ``fold`` reads a log back. Nothing here appends, opens a
socket or reads the clock: the caller passes ``now``.

Who is asking is the caller's to establish. ``end`` takes ``ended_by`` as given, and the
caller derives it from the transport the act arrived on: the observed agent's own control
socket, the onlooker presenting its secret, the operator's surface. Never from a field in
the request, or an onlooker could end an observation as the operator.

Binding an onlooker. On a shared login every agent has the same uid, so a socket peer's
credentials cannot say which agent is reading a stream. Each invitation therefore
carries a secret, delivered to the onlooker through its own channel; the stream admits
whoever presents it. The log keeps only the secret's hash, so the record can be read
without handing out the key.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, Iterable, Optional

EVENT_INVITE = "pd_observe_invite"
EVENT_PAUSE = "pd_observe_pause"
EVENT_RESUME = "pd_observe_resume"
EVENT_END = "pd_observe_end"

ACTIVE = "active"
PAUSED = "paused"
ENDED = "ended"

#: Who may end an observation (MIS-0002-R86, R87), and the lease's own ending (R89).
ENDED_BY = ("observed", "onlooker", "operator", "lease")

#: A calling card: a name, ``@``, and the first six hex digits of the agent's UUID.
_CARD = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}@[0-9a-f]{6}$")


class ActRefused(ValueError):
    """An act the record does not allow, with the reason."""


@dataclass(frozen=True)
class Invitation:
    """A minted invitation: the event to append, and the secret for the onlooker's channel only."""

    event: dict
    secret: str


@dataclass(frozen=True)
class Observation:
    """One onlooker's observation, as the log says it stands."""

    onlooker: str
    status: str
    stream_from: int
    secret_sha256: str
    lease_until: Optional[float] = None
    ended_by: Optional[str] = None
    history: tuple = field(default_factory=tuple)
    #: What the pauses withhold: ``(from, to)`` transcript offsets, ``to`` None while one holds.
    pauses: tuple = field(default_factory=tuple)


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _check_card(card: str, what: str) -> None:
    """MIS-0002-R94 (invitation_MUST_name_card): a calling card, never a login user."""
    if not isinstance(card, str) or not _CARD.match(card):
        raise ActRefused(f"the {what} must be named by calling card (Name@abc123), not {card!r}")


def fold(events: Iterable[dict]) -> Dict[str, Observation]:
    """The observations a log describes, by onlooker card. Events for others are ignored."""
    state: Dict[str, Observation] = {}
    for ev in events:
        kind, data = ev.get("event"), ev.get("data") or {}
        who = data.get("onlooker")
        if kind == EVENT_INVITE:
            state[who] = Observation(onlooker=who, status=ACTIVE, stream_from=int(data["stream_from"]),
                                     secret_sha256=data["secret_sha256"], lease_until=data.get("lease_until"),
                                     history=(EVENT_INVITE,))
        elif who in state and state[who].status != ENDED:
            o = state[who]
            if kind == EVENT_PAUSE and o.status == ACTIVE:
                state[who] = replace(o, status=PAUSED, history=o.history + (kind,),
                                     pauses=o.pauses + ((int(data["at"]), None),))
            elif kind == EVENT_RESUME and o.status == PAUSED:
                began = o.pauses[-1][0]
                state[who] = replace(o, status=ACTIVE, history=o.history + (kind,),
                                     pauses=o.pauses[:-1] + ((began, int(data["at"])),))
            elif kind == EVENT_END:
                state[who] = replace(o, status=ENDED, ended_by=data.get("ended_by"), history=o.history + (kind,))
    return state


def invite(observed: str, onlooker: str, stream_from: int, state: Dict[str, Observation], *,
           container_of: Callable[[str], Optional[str]], lease_until: Optional[float] = None,
           now: Optional[float] = None) -> Invitation:
    """The observed agent invites an onlooker (MIS-0002-R82). Returns the event and the secret.

    ``stream_from`` is the transcript offset at the invitation, so the stream holds nothing
    from before it (R84). ``container_of`` names the container a card's agent runs in, None
    for the host itself, and raises ``LookupError`` for an agent it cannot place.
    """
    _check_card(observed, "observed agent")
    _check_card(onlooker, "onlooker")
    if onlooker == observed:
        raise ActRefused("an agent does not invite itself to watch its own session")
    current = state.get(onlooker)
    if current is not None and current.status != ENDED:
        raise ActRefused(f"{onlooker} already has an observation that is {current.status}; end it first")
    try:
        same_place = container_of(observed) == container_of(onlooker)
    except LookupError as e:
        raise ActRefused(f"cannot tell where {onlooker} runs, so it is not invited: {e}") from e
    if not same_place:
        # MIS-0002-R111 (invitation_MUST-NOT_cross_containers)
        raise ActRefused(f"{onlooker} runs in another container than {observed}; an invitation does not cross")
    if not isinstance(stream_from, int) or stream_from < 0:
        raise ActRefused("the stream starts at a transcript offset, a non-negative integer")
    if lease_until is not None and now is not None and lease_until <= now:
        raise ActRefused("the lease ends before the invitation starts")
    secret = secrets.token_urlsafe(32)
    data = {"onlooker": onlooker, "observed": observed, "stream_from": stream_from,
            "secret_sha256": _digest(secret)}
    if lease_until is not None:
        data["lease_until"] = lease_until  # MIS-0002-R88 (invitation_MAY_carry_lease)
    return Invitation(event={"event": EVENT_INVITE, "data": data}, secret=secret)


def pause(onlooker: str, state: Dict[str, Observation], *, at: int) -> dict:
    """The observed agent pauses a stream (MIS-0002-R92 (owner_MAY_pause_stream)).

    ``at`` is the transcript offset when the pause is taken, as ``stream_from`` is for the
    invitation. What is written from there until the resume is withheld from the stream,
    wherever the stream's reads happen to fall.
    """
    o = _live(onlooker, state)
    if o.status != ACTIVE:
        raise ActRefused(f"{onlooker}'s observation is {o.status}, not active")
    _check_offset(at, o)
    return {"event": EVENT_PAUSE, "data": {"onlooker": onlooker, "by": "observed", "at": at}}


def resume(onlooker: str, state: Dict[str, Observation], *, at: int) -> dict:
    """The observed agent resumes a paused stream; ``at`` is the transcript offset when it does.

    Take ``at`` after the paused work's output is in the transcript. A resume run beside
    the tool that prints, in the same turn, is too early: whatever that tool writes after
    the offset is read falls outside the pause and goes out.
    """
    o = _live(onlooker, state)
    if o.status != PAUSED:
        raise ActRefused(f"{onlooker}'s observation is {o.status}, not paused")
    _check_offset(at, o)
    return {"event": EVENT_RESUME, "data": {"onlooker": onlooker, "by": "observed", "at": at}}


def end(onlooker: str, ended_by: str, state: Dict[str, Observation]) -> dict:
    """End an observation: the observed agent or the onlooker (R86), the operator for any
    (R87), or the lease (R89), which records the same event as a party's ending."""
    if ended_by not in ENDED_BY:
        raise ActRefused(f"an observation is ended by one of {', '.join(ENDED_BY)}, not {ended_by!r}")
    _live(onlooker, state)
    return {"event": EVENT_END, "data": {"onlooker": onlooker, "ended_by": ended_by}}


def expired(state: Dict[str, Observation], now: float) -> list:
    """The ending events owed for leases that have run out (MIS-0002-R89 (lease_end_MUST_match_party_end))."""
    return [end(o.onlooker, "lease", state) for o in state.values()
            if o.status != ENDED and o.lease_until is not None and o.lease_until <= now]


def lapsed(o: Observation, now: float) -> bool:
    """True once the observation's lease has run out, whether or not its end is logged yet."""
    return o.lease_until is not None and o.lease_until <= now


def admit(onlooker: str, presented: str, state: Dict[str, Observation], *, now: float) -> Optional[Observation]:
    """The observation a stream may serve to whoever presents ``presented`` for ``onlooker``.

    None unless the onlooker was invited, the observation has not ended, its lease has not
    run out at ``now``, and the secret matches. The lease is checked here, not only when a
    sweep logs its end, because the lease ends the invitation itself (R88). A stream checks
    the same before every send. A paused observation is admitted, so the onlooker sees that
    it is paused (R93).
    """
    o = state.get(onlooker)
    if o is None or o.status == ENDED or not isinstance(presented, str) or lapsed(o, now):
        return None
    if not hmac.compare_digest(_digest(presented), o.secret_sha256):
        return None
    return o


def _live(onlooker: str, state: Dict[str, Observation]) -> Observation:
    o = state.get(onlooker)
    if o is None:
        raise ActRefused(f"{onlooker} was never invited")
    if o.status == ENDED:
        raise ActRefused(f"{onlooker}'s observation has ended")
    return o


def _check_offset(at: int, o: Observation) -> None:
    """The transcript only grows, so an act is never taken at an offset earlier than the last
    one the observation recorded. A resume before its own pause would withhold nothing."""
    if not isinstance(at, int) or at < 0:
        raise ActRefused("a pause or a resume is taken at a transcript offset, a non-negative integer")
    last = max([o.stream_from] + [x for pair in o.pauses for x in pair if x is not None])
    if at < last:
        raise ActRefused(f"offset {at} is earlier than {last}, the last one this observation recorded")
