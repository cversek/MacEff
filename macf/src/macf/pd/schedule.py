"""The scheduler's core: when a schedule fires, and what a downtime's missed runs become.

Pure functions over explicit times. Nothing here reads a clock, writes an event or
starts a run; the scheduler that does those decides from what these return.

The cron dialect is the common five fields: minute, hour, day of month, month, day of
week. Each is ``*``, a number, a range ``a-b``, a list ``a,b``, or a step ``*/n``,
``a-b/n`` or ``a/n``. Day of week 0 and 7 are both Sunday. When both day fields are
restricted, a day matching either one fires, as cron does.

A cron is read in one timezone. A wall-clock time that does not exist there (the hour
skipped when the clocks go forward) is skipped, and one that happens twice (when they go
back) fires once, at its first occurrence. Times are compared as instants, in UTC: two
aware datetimes sharing a tzinfo compare by wall clock with ``fold`` ignored, which gets
the repeated hour wrong.
"""
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Deque, FrozenSet, Iterator, Optional

from macf.pd.interface import MissedRunPolicy, Window

#: How far ahead a cron is searched. Five years holds every pairing of month, day and
#: weekday, the 29th of February included, so a cron with no firing in five years has
#: none at all.
SEARCH_YEARS = 5

_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day of month", 1, 31),
    ("month", 1, 12),
    ("day of week", 0, 7),
)


def _utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        raise ValueError(f"{when} has no timezone; the scheduler compares instants only")
    return when.astimezone(timezone.utc)


def _parse_field(text: str, name: str, low: int, high: int) -> FrozenSet[int]:
    values = set()
    for part in text.split(","):
        base, slash, step_text = part.partition("/")
        try:
            step = int(step_text) if slash else 1
            if base == "*":
                start, end = low, high
            elif "-" in base:
                first, last = base.split("-", 1)
                start, end = int(first), int(last)
            else:
                start = int(base)
                end = high if slash else start
        except ValueError:
            raise ValueError(
                f"the {name} field {text!r} is not a number, a range, a list or a step"
            ) from None
        if step < 1:
            raise ValueError(f"the {name} field {text!r} has a step below 1")
        if not low <= start <= end <= high:
            raise ValueError(f"the {name} field {text!r} is outside {low}-{high}")
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class CronExpr:
    """A parsed cron, read in ``tz``. Build it with :meth:`parse`, which refuses one it
    cannot read and one that can never fire."""

    text: str
    tz: tzinfo
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days: FrozenSet[int]
    months: FrozenSet[int]
    weekdays: FrozenSet[int]  # 0 is Sunday
    days_unrestricted: bool
    weekdays_unrestricted: bool

    @classmethod
    def parse(cls, text: str, tz: tzinfo = timezone.utc) -> "CronExpr":
        fields = text.split()
        if len(fields) != 5:
            raise ValueError(
                f"{text!r} is not a cron: it needs five fields, minute, hour, day of month, "
                "month and day of week")
        minutes, hours, days, months, weekdays = (
            _parse_field(field, name, low, high)
            for field, (name, low, high) in zip(fields, _FIELDS, strict=True))
        cron = cls(
            text=text, tz=tz, minutes=minutes, hours=hours, days=days, months=months,
            weekdays=frozenset(day % 7 for day in weekdays),
            # cron's own rule: a day field written from * does not restrict on its own
            days_unrestricted=fields[2].startswith("*"),
            weekdays_unrestricted=fields[4].startswith("*"),
        )
        if cron.next_after(datetime(2000, 1, 1, tzinfo=timezone.utc)) is None:
            raise ValueError(f"{text!r} never fires: no date has those days in those months")
        return cron

    def _day_matches(self, day: date) -> bool:
        in_month = day.day in self.days
        in_week = day.isoweekday() % 7 in self.weekdays
        if self.days_unrestricted or self.weekdays_unrestricted:
            return in_month and in_week
        return in_month or in_week

    def iter_after(self, after: datetime) -> Iterator[datetime]:
        """Every firing strictly after ``after``, in order, up to SEARCH_YEARS ahead."""
        after_utc = _utc(after)
        day = after.astimezone(self.tz).date()
        last_day = day + timedelta(days=366 * SEARCH_YEARS)
        hours, minutes = sorted(self.hours), sorted(self.minutes)
        while day <= last_day:
            if day.month in self.months and self._day_matches(day):
                for hour in hours:
                    for minute in minutes:
                        wall = datetime.combine(day, time(hour, minute))
                        when = wall.replace(tzinfo=self.tz)  # fold 0: a repeated time's first
                        if _utc(when).astimezone(self.tz).replace(tzinfo=None) != wall:
                            continue  # this wall-clock time does not exist in tz
                        if _utc(when) > after_utc:
                            yield when
            day += timedelta(days=1)

    def next_after(self, after: datetime) -> Optional[datetime]:
        """The first firing strictly after ``after``, or None if there is none ahead."""
        return next(self.iter_after(after), None)


