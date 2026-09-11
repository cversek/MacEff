"""Priority tiers and the due-approach ramp, exactly as the roles policy states them.

Lexicographic by tier, never a weighted score; every placement carries the
fact that produced it, so ``role duty why`` can print it and a tier the code
cannot explain is a bug. Nothing here is stored: it is all computed from the
duty records and *now*.

    OVERDUE > DUE_SOON > BLOCKING > IMPORTANT > NORMAL > BLOCKED > DONE/DEFERRED
"""
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .cadence import Cadence, parse_cadence
from .models import Duty, Role

OVERDUE, DUE_SOON, BLOCKING, IMPORTANT, NORMAL, BLOCKED, DONE = range(7)
TIER_NAMES = ("OVERDUE", "DUE_SOON", "BLOCKING", "IMPORTANT", "NORMAL", "BLOCKED", "DONE")
_IMPORTANCE_RANK = {"critical": 0, "high": 1, "normal": 2, "low": 3}
NOW_ENV = "MACF_ROLES_NOW"   # test seam: freeze the clock for a CLI invocation


def now() -> datetime:
    """The clock every tier reads. ``MACF_ROLES_NOW`` pins it for tests."""
    frozen = os.environ.get(NOW_ENV)
    if frozen:
        return datetime.fromisoformat(frozen)
    return datetime.now()


# ---- occurrences ---------------------------------------------------------------

def _first_on_or_after(cad: Cadence, day: date) -> Optional[date]:
    """The first calendar day on/after *day* the cadence fires on."""
    if cad.kind == "daily":
        return day
    if cad.kind == "weekly":
        for i in range(7):
            d = day + timedelta(days=i)
            if d.weekday() in cad.weekdays:
                return d
        return None
    if cad.kind == "monthly":
        y, m = day.year, day.month
        for _ in range(13):
            try:
                d = date(y, m, cad.day_of_month)
            except ValueError:
                d = None       # e.g. the 31st in a 30-day month: skipped
            if d is not None and d >= day:
                return d
            m += 1
            if m == 13:
                m, y = 1, y + 1
        return None
    return None


def declared_on(duty: Duty) -> Optional[date]:
    """The day the duty was declared: its first update. Nothing recurs before it.

    A record with no updates, or a first update whose timestamp does not parse,
    has no floor; the second case is said on stderr because it means a
    hand-edited file, and occurrences will then reach back before the duty.
    """
    if not duty.updates:
        return None
    try:
        return datetime.fromisoformat(duty.updates[0].at).date()
    except ValueError as e:
        print(f"⚠️ MACF: duty {duty.id} first update has an unparseable timestamp "
              f"{duty.updates[0].at!r}; no declaration floor ({e})", file=sys.stderr)
        return None


def end_of_day(dt: datetime) -> datetime:
    """A due given as a bare date means 'during that day': it is late only once
    the day is over. A due with a time means that time."""
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        return dt + timedelta(days=1) - timedelta(seconds=1)
    return dt


def occurrences(duty: Duty, start: date, end: date, role_expires: Optional[date] = None) -> List[datetime]:
    """Every occurrence of a cadence duty in [start, end], honouring until/expires
    and never before the duty was declared.

    Walks day by day, which is cheap at the scale of a semester and immune to
    month-length and DST arithmetic: a day is a day.
    """
    if not duty.cadence:
        return []
    cad = parse_cadence(duty.cadence)
    limit = cad.until or role_expires
    if limit is not None:
        end = min(end, limit)
    floor = declared_on(duty)
    if floor is not None and start < floor:
        start = floor
    at = cad.at
    out: List[datetime] = []
    day = start
    while day <= end:
        nxt = _first_on_or_after(cad, day)
        if nxt is None or nxt > end:
            break
        out.append(datetime.combine(nxt, at) if at else datetime.combine(nxt, datetime.min.time()))
        day = nxt + timedelta(days=1)
    return out


