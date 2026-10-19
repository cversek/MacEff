"""Agents' own entries: ids, and when an entry fires (design 2 and 3).

An entry's ``when`` is one of four shapes, each a time the agent can say plainly:
- an instant, ``2026-10-20T06:30``, read in the entry's zone;
- a time from now, ``in 20m``, ``in 2h`` or ``in 3d``, and ``tomorrow 06:30``;
- a cron, ``cron:*/5 * * * *``, the five fields ``pd.schedule`` reads;
- a recurrence, ``rrule:FREQ=WEEKLY;BYDAY=MO``, the subset ``pd.recurrence`` reads, starting at
  the instant given with ``start``, and with any exceptions.

A relative time is resolved once, when the entry is made, and stored as the instant it
names, so "in 20m" still means the same moment after a restart. Pure functions over explicit
times: nothing here reads a clock.
"""
import re
import secrets
from datetime import datetime, time, timedelta, tzinfo
from typing import Iterable, Optional, Union

from macf.pd.recurrence import Recurrence
from macf.pd.schedule import CronExpr, _utc

#: An entry's id: ``e-`` and 12 hex digits. Opaque, and within the MacEff channel's id
#: pattern, which a calling card's ``@`` is not (#734's class).
ENTRY_ID = re.compile(r"^e-[0-9a-f]{12}$")

_RELATIVE = re.compile(r"^in (\d+)([mhd])$")
_TOMORROW = re.compile(r"^tomorrow (\d{1,2}):(\d{2})$")
_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def new_entry_id() -> str:
    return "e-" + secrets.token_hex(6)


class OneShot:
    """A single instant. It fires once, and an entry ends after it."""

    def __init__(self, at: datetime):
        _utc(at)
        self.at = at

    def next_after(self, after: datetime) -> Optional[datetime]:
        return self.at if _utc(self.at) > _utc(after) else None


When = Union[OneShot, CronExpr, Recurrence]


def parse_when(text: str, tz: tzinfo, now: datetime, start: Optional[datetime] = None,
               exceptions: Iterable[datetime] = ()) -> When:
    """The shape ``text`` names, read in ``tz``. ``now`` resolves a relative time, and
    ``start`` begins a recurrence (default ``now``). Anything else is refused by name."""
    _utc(now)
    text = text.strip()
    if text.startswith("cron:"):
        return CronExpr.parse(text[len("cron:"):].strip(), tz)
    if text.startswith("rrule:"):
        return Recurrence.parse(text[len("rrule:"):].strip(), (start or now).astimezone(tz), exceptions)
    relative = _RELATIVE.match(text)
    if relative:
        amount, unit = int(relative.group(1)), relative.group(2)
        if amount < 1:
            raise ValueError(f"{text!r} is not in the future")
        return OneShot(now + timedelta(**{_UNITS[unit]: amount}))
    tomorrow = _TOMORROW.match(text)
    if tomorrow:
        hour, minute = int(tomorrow.group(1)), int(tomorrow.group(2))
        if hour > 23 or minute > 59:
            raise ValueError(f"{text!r} names no time of day")
        day = now.astimezone(tz).date() + timedelta(days=1)
        return OneShot(datetime.combine(day, time(hour, minute)).replace(tzinfo=tz))
    try:
        at = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{text!r} is not a time an entry reads: an instant, 'in 20m', 'tomorrow 06:30', "
                         "'cron:<five fields>' or 'rrule:<rule>'") from None
    at = at.replace(tzinfo=tz) if at.tzinfo is None else at
    if _utc(at) <= _utc(now):
        raise ValueError(f"{text!r} is not in the future")
    return OneShot(at)
