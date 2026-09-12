"""The cadence grammar from the roles policy, parsed and validated.

    daily
    weekly:<day>[,<day>...]          weekly:tue     weekly:tue,thu
    monthly:<day-of-month>           monthly:15
    [at HH:MM] [dur <N>h|<N>m] [until YYYY-MM-DD]

Parsing lives here so ``duty add`` can refuse a malformed cadence at entry
(the validator is where a bad value should be discovered, per the Python
standards) and so the calendar can expand occurrences from a structure rather
than re-reading the string. Expansion itself is the calendar's job.
"""
import re
from dataclasses import dataclass, field
from datetime import date, time
from typing import List, Optional

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_DUR_RE = re.compile(r"^(\d+)([hm])$")
_HORIZON_RE = re.compile(r"^(\d+)([dhm])$")


class CadenceError(ValueError):
    """A cadence string that does not follow the policy grammar."""


@dataclass
class Cadence:
    kind: str                              # daily | weekly | monthly
    weekdays: List[int] = field(default_factory=list)   # 0=mon .. 6=sun
    day_of_month: Optional[int] = None
    at: Optional[time] = None
    duration_minutes: Optional[int] = None
    until: Optional[date] = None
    text: str = ""

    def __str__(self) -> str:
        return self.text


def parse_horizon_minutes(text: str) -> int:
    """``3d`` / ``36h`` / ``90m`` → minutes. Refuses anything else."""
    m = _HORIZON_RE.match((text or "").strip().lower())
    if not m:
        raise CadenceError(f"horizon must look like 3d, 36h or 90m, not {text!r}")
    n, unit = int(m.group(1)), m.group(2)
    if n <= 0:
        raise CadenceError("horizon must be positive")
    return n * {"d": 1440, "h": 60, "m": 1}[unit]


def parse_cadence(text: str) -> Cadence:
    """Parse one cadence string; every failure names the offending token."""
    raw = (text or "").strip()
    if not raw:
        raise CadenceError("cadence is empty")
    tokens = raw.split()
    head, rest = tokens[0].lower(), tokens[1:]
    cad = Cadence(kind="", text=raw)

    if head == "daily":
        cad.kind = "daily"
    elif head.startswith("weekly:"):
        cad.kind = "weekly"
        names = [d.strip().lower() for d in head[len("weekly:"):].split(",") if d.strip()]
        if not names:
            raise CadenceError("weekly needs at least one day: weekly:tue")
        for d in names:
            if d not in DAYS:
                raise CadenceError(f"unknown weekday {d!r}; use {', '.join(DAYS)}")
        cad.weekdays = sorted({DAYS.index(d) for d in names})
    elif head.startswith("monthly:"):
        cad.kind = "monthly"
        body = head[len("monthly:"):]
        if not body.isdigit() or not 1 <= int(body) <= 31:
            raise CadenceError("monthly needs a day of month 1-31: monthly:15")
        cad.day_of_month = int(body)
    else:
        raise CadenceError(f"cadence must start with daily, weekly:<day> or monthly:<n>, not {tokens[0]!r}")

    i = 0
    while i < len(rest):
        key = rest[i].lower()
        val = rest[i + 1] if i + 1 < len(rest) else None
        if key == "at":
            if not val:
                raise CadenceError("'at' needs HH:MM")
            try:
                hh, mm = val.split(":")
                cad.at = time(int(hh), int(mm))
            except (ValueError, TypeError):
                raise CadenceError(f"'at' needs HH:MM, not {val!r}") from None
        elif key == "dur":
            m = _DUR_RE.match((val or "").lower())
            if not m:
                raise CadenceError(f"'dur' needs <N>h or <N>m, not {val!r}")
            cad.duration_minutes = int(m.group(1)) * (60 if m.group(2) == "h" else 1)
        elif key == "until":
            try:
                cad.until = date.fromisoformat(val or "")
            except ValueError:
                raise CadenceError(f"'until' needs YYYY-MM-DD, not {val!r}") from None
        else:
            raise CadenceError(f"unexpected token {rest[i]!r} in cadence")
        i += 2
    return cad