def current_occurrence(duty: Duty, at: datetime, role_expires: Optional[date] = None) -> Optional[datetime]:
    """The one occurrence that ranks.

    Dated duty: its ``due``. Cadence duty: the most recent occurrence at or
    before *at* if no ``done_on`` note closed it (it stays OVERDUE until the
    next occurrence arrives, and then becomes a missed cell in the calendar
    rather than a second overdue -- past misses do not accumulate); otherwise
    the next occurrence after *at*.
    """
    if duty.due is not None:
        return duty.due
    if not duty.cadence:
        return None
    done = set(duty.done_on_dates())
    lookback = at.date() - timedelta(days=62)
    past = [o for o in occurrences(duty, lookback, at.date(), role_expires) if end_of_day(o) <= at]
    if past:
        last = past[-1]
        if last.date() not in done:
            return last
    future = occurrences(duty, at.date(), at.date() + timedelta(days=400), role_expires)
    for o in future:
        if end_of_day(o) > at and o.date() not in done:
            return o
    return None


# ---- classification ------------------------------------------------------------

@dataclass
class Placement:
    duty: Duty
    tier: int
    reason: str
    occurrence: Optional[datetime]
    entered: Optional[datetime]        # when the duty entered OVERDUE/DUE_SOON, else None
    key: tuple

    @property
    def tier_name(self) -> str:
        return TIER_NAMES[self.tier]

    @property
    def due_now(self) -> bool:
        return self.tier in (OVERDUE, DUE_SOON)


def _last_serviced_ts(duty: Duty) -> str:
    u = duty.last_serviced()
    return u.at if u else ""


def _horizon_delta(duty: Duty) -> Optional[timedelta]:
    m = duty.horizon_minutes()
    return timedelta(minutes=m) if m is not None else None


def classify(duty: Duty, open_duties: Sequence[Duty], at: Optional[datetime] = None,
             role_expires: Optional[date] = None) -> Placement:
    """Place one duty in the first tier whose test it passes."""
    at = at or now()
    occ = current_occurrence(duty, at, role_expires)
    last = _last_serviced_ts(duty)
    imp = _IMPORTANCE_RANK.get(duty.importance, 2)
    far = datetime.max
    # Ties end on the title so the order is deterministic when everything
    # else -- due, importance, last serviced to the second -- is equal.
    tie = (occ or far, imp, last, duty.title.lower())

    if duty.state in ("done", "deferred"):
        return Placement(duty, DONE, f"{duty.state}", occ, None, (DONE, 0) + tie)

    if occ is not None:
        # A bare date is due 'during that day': late once the day ends, and
        # the horizon opens measured from the start of that day. A due with a
        # time uses the time for both.
        hz = _horizon_delta(duty) or timedelta(0)
        late_after = end_of_day(occ)
        shown = occ.strftime("%Y-%m-%d") if late_after != occ else occ.strftime("%Y-%m-%d %H:%M")
        if late_after < at:
            days = (at.date() - occ.date()).days
            return Placement(duty, OVERDUE, f"due {shown}, {days}d past", occ, late_after,
                             (OVERDUE, 0) + tie)
        entered = occ - hz
        if at >= entered:
            left = (occ.date() - at.date()).days
            return Placement(duty, DUE_SOON,
                             f"due {shown}, horizon {duty.horizon}, entered {entered:%Y-%m-%d %H:%M}, {left}d left",
                             occ, entered, (DUE_SOON, 0) + tie)

    # A blocked duty cannot be worked on, so it never surfaces above a runnable
    # one: BLOCKING, IMPORTANT and NORMAL all require 'not itself blocked'. Its
    # blocker is the one that ranks (as BLOCKING), which is where the work is.
    open_ids = {d.id for d in open_duties}
    blockers = [b for b in duty.depends_on if b in open_ids]
    if blockers:
        return Placement(duty, BLOCKED, f"waits on open dut{'y' if len(blockers) == 1 else 'ies'}: {', '.join(blockers)}",
                         occ, None, (BLOCKED, 0) + tie)

    dependents = [d.id for d in open_duties if duty.id in d.depends_on and d.id != duty.id]
    if dependents:
        return Placement(duty, BLOCKING, f"{len(dependents)} open dut{'y' if len(dependents) == 1 else 'ies'} depend on this: {', '.join(dependents)}",
                         occ, None, (BLOCKING, -len(dependents)) + tie)

    if duty.importance in ("critical", "high"):
        return Placement(duty, IMPORTANT, f"importance {duty.importance}", occ, None, (IMPORTANT, imp) + tie)

    # NORMAL is staleness-ordered (least recently serviced first), then the
    # ordinary ties: a nearer occurrence, importance, title.
    return Placement(duty, NORMAL, f"no due date or dependency; last serviced {last or 'never'}", occ, None,
                     (NORMAL, 0, last, occ or far, imp, duty.title.lower()))


