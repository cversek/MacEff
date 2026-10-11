"""Each declared unit's health, derived from the agent's event log when it is asked for.

The readout calls ``health``, and the outside watch calls ``read_liveness``, the rule
``health`` applies to each unit, so they give the same verdict from the same event. Nothing here is stored, and the daemon need not be running for it
to answer (MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)).

A unit's liveness has five verdicts, because unknown is not healthy:

- ``ALIVE``: its last liveness is within the bound its own interval sets, and the
  process it names is still that process, by pid and start time
  (MIS-0002-R15 (readout_MUST_probe_liveness));
- ``STALE``: it wrote liveness and then stopped;
- ``GONE``: the process its last liveness named is no longer that process;
- ``ABSENT``: none among the events read, which may mean this deployment does not run it;
- ``UNREADABLE``: its last liveness cannot be read, so its liveness is unknown.

Runs owed against runs done (MIS-0002-R17 (readout_MUST_derive_health_from_runs),
MIS-0002-R18 (overdue_run_MUST_read_unhealthy)) join this function with the scheduler.
"""
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

from macf.notify.session import verify_incarnation
# The core's bound, so the daemon and every reader agree on when a unit is stale.
from macf.pd.core import LIVENESS_TOLERANCE
from macf.pd.interface import EVENT_LIVENESS, EVENT_STATE, Declaration, Liveness

Verdict = Literal["ALIVE", "STALE", "GONE", "ABSENT", "UNREADABLE"]
ALIVE: Verdict = "ALIVE"
STALE: Verdict = "STALE"
GONE: Verdict = "GONE"
ABSENT: Verdict = "ABSENT"
UNREADABLE: Verdict = "UNREADABLE"

#: Whether the process with this pid is still the one that started at this time.
Probe = Callable[[int, str], bool]


@dataclass(frozen=True)
class Reading:
    """What a unit's last liveness says, before anyone words it."""

    verdict: Verdict
    live: Optional[Liveness] = None  # the record, when it could be read
    age: float = 0.0                 # seconds since it was written
    bound: float = 0.0               # how old it may be before the unit is stale
    error: str = ""                  # why it could not be read


def read_liveness(event: Optional[dict], now: float, probe: Optional[Probe]) -> Reading:
    """The verdict on a unit's last ``pd_unit_alive`` event: the one rule the readout and
    the outside watch share. ``probe`` None skips the process check, for a reader that
    cannot see the pid namespace the unit runs in, and the verdict is then never GONE."""
    if event is None:
        return Reading(ABSENT)
    try:
        live = Liveness.model_validate(event.get("data"))
        stamped = float(event["timestamp"])
    except (ValidationError, KeyError, TypeError, ValueError) as e:
        return Reading(UNREADABLE, error=str(e))
    age, bound = now - stamped, LIVENESS_TOLERANCE * live.interval_s
    if age > bound:
        return Reading(STALE, live, age, bound)
    if probe is not None and not probe(live.pid, live.proc_start):
        return Reading(GONE, live, age, bound)
    return Reading(ALIVE, live, age, bound)


class UnitHealth(BaseModel):
    """One declared unit, as the event log has it when read."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: str
    state: Optional[str] = None       # the daemon's last pd_unit_state for it
    since: Optional[float] = None     # when that state was recorded
    reason: str = ""                  # the daemon's reason for that state
    liveness: Verdict
    pid: Optional[int] = None         # the process its last liveness named
    in_flight: Optional[int] = None   # work it reported started and not finished
    waiting_on: Optional[str] = None  # what it reported waiting on a person for
    detail: str                       # why the verdict is what it is


def health(declaration: Declaration, events: Iterable[dict], now: float,
           probe: Probe = verify_incarnation) -> List[UnitHealth]:
    """One ``UnitHealth`` per declared unit, in the declaration's order.

    ``events`` are rows of the agent's event log, oldest first, as the caller chose to
    read them; ``now`` is epoch time. Events of other agents, and of units the
    declaration does not name, are ignored: an undeclared process cannot read as a
    healthy unit, and a declared unit with no liveness among them reads as ABSENT.
    """
    declared = {u.name for u in declaration.units}
    states: Dict[str, dict] = {}
    lives: Dict[str, dict] = {}
    for event in events:
        kind = event.get("event")
        if kind not in (EVENT_STATE, EVENT_LIVENESS):
            continue
        data = event.get("data") or {}
        if data.get("agent") != declaration.agent or data.get("unit") not in declared:
            continue
        (states if kind == EVENT_STATE else lives)[data["unit"]] = event
    return [_unit_health(u.name, states.get(u.name), lives.get(u.name), now, probe)
            for u in declaration.units]


def _unit_health(unit: str, state_event: Optional[dict], live_event: Optional[dict],
                 now: float, probe: Probe) -> UnitHealth:
    state_data = (state_event or {}).get("data") or {}
    known = {
        "unit": unit,
        "state": _str_or_none(state_data.get("state")),
        "since": _float_or_none((state_event or {}).get("timestamp")),
        "reason": str(state_data.get("reason") or ""),
    }
    reading = read_liveness(live_event, now, probe)
    if reading.verdict == ABSENT:
        return UnitHealth(**known, liveness=ABSENT, detail="no liveness among the events read")
    if reading.verdict == UNREADABLE:
        data = live_event.get("data") or {}
        pid = data.get("pid") if isinstance(data.get("pid"), int) else None
        return UnitHealth(**known, liveness=UNREADABLE, pid=pid,
                          detail=f"the last liveness cannot be read: {reading.error}")

    live = reading.live
    reported = {"pid": live.pid, "in_flight": live.in_flight, "waiting_on": live.waiting_on}
    if reading.verdict == STALE:
        detail = (f"the last liveness was {reading.age:.0f} s ago, against a bound of "
                  f"{reading.bound:g} s from its interval of {live.interval_s:g} s")
    elif reading.verdict == GONE:
        detail = f"pid {live.pid} is no longer the process that wrote it"
    else:
        detail = f"liveness {reading.age:.0f} s ago from pid {live.pid}, still that process"
    return UnitHealth(**known, **reported, liveness=reading.verdict, detail=detail)


def _str_or_none(value) -> Optional[str]:
    return value if isinstance(value, str) else None


def _float_or_none(value) -> Optional[float]:
    """An event's epoch timestamp, which the log writes as a number; anything else is unknown."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
