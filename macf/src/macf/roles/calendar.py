"""The calendar: roles × duties walked into events, rendered four ways.

Nothing is stored. Dated duties contribute their due; cadence duties their
occurrences in the window (with done_on notes marking cells done, and past
cells without one marking missed); roles contribute review_by and expires as
milestones. Agenda by default, a week grid, JSON, or an iCalendar file that a
calendar client can import.
"""
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from .cadence import parse_cadence
from .models import Duty, Role
from .priority import approach_mark, now, occurrences

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass
class Event:
    when: datetime
    kind: str                   # due | occurrence | review | expires
    role: Role
    duty: Optional[Duty] = None
    duration_minutes: Optional[int] = None
    done: bool = False
    missed: bool = False

    @property
    def title(self) -> str:
        if self.duty is not None:
            return self.duty.title
        return {"review": "review", "expires": "tenure ends"}[self.kind]

    @property
    def uid(self) -> str:
        who = self.duty.id if self.duty else self.role.id
        return f"{who}-{self.kind}-{self.when:%Y%m%dT%H%M}@macf.roles"

    def to_json(self) -> Dict:
        return {"when": self.when.isoformat(), "kind": self.kind, "role_id": self.role.id,
                "role": self.role.title, "icon": self.role.icon,
                "duty_id": self.duty.id if self.duty else None, "title": self.title,
                "duration_minutes": self.duration_minutes, "done": self.done, "missed": self.missed}


def window(weeks: Optional[int] = None, start: Optional[date] = None, end: Optional[date] = None,
           at: Optional[datetime] = None) -> Tuple[date, date]:
    """Default: from today for two weeks; --weeks N; or an explicit --from/--to."""
    at = at or now()
    if start is None:
        start = at.date()
    if end is None:
        end = start + timedelta(weeks=weeks or 2) - timedelta(days=1)
    return start, end


def events(pairs: Sequence[Tuple[Role, List[Duty]]], start: date, end: date,
           at: Optional[datetime] = None) -> List[Event]:
    at = at or now()
    out: List[Event] = []
    for role, duties in pairs:
        if role.state in ("expired", "retired", "paused"):
            continue
        if role.review_by and start <= role.review_by <= end:
            out.append(Event(datetime.combine(role.review_by, datetime.min.time()), "review", role))
        if role.expires and start <= role.expires <= end:
            out.append(Event(datetime.combine(role.expires, datetime.min.time()), "expires", role))
        for d in duties:
            if d.state in ("done", "deferred"):
                continue
            if d.due is not None and start <= d.due.date() <= end:
                out.append(Event(d.due, "due", role, d, done=d.state == "done"))
            if d.cadence:
                cad = parse_cadence(d.cadence)
                done = set(d.done_on_dates())
                for occ in occurrences(d, start, end, role.expires):
                    is_done = occ.date() in done
                    out.append(Event(occ, "occurrence", role, d, cad.duration_minutes,
                                     done=is_done, missed=(not is_done and occ < at)))
    out.sort(key=lambda e: (e.when, e.role.title, e.title))
    return out


# ---- renderings ----------------------------------------------------------------

def _event_line(e: Event, at: datetime) -> str:
    when = e.when.strftime("%a %m-%d") + (e.when.strftime(" %H:%M") if (e.when.hour or e.when.minute) else "      ")
    if e.duration_minutes:
        h, m = divmod(e.duration_minutes, 60)
        when += f" +{h}h" if not m else f" +{h}h{m:02d}"
    status = "✔ " if e.done else ("✗ " if e.missed else "")
    mark = "" if (e.done or e.missed) else approach_mark(e.when, e.duty.horizon_minutes() if e.duty else None, at)
    tag = {"review": " · review", "expires": " · tenure ends"}.get(e.kind, "")
    return f"{when:<20} {e.role.icon} {status}{e.title}{tag}" + (f"  {mark}" if mark else "")


def agenda(evs: Sequence[Event], start: date, end: date, at: Optional[datetime] = None) -> str:
    at = at or now()
    lines = [f"📅 {start} → {end}  ({len(evs)} event{'s' if len(evs) != 1 else ''})"]
    if not evs:
        lines.append("   nothing due")
    last_day = None
    for e in evs:
        if e.when.date() != last_day:
            last_day = e.when.date()
        lines.append("   " + _event_line(e, at))
    return "\n".join(lines)


def _cell_width(s: str) -> int:
    """Terminal columns: wide (emoji, CJK) glyphs take two, combining marks none."""
    w = 0
    for ch in s:
        if unicodedata.combining(ch) or ch == "\ufe0f":
            continue
        w += 2 if unicodedata.east_asian_width(ch) in "WF" else 1
    return w


