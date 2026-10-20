"""Calendar-shaped recurrence: the subset of RFC 5545's RRULE that agents' entries need.

Pure functions over explicit times, like the cron parser beside it (``pd.schedule``).
Nothing here reads a clock.

The subset:
- ``FREQ`` of ``DAILY``, ``WEEKLY`` or ``MONTHLY``, with ``INTERVAL``;
- ``FREQ`` of ``HOURLY`` or ``MINUTELY``, with ``INTERVAL``, ``COUNT`` and ``UNTIL`` only, so a
  wake can be paced in minutes, as ``FREQ=MINUTELY;INTERVAL=50`` keeps it inside an hour's
  prompt cache;
- ``BYDAY``, with an ordinal in a monthly rule (``1MO``, ``-1FR``) and ``BYSETPOS`` to pick
  from a month's matches, so "the last weekday of the month" is
  ``FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1``;
- ``BYMONTHDAY``, negative from the month's end;
- ``COUNT`` and ``UNTIL``;
- exceptions, as RFC 5545's ``EXDATE``, given beside the rule.

Any other part is refused by name, never half-read: a rule that is silently read as
something else fires at times nobody declared. Weeks start on Monday (``WKST=MO``, the
default), and no other start is accepted.

A rule is read in one timezone, at the start's wall-clock time of day, so "09:00 every
weekday" stays at 09:00 across a daylight-saving change. As with cron, a wall-clock time
that doesn't exist that day is skipped, and one that happens twice fires once, at its
first occurrence. An hourly or minutely rule steps by elapsed time from its start instead,
as RFC 5545 does, so fifty minutes is fifty minutes across a daylight-saving change.
``COUNT`` counts the rule's occurrences before exceptions are removed, as RFC 5545 does.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import FrozenSet, Iterable, Iterator, Optional, Tuple

from macf.pd.schedule import SEARCH_YEARS, _utc

_FREQS = ("MINUTELY", "HOURLY", "DAILY", "WEEKLY", "MONTHLY")
_SUBDAILY = {"MINUTELY": 60, "HOURLY": 3600}   # seconds per step
_WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")   # date.weekday() order
_PARTS = ("FREQ", "INTERVAL", "BYDAY", "BYMONTHDAY", "BYSETPOS", "COUNT", "UNTIL", "WKST")


def _int(text: str, part: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"{part}={text!r} is not a whole number") from None


def _byday(text: str, freq: str) -> Tuple[Tuple[int, int], ...]:
    """Each ``BYDAY`` item as (ordinal, weekday): 0 means every such day."""
    days = []
    for item in text.split(","):
        code, ordinal = item[-2:], item[:-2]
        if code not in _WEEKDAYS:
            raise ValueError(f"BYDAY item {item!r} names no weekday ({', '.join(_WEEKDAYS)})")
        n = _int(ordinal, "BYDAY") if ordinal not in ("", "+") else 0
        if n and freq != "MONTHLY":
            raise ValueError(f"BYDAY item {item!r} has an ordinal, which only a monthly rule takes")
        if abs(n) > 5:
            raise ValueError(f"BYDAY item {item!r}: a month has at most five of a weekday")
        days.append((n, _WEEKDAYS.index(code)))
    return tuple(days)


def _until(text: str) -> datetime:
    try:
        if text.endswith("Z"):
            return datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        pass  # noqa: MACEFF003 - falls through to the refusal below, which names the form
    raise ValueError(f"UNTIL={text!r} must be a UTC time, such as 20261231T235959Z")


def _month_days(year: int, month: int) -> int:
    nxt = date(year + month // 12, month % 12 + 1, 1)
    return (nxt - timedelta(days=1)).day


@dataclass(frozen=True)
class Recurrence:
    """A parsed rule, starting at ``start`` and read in its timezone. Build it with
    :meth:`parse`, which refuses one it can't read and one that never fires."""

    text: str
    start: datetime
    freq: str
    interval: int
    byday: Tuple[Tuple[int, int], ...]
    bymonthday: Tuple[int, ...]
    bysetpos: Optional[int]
    count: Optional[int]
    until: Optional[datetime]
    exceptions: FrozenSet[datetime]

    @property
    def tz(self) -> tzinfo:
        return self.start.tzinfo

    @classmethod
    def parse(cls, text: str, start: datetime, exceptions: Iterable[datetime] = ()) -> "Recurrence":
        _utc(start)  # refuses a naive start: rules are read in a named zone
        parts = {}
        for item in text.split(";"):
            name, sep, value = item.partition("=")
            if not sep or not value:
                raise ValueError(f"{item!r} in {text!r} is not a NAME=VALUE part")
            if name not in _PARTS:
                raise ValueError(f"{name} is not supported in a recurrence; the parts read are "
                                 f"{', '.join(_PARTS)}")
            if name in parts:
                raise ValueError(f"{name} is given twice in {text!r}")
            parts[name] = value
        freq = parts.get("FREQ")
        if freq not in _FREQS:
            raise ValueError(f"FREQ={freq} is not supported; a recurrence is {', '.join(_FREQS)}")
        if parts.get("WKST", "MO") != "MO":
            raise ValueError("WKST other than MO is not supported: weeks start on Monday")
        if freq in _SUBDAILY:
            extra = sorted(set(parts) & {"BYDAY", "BYMONTHDAY", "BYSETPOS"})
            if extra:
                raise ValueError(f"{', '.join(extra)} is not read in a {freq.lower()} rule, which takes "
                                 f"only INTERVAL, COUNT and UNTIL")
        if "COUNT" in parts and "UNTIL" in parts:
            raise ValueError("COUNT and UNTIL can't both be given (RFC 5545)")
        interval = _int(parts.get("INTERVAL", "1"), "INTERVAL")
        if interval < 1:
            raise ValueError("INTERVAL must be at least 1")
        bymonthday = tuple(_int(d, "BYMONTHDAY") for d in parts["BYMONTHDAY"].split(",")) \
            if "BYMONTHDAY" in parts else ()
        if any(d == 0 or abs(d) > 31 for d in bymonthday):
            raise ValueError("BYMONTHDAY values are 1 to 31, or -1 to -31 from the month's end")
        bysetpos = _int(parts["BYSETPOS"], "BYSETPOS") if "BYSETPOS" in parts else None
        if bysetpos is not None and (freq != "MONTHLY" or bysetpos == 0):
            raise ValueError("BYSETPOS is read only in a monthly rule, and is never 0")
        count = _int(parts["COUNT"], "COUNT") if "COUNT" in parts else None
        if count is not None and count < 1:
            raise ValueError("COUNT must be at least 1")
        rule = cls(text=text, start=start, freq=freq, interval=interval,
                   byday=_byday(parts["BYDAY"], freq) if "BYDAY" in parts else (),
                   bymonthday=bymonthday, bysetpos=bysetpos, count=count,
                   until=_until(parts["UNTIL"]) if "UNTIL" in parts else None,
                   exceptions=frozenset(_utc(e) for e in exceptions))
        if rule.next_after(start - timedelta(seconds=1)) is None:
            raise ValueError(f"{text!r} never fires after {start.isoformat()}")
        return rule

    # ------------------------------------------------------------------ dates

    def _month_matches(self, year: int, month: int) -> list:
        last = _month_days(year, month)
        days = set()
        for d in self.bymonthday:
            n = d if d > 0 else last + 1 + d
            if 1 <= n <= last:
                days.add(n)
        by_weekday = set()
        for ordinal, weekday in self.byday:
            matching = [n for n in range(1, last + 1) if date(year, month, n).weekday() == weekday]
            if ordinal == 0:
                by_weekday.update(matching)
            elif abs(ordinal) <= len(matching):
                by_weekday.add(matching[ordinal - 1] if ordinal > 0 else matching[ordinal])
        if self.bymonthday and self.byday:
            days &= by_weekday                 # in a monthly rule BYMONTHDAY limits BYDAY
        elif self.byday:
            days = by_weekday
        elif not self.bymonthday:
            days = {self.start.day} if self.start.day <= last else set()
        ordered = sorted(days)
        if self.bysetpos is not None:
            pos = self.bysetpos
            ordered = [ordered[pos - 1 if pos > 0 else pos]] if abs(pos) <= len(ordered) else []
        return [date(year, month, n) for n in ordered]

    def _dates(self, first: date, last: date) -> Iterator[date]:
        weekdays = {weekday for _, weekday in self.byday}
        if self.freq == "DAILY":
            day = first
            while day <= last:
                if (not weekdays or day.weekday() in weekdays) and \
                        (not self.bymonthday or day.day in self._monthdays(day)):
                    yield day
                day += timedelta(days=self.interval)
        elif self.freq == "WEEKLY":
            week = first - timedelta(days=first.weekday())
            for_days = sorted(weekdays) if weekdays else [first.weekday()]
            while week <= last:
                for weekday in for_days:
                    yield week + timedelta(days=weekday)
                week += timedelta(weeks=self.interval)
        else:
            year, month = first.year, first.month
            while date(year, month, 1) <= last:
                yield from self._month_matches(year, month)
                month += self.interval
                year, month = year + (month - 1) // 12, (month - 1) % 12 + 1

    def _monthdays(self, day: date) -> set:
        last = _month_days(day.year, day.month)
        return {d if d > 0 else last + 1 + d for d in self.bymonthday}

    # ------------------------------------------------------------------ instants

    def _occurrences(self) -> Iterator[datetime]:
        """Every occurrence the rule makes from its start, exceptions included, in order."""
        start_utc = _utc(self.start)
        wall_start = self.start.astimezone(self.tz)
        at = time(wall_start.hour, wall_start.minute, wall_start.second)
        first = wall_start.date()
        made = 0
        for day in self._dates(first, first + timedelta(days=366 * SEARCH_YEARS)):
            wall = datetime.combine(day, at)
            when = wall.replace(tzinfo=self.tz)    # fold 0: a repeated time's first
            if _utc(when).astimezone(self.tz).replace(tzinfo=None) != wall:
                continue                           # this wall-clock time doesn't exist that day
            if _utc(when) < start_utc:
                continue
            if self.until is not None and _utc(when) > self.until:
                return
            yield when
            made += 1
            if self.count is not None and made >= self.count:
                return

    def _steps_after(self, after_utc: datetime) -> Iterator[datetime]:
        """An hourly or minutely rule's occurrences after ``after_utc``, by elapsed time from
        the start. It jumps to the first step past ``after_utc``, so an entry made months ago
        doesn't walk every step since; the step's index is its place in ``COUNT``."""
        start_utc = _utc(self.start)
        step = timedelta(seconds=_SUBDAILY[self.freq] * self.interval)
        k = 0 if after_utc < start_utc else (after_utc - start_utc) // step + 1
        horizon = start_utc + timedelta(days=366 * SEARCH_YEARS)
        while True:
            when = start_utc + k * step
            if self.count is not None and k >= self.count:
                return
            if (self.until is not None and when > self.until) or when > horizon:
                return
            yield when.astimezone(self.tz)
            k += 1

    def iter_after(self, after: datetime) -> Iterator[datetime]:
        """Every occurrence strictly after ``after``, exceptions removed, in order."""
        after_utc = _utc(after)
        if self.freq in _SUBDAILY:
            for when in self._steps_after(after_utc):
                if _utc(when) not in self.exceptions:
                    yield when
            return
        for when in self._occurrences():
            if _utc(when) > after_utc and _utc(when) not in self.exceptions:
                yield when

    def next_after(self, after: datetime) -> Optional[datetime]:
        """The first occurrence strictly after ``after``, or None if there is none ahead."""
        return next(self.iter_after(after), None)