def rank(duties: Iterable[Duty], at: Optional[datetime] = None, role_expires: Optional[date] = None,
         include_done: bool = False) -> List[Placement]:
    """Every duty placed and sorted, open ones first by tier."""
    duties = list(duties)
    open_duties = [d for d in duties if d.state in ("pending", "active")]
    placed = [classify(d, open_duties, at, role_expires) for d in duties]
    if not include_done:
        placed = [p for p in placed if p.tier != DONE]
    return sorted(placed, key=lambda p: p.key)


# ---- the ramp ------------------------------------------------------------------

def approach_mark(occ: Optional[datetime], horizon_minutes: Optional[int], at: Optional[datetime] = None) -> str:
    """none / ⏳Nd / ⏰ today / 🔴 OVERDUE Nd, from one due time and one horizon."""
    if occ is None:
        return ""
    at = at or now()
    if end_of_day(occ) < at:
        past = (at.date() - occ.date()).days
        return f"🔴 OVERDUE {past}d" if past else "🔴 OVERDUE today"
    if occ.date() == at.date():
        return "⏰ today"
    if horizon_minutes is None:
        return ""
    if at >= occ - timedelta(minutes=horizon_minutes):
        return f"⏳{(occ.date() - at.date()).days}d"
    return ""


def duty_mark(p: Placement, at: Optional[datetime] = None) -> str:
    if p.tier == DONE:
        return ""
    return approach_mark(p.occurrence, p.duty.horizon_minutes(), at)


_MARK_URGENCY = {"🔴": 0, "⏰": 1, "⏳": 2}


def most_urgent_mark(marks: Iterable[str]) -> str:
    """The role line shows the most urgent of its duties' marks."""
    best, best_key = "", (9, 0)
    for m in marks:
        if not m:
            continue
        head = m[0]
        # Within a family: more days OVERDUE is worse; fewer days ⏳ is worse.
        try:
            n = int("".join(ch for ch in m if ch.isdigit()) or 0)
        except ValueError:
            n = 0
        key = (_MARK_URGENCY.get(head, 9), -n if head == "🔴" else n)
        if key < best_key:
            best, best_key = m, key
    return best


def review_mark(role: Role, at: Optional[datetime] = None) -> str:
    if role.review_by is None or role.review_horizon is None:
        return ""
    from .cadence import parse_horizon_minutes
    occ = datetime.combine(role.review_by, datetime.min.time())
    return approach_mark(occ, parse_horizon_minutes(role.review_horizon), at)


# ---- roles among themselves ----------------------------------------------------

def rank_roles(pairs: Sequence[Tuple[Role, List[Duty]]], focused_id: Optional[str] = None,
               at: Optional[datetime] = None) -> List[Tuple[Role, List[Placement]]]:
    """Focused first, then most-urgent duty tier, then review proximity, then last serviced."""
    at = at or now()
    rows = []
    for role, duties in pairs:
        placed = rank(duties, at, role.expires)
        top = placed[0].key if placed else (DONE + 1,)
        review = (datetime.combine(role.review_by, datetime.min.time()) - at) if role.review_by else timedelta.max
        last = role.updates[-1].at if role.updates else ""
        rows.append(((0 if role.id == focused_id else 1, top, review, last), role, placed))
    rows.sort(key=lambda r: r[0])
    return [(r, p) for _, r, p in rows]


def why(p: Placement) -> str:
    return f"{p.tier_name:<10} {p.reason}"