def _fit(s: str, width: int) -> str:
    """Truncate to *width* columns and pad to exactly *width*."""
    out, w = "", 0
    for ch in s:
        cw = 0 if (unicodedata.combining(ch) or ch == "\ufe0f") else (2 if unicodedata.east_asian_width(ch) in "WF" else 1)
        if w + cw > width:
            break
        out += ch
        w += cw
    return out + " " * (width - w)


def grid(evs: Sequence[Event], start: date, end: date, at: Optional[datetime] = None, width: int = 16) -> str:
    """One row per week, one cell per day; cell text is the first event's title."""
    at = at or now()
    by_day: Dict[date, List[Event]] = {}
    for e in evs:
        by_day.setdefault(e.when.date(), []).append(e)
    first = start - timedelta(days=start.weekday())
    last = end + timedelta(days=6 - end.weekday())
    cols = 7
    sep = "┼".join("─" * width for _ in range(cols))
    lines = ["┌" + "┬".join("─" * width for _ in range(cols)) + "┐",
             "│" + "│".join(f" {n:<{width - 1}}" for n in DAY_NAMES) + "│",
             "├" + sep + "┤"]
    day = first
    while day <= last:
        head, body, more = [], [], []
        for i in range(cols):
            d = day + timedelta(days=i)
            inside = start <= d <= end
            today = "•" if d == at.date() else " "
            head.append(f"{today}{d.day:>2} {d:%b}" if inside else "")
            evs_d = by_day.get(d, [])
            cell = ""
            if evs_d:
                e = evs_d[0]
                glyph = "✔" if e.done else ("✗" if e.missed else e.role.icon)
                cell = f"{glyph} {e.title}"
            body.append(cell)
            more.append(f"+{len(evs_d) - 1} more" if len(evs_d) > 1 else "")
        for row in (head, body, more):
            lines.append("│" + "│".join(" " + _fit(c, width - 1) for c in row) + "│")
        day += timedelta(days=7)
        lines.append(("├" + sep + "┤") if day <= last else ("└" + "┴".join("─" * width for _ in range(cols)) + "┘"))
    return "\n".join(lines)


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def ics(pairs: Sequence[Tuple[Role, List[Duty]]], start: date, end: date, at: Optional[datetime] = None) -> str:
    """A VCALENDAR: one VEVENT per dated duty and milestone; cadence duties as a
    single VEVENT with an RRULE where the grammar maps (daily, weekly, monthly
    all do), so the client keeps them recurring past the window.
    """
    at = at or now()
    stamp = _ics_dt(at)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//macf_tools//roles//EN", "CALSCALE:GREGORIAN"]

    def vevent(uid: str, dt: datetime, summary: str, minutes: Optional[int], extra: Sequence[str] = ()):
        lines.extend(["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}"])
        if dt.hour or dt.minute:
            lines.append(f"DTSTART:{_ics_dt(dt)}")
            lines.append(f"DTEND:{_ics_dt(dt + timedelta(minutes=minutes or 60))}")
        else:
            lines.append(f"DTSTART;VALUE=DATE:{dt:%Y%m%d}")
            lines.append(f"DTEND;VALUE=DATE:{dt + timedelta(days=1):%Y%m%d}")
        lines.append(f"SUMMARY:{_ics_escape(summary)}")
        lines.extend(extra)
        lines.append("END:VEVENT")

    for role, duties in pairs:
        if role.state in ("expired", "retired", "paused"):
            continue
        label = f"{role.icon} {role.title}"
        if role.review_by:
            vevent(f"{role.id}-review@macf.roles", datetime.combine(role.review_by, datetime.min.time()),
                   f"{label}: review", None)
        if role.expires:
            vevent(f"{role.id}-expires@macf.roles", datetime.combine(role.expires, datetime.min.time()),
                   f"{label}: tenure ends", None)
        for d in duties:
            if d.state in ("done", "deferred"):
                continue
            if d.due is not None:
                vevent(f"{d.id}-due@macf.roles", d.due, f"{label}: {d.title}", None,
                       [f"DESCRIPTION:{_ics_escape(d.body)}"] if d.body else ())
            if d.cadence:
                cad = parse_cadence(d.cadence)
                occs = occurrences(d, start, start + timedelta(days=400), role.expires)
                if not occs:
                    continue
                first = occs[0]
                until = cad.until or role.expires
                rrule = {"daily": "FREQ=DAILY", "weekly": "FREQ=WEEKLY;BYDAY=" + ",".join(
                    ("MO", "TU", "WE", "TH", "FR", "SA", "SU")[w] for w in cad.weekdays),
                    "monthly": f"FREQ=MONTHLY;BYMONTHDAY={cad.day_of_month}"}[cad.kind]
                if until:
                    rrule += f";UNTIL={until:%Y%m%d}T235959"
                extra = [f"RRULE:{rrule}"]
                # Done occurrences stay on the calendar; the client shows them as
                # past events, which is the honest record. No EXDATE for them.
                vevent(f"{d.id}-cadence@macf.roles", first, f"{label}: {d.title}", cad.duration_minutes, extra)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