@dataclass(frozen=True, kw_only=True)
class RunPlan:
    """What a schedule owes now. ``missed`` counts the firings that will not run."""

    run_at: Optional[datetime]
    scheduled_for: Optional[datetime]
    late_s: Optional[float]
    missed: int
    first_missed: Optional[datetime]
    last_missed: Optional[datetime]
    next_regular: Optional[datetime]


def _clock(hhmm: str, window: Window) -> time:
    try:
        return time.fromisoformat(hhmm)
    except ValueError:
        raise ValueError(f"the window {window.start}-{window.end} has a time that is not one") from None


def check_window(window: Window) -> None:
    """Refuse a window whose ends are not times of day; its format alone admits 25:00."""
    _clock(window.start, window)
    _clock(window.end, window)


def _window_opening(now: datetime, window: Window, tz: tzinfo) -> datetime:
    """``now`` if it falls in the window, else the window's next opening. A window whose
    end is before its start runs across midnight."""
    start, end = _clock(window.start, window), _clock(window.end, window)
    local = now.astimezone(tz)
    clock = local.time()
    inside = start <= clock < end if start <= end else (clock >= start or clock < end)
    if inside:
        return now
    opening = datetime.combine(local.date(), start).replace(tzinfo=tz)
    if _utc(opening) <= _utc(now):
        opening = datetime.combine(local.date() + timedelta(days=1), start).replace(tzinfo=tz)
    return opening


def plan_runs(cron: CronExpr, missed_run: MissedRunPolicy, *, last_due: Optional[datetime],
              boot: datetime, now: datetime, since: Optional[datetime] = None,
              restarts_unit: bool = False) -> RunPlan:
    """What ``cron`` owes at ``now``.

    ``last_due`` is the time the newest recorded run was scheduled for. A schedule that
    has never run has none; ``since`` then says when it was declared, and nothing before
    that is owed. ``boot`` is when the daemon started.

    A firing before ``boot`` was missed, because no daemon was there to run it, and its
    fate is the declared missed-run policy (MIS-0002-R25 (missed-run_policy_MUST_be_listed));
    there is no default (MIS-0002-R110 (scheduler_MUST-NOT_default_missed-run_policy)). A
    firing since ``boot`` is due: the newest one runs now and says how late it is
    (MIS-0002-R34 (late_run_MUST_state_lateness)), standing in for any older one, which
    counts as missed. A missed run whose act restarts a unit is never replayed, whatever
    the policy (MIS-0002-R27 (scheduler_MUST-NOT_replay_restart_runs)).
    """
    origin = last_due if last_due is not None else since
    if origin is None:
        raise ValueError("a schedule that has never run needs the time it was declared")
    now_utc, boot_utc = _utc(now), _utc(boot)

    missed, first_missed = 0, None
    recent: Deque[datetime] = deque(maxlen=2)  # the last two missed firings
    latest_due: Optional[datetime] = None
    next_regular: Optional[datetime] = None
    for when in cron.iter_after(origin):
        if _utc(when) > now_utc:
            next_regular = when
            break
        if _utc(when) < boot_utc:
            not_run = when  # no daemon was there to run it
        elif latest_due is None:
            latest_due = when
            continue
        else:
            not_run, latest_due = latest_due, when  # the newer due firing stands in for it
        missed += 1
        first_missed = first_missed or not_run
        recent.append(not_run)

    def plan(run_at: Optional[datetime], scheduled_for: Optional[datetime], ran_a_missed: bool) -> RunPlan:
        count = missed - 1 if ran_a_missed else missed
        last = (recent[-2] if len(recent) > 1 else None) if ran_a_missed else (recent[-1] if recent else None)
        return RunPlan(
            run_at=run_at, scheduled_for=scheduled_for,
            late_s=(_utc(run_at) - _utc(scheduled_for)).total_seconds() if run_at else None,
            missed=count, first_missed=first_missed if count else None,
            last_missed=last if count else None, next_regular=next_regular)

    if latest_due is not None:
        return plan(now, latest_due, ran_a_missed=False)
    if not missed or restarts_unit or missed_run.kind in ("skip", "report_only"):
        return plan(None, None, ran_a_missed=False)
    if missed_run.kind == "run_once":
        return plan(now, recent[-1], ran_a_missed=True)
    run_at = _window_opening(now, missed_run.window, cron.tz)
    if next_regular is not None and _utc(next_regular) <= _utc(run_at):
        return plan(None, None, ran_a_missed=False)  # the next regular run comes first
    return plan(run_at, recent[-1], ran_a_missed=True)
