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
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Dict, Iterable, Optional, Union

from macf.pd.recurrence import Recurrence
from macf.pd.schedule import CronExpr, _utc

#: An entry's id: ``e-`` and 12 hex digits. Opaque, and within the MacEff channel's id
#: pattern, which a calling card's ``@`` is not (#734's class).
ENTRY_ID = re.compile(r"^e-[0-9a-f]{12}$")

_RELATIVE = re.compile(r"^in (\d+)([mhd])$")
_TOMORROW = re.compile(r"^tomorrow (\d{1,2}):(\d{2})$")
_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


#: An entry made, with every field it holds, and an entry removed. The event log is the only
#: store (MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)): the entries an agent holds are
#: what these events fold to.
EVENT_ENTRY_ADDED = "pd_entry_added"
EVENT_ENTRY_REMOVED = "pd_entry_removed"
#: An entry edited (its whole new form, under the same id), paused, and resumed. A pause stops
#: its firings without forgetting it; a resume starts them again from the moment of resuming,
#: so the instants that passed while it was paused are not fired late.
EVENT_ENTRY_CHANGED = "pd_entry_changed"
EVENT_ENTRY_PAUSED = "pd_entry_paused"
EVENT_ENTRY_RESUMED = "pd_entry_resumed"
ENTRY_EVENTS = (EVENT_ENTRY_ADDED, EVENT_ENTRY_REMOVED, EVENT_ENTRY_CHANGED, EVENT_ENTRY_PAUSED,
                EVENT_ENTRY_RESUMED)


def new_entry_id() -> str:
    return "e-" + secrets.token_hex(6)


def fold(events: Iterable[dict], card: str) -> Dict[str, dict]:
    """The entries the agent ``card`` holds, from its events read oldest first. Another agent's
    events, and a record whose id isn't an entry id, change nothing."""
    held: Dict[str, dict] = {}
    for event in events:
        data = event.get("data") if isinstance(event, dict) else None
        if not isinstance(data, dict) or data.get("agent") != card:
            continue
        entry_id = data.get("id")
        if not isinstance(entry_id, str) or not ENTRY_ID.match(entry_id):
            continue
        kind = event.get("event")
        if kind == EVENT_ENTRY_ADDED:
            held[entry_id] = data
        elif kind == EVENT_ENTRY_REMOVED:
            held.pop(entry_id, None)
        elif entry_id not in held:
            continue  # an edit, pause or resume of an entry not held changes nothing
        elif kind == EVENT_ENTRY_CHANGED:
            # The edit carries the entry's whole new form. A pause outlives it, and so does a
            # resume: an edit that keeps the start must not bring back what the pause covered.
            kept = {k: held[entry_id][k] for k in ("paused_at", "resumed_at", "skipped_in_pause")
                    if held[entry_id].get(k)}
            held[entry_id] = {**data, **kept}
        elif kind == EVENT_ENTRY_PAUSED:
            held[entry_id] = {**held[entry_id], "paused_at": data.get("at")}
        elif kind == EVENT_ENTRY_RESUMED:
            entry = {k: v for k, v in held[entry_id].items() if k != "paused_at"}
            held[entry_id] = {**entry, "resumed_at": data.get("at"), "skipped_in_pause": data.get("skipped", 0)}
    return held


#: The fields of an entry's newest pd_entry_fired that its views carry as ``last_fired``.
LAST_FIRED_FIELDS = ("for", "late_s", "missed", "notified")


def with_last_firing(held: Dict[str, dict], events: Iterable[dict], card: str, fired_event: str) -> list:
    """The entries held, each carrying ``last_fired`` from its newest *fired_event* (the
    scheduler's pd_entry_fired) in *events*, read oldest first: the instant it fired for and how late it fired, so the record a
    pd_entry_due notice points to says how late the wake is (MIS-0002-R34
    (late_run_MUST_state_lateness)). Read from the log, which stays the only store."""
    last: Dict[str, dict] = {}
    for event in events:
        data = event.get("data") if isinstance(event, dict) else None
        if (event.get("event") == fired_event and isinstance(data, dict) and data.get("agent") == card
                and data.get("id") in held):
            last[data["id"]] = {k: data.get(k) for k in LAST_FIRED_FIELDS}
    return [{**entry, "last_fired": last[entry_id]} if entry_id in last else entry
            for entry_id, entry in held.items()]


class OneShot:
    """A single instant. It fires once, and an entry ends after it."""

    def __init__(self, at: datetime):
        _utc(at)
        self.at = at

    def next_after(self, after: datetime) -> Optional[datetime]:
        return self.at if _utc(self.at) > _utc(after) else None


When = Union[OneShot, CronExpr, Recurrence]


def when_of(entry: dict) -> When:
    """An entry's time shape, read back from what was recorded: a fixed instant, or the shape and
    its start, in the entry's zone."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(entry["zone"]) if entry.get("zone") not in (None, "UTC") else timezone.utc
    start = datetime.fromisoformat(entry["start"])
    try:
        return OneShot(datetime.fromisoformat(entry["when"]))
    except ValueError:
        return parse_when(entry["when"], tz, start, start=start)


def firings_between(entry: dict, after: datetime, until: datetime, cap: int = 10000) -> int:
    """How many of ``entry``'s instants fall strictly after ``after`` (and its start) and at or
    before ``until``: the firings a pause covered, which a resume says rather than fires."""
    when = when_of(entry)
    t, n = max(after, datetime.fromisoformat(entry["start"])), 0
    while n < cap and (t := when.next_after(t)) is not None and t <= until:
        n += 1
    return n


def next_fire(entry: dict, now: datetime) -> Optional[datetime]:
    """When ``entry`` next fires after ``now``, or None when it never will, or is paused."""
    if entry.get("paused_at"):
        return None
    return when_of(entry).next_after(now)


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
