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

Each declared schedule's health is derived the same way, from runs owed and runs done when
read (MIS-0002-R17 (readout_MUST_derive_health_from_runs)): ``schedule_health``. The cron
says what was owed by now, and the scheduler's events say what started, ended or was missed by
the declared policy. A run owed and not started, or started and past its limit with no end,
is overdue, and the daemon that owes it reads unhealthy while it is alive
(MIS-0002-R18 (overdue_run_MUST_read_unhealthy)).
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, ValidationError

from macf.notify.session import verify_incarnation
# The core's bound, so the daemon and every reader agree on when a unit is stale.
from macf.pd.core import LIVENESS_TOLERANCE
from macf.pd.interface import EVENT_LIVENESS, EVENT_STATE, CommandRun, Declaration, Liveness, Schedule
from macf.pd.schedule import CronExpr
from macf.pd.scheduler import (
    EVENT_DONE,
    EVENT_MISSED,
    EVENT_NOT_RUN,
    EVENT_SEEN,
    EVENT_STARTED,
    KILL_GRACE_S,
)

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
        # A malformed row costs that row's verdict, never the whole readout.
        kind = event.get("event") if isinstance(event, dict) else None
        if kind not in (EVENT_STATE, EVENT_LIVENESS):
            continue
        data = event.get("data") or {}
        if not isinstance(data, dict):
            continue
        unit = data.get("unit")
        # A unit that isn't a string can't be a declared name, and a list or a dict would
        # raise in the membership test and cost every unit its verdict.
        if data.get("agent") != declaration.agent or not isinstance(unit, str) or unit not in declared:
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


# ============================================================================
# Runs owed and runs done
# ============================================================================

RunVerdict = Literal["NONE_OWED", "OK", "DUE", "RUNNING", "OVERDUE", "FAILED", "NOT_RUN"]
#: The verdicts that make the daemon owing the runs unhealthy.
UNHEALTHY_RUNS = ("OVERDUE", "FAILED", "NOT_RUN")
#: The scheduler's events, which ``schedule_health`` reads.
SCHEDULE_EVENTS = (EVENT_SEEN, EVENT_STARTED, EVENT_DONE, EVENT_MISSED, EVENT_NOT_RUN)
#: How long after its firing a run may still be starting. The daemon starts a due run on its
#: next pass, a fraction of a second later, so this is room for a slow pass, not a policy.
START_GRACE_S = 60.0


class ScheduleHealth(BaseModel):
    """One declared schedule, as runs owed and runs done have it when read."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schedule: str
    verdict: RunVerdict
    owed: Optional[str] = None       # the newest firing owed and not started, ISO
    last_run: Optional[str] = None   # the firing the newest recorded run was for, ISO
    outcome: str = ""                # how the newest ended run ended
    detail: str


def _at(text) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None  # noqa: MACEFF003 - a time that doesn't parse is no time: the row is skipped


def schedule_health(declaration: Declaration, events: Iterable[dict], now: float) -> List[ScheduleHealth]:
    """One ``ScheduleHealth`` per declared schedule, in the declaration's order.

    ``events`` are rows of the agent's event log, in any order; the newest of each kind is
    taken by its timestamp. Nothing is kept between calls, so the verdict moves with ``now``
    alone: a run that was due a moment ago reads overdue once its grace has passed, with no
    event written in between (MIS-0002-R17 (readout_MUST_derive_health_from_runs))."""
    names = {s.name for s in declaration.schedules}
    newest: Dict[tuple, dict] = {}
    seen: Dict[str, datetime] = {}
    done_for: Dict[str, set] = {}
    for event in events:
        kind = event.get("event") if isinstance(event, dict) else None
        if kind not in SCHEDULE_EVENTS:
            continue
        data = event.get("data") or {}
        if not isinstance(data, dict) or data.get("agent") != declaration.agent:
            continue
        name = data.get("schedule")
        if not isinstance(name, str) or name not in names:
            continue
        if kind == EVENT_SEEN:
            at = _at(data.get("at"))
            if at is not None and (name not in seen or at < seen[name]):
                seen[name] = at
            continue
        if kind == EVENT_DONE:
            done_for.setdefault(name, set()).add(data.get("scheduled_for"))
        stamp = _float_or_none(event.get("timestamp")) or 0.0
        key = (kind, name)
        if key not in newest or stamp >= (_float_or_none(newest[key].get("timestamp")) or 0.0):
            newest[key] = event
    tz = ZoneInfo(declaration.timezone) if declaration.timezone else timezone.utc
    return [_schedule_health(s, tz, newest, seen.get(s.name), done_for.get(s.name, set()), now)
            for s in declaration.schedules]


def _schedule_health(s: Schedule, tz, newest: Dict[tuple, dict], seen: Optional[datetime],
                     done_for: set, now: float) -> ScheduleHealth:
    def data(kind):
        return (newest.get((kind, s.name)) or {}).get("data") or {}

    started, done, missed = data(EVENT_STARTED), data(EVENT_DONE), data(EVENT_MISSED)
    last_run = _at(started.get("scheduled_for"))
    accounted = [t for t in (last_run, _at(missed.get("last"))) if t is not None]
    origin = max(accounted + ([seen] if seen else []), default=None)
    outcome = str(done.get("outcome") or "")
    known = {"schedule": s.name, "last_run": last_run.isoformat() if last_run else None,
             "outcome": outcome}
    if not isinstance(s.run, CommandRun) and data(EVENT_NOT_RUN):
        return ScheduleHealth(**known, verdict="NOT_RUN",
                              detail=f"the daemon does not run it: {data(EVENT_NOT_RUN).get('reason', '')}")
    if origin is None:
        return ScheduleHealth(**known, verdict="NONE_OWED",
                              detail="no daemon has run this declaration yet, so nothing is owed")
    # A run in flight holds its schedule: the scheduler starts no other until it ends, so a
    # firing that passes meanwhile is not yet owed.
    if last_run is not None and started.get("scheduled_for") not in done_for:
        ran_for = now - (_float_or_none(newest[(EVENT_STARTED, s.name)].get("timestamp")) or now)
        if ran_for > s.timeout_s + KILL_GRACE_S + START_GRACE_S:
            return ScheduleHealth(**known, verdict="OVERDUE",
                                  detail=f"started {ran_for:.0f} s ago with no end recorded, past "
                                         f"its {s.timeout_s:g} s limit")
        return ScheduleHealth(**known, verdict="RUNNING", detail=f"started {ran_for:.0f} s ago")
    now_at = datetime.fromtimestamp(now, timezone.utc)
    owed = None
    for when in CronExpr.parse(s.cron, tz).iter_after(origin):
        if when > now_at:
            break
        owed = when
    if owed is not None:
        late = (now_at - owed).total_seconds()
        return ScheduleHealth(**known, owed=owed.isoformat(),
                              verdict="OVERDUE" if late > START_GRACE_S else "DUE",
                              detail=f"the run owed for {owed.isoformat()} has not started, {late:.0f} s after it")
    if not done:
        return ScheduleHealth(**known, verdict="NONE_OWED", detail="no run owed since it was first seen")
    if outcome.startswith("ok"):
        return ScheduleHealth(**known, verdict="OK", detail=f"the last run: {outcome}")
    return ScheduleHealth(**known, verdict="FAILED", detail=f"the last run: {outcome}")
