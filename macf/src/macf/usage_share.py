"""
An agent's share of the account's weekly counter.

The account reports one whole-percent counter for everyone on the login. The usage meter knows this
agent's own weighted tokens. This agent's points are its own tokens times a rate, and the rate is a
**frozen calibration**: computed once by ``budget calibrate``, stored as a ``usage_rate_calibrated``
event, and read from there by everything that converts tokens to points. Nothing on the hook or Stop
path recomputes it from current hours, so what other agents on the account do this hour cannot move
this agent's figure (#1176).

Calibration, the lower envelope:

- The counter's change over a window is this agent's points plus everyone else's, and everyone
  else's is never negative. So for a window W, ``rate * x_W <= delta_W + 1``, where ``x_W`` is this
  agent's weighted tokens in W, ``delta_W`` the counter's change over it and the 1 the whole-percent
  step. Each window gives an upper bound ``(delta_W + 1) / x_W``, and the calibrated rate is the
  smallest of them. Other agents' use can only raise a window's bound, never lower it, so a busy
  hour from someone else loosens that window and is simply not the one chosen.
- Windows are 1 to ``MAX_WINDOW_H`` consecutive whole hours in the last ``LOOKBACK_DAYS`` days. The
  counter at a boundary is the newest ``weekly_all`` sample at or before it, if under an hour old; a
  window needs one at both ends. A window holding a weekly reset (the counter falls at a usable
  boundary inside it, or the two ends name different reset times) is skipped.
- Step windows are considered too: from a step-up sample (the first reading of a new value) to the
  sample just before a later step-up, at the samples' own times, spans of 1 to ``MAX_WINDOW_H``
  hours. The bound has the same form, since every reading ``v`` means ``v <= C < v + 1``, but at these
  ends the counter has just passed its start reading and is just short of its end reading plus one,
  so the ``+ 1`` is nearly all real movement. No margin for movement inside a sample gap is needed,
  so none is assumed. Any fall of the counter between the ends breaks a step window, with or without
  reset times on the samples. The calibration takes the minimum over both sets and records the window
  ``kind`` (``hour`` or ``step``) that set it.
- A bound at or below zero is refused and named, never chosen; with no positive bound there is no
  calibration. The tightest window not overlapping the chosen one is reported and recorded as
  ``runner_up``, and ``budget calibrate`` refuses to record a rate more than ``SANITY_FACTOR`` from the
  provisional constant either way.
- ``me`` is therefore an upper bound on this agent's points, and ``budget me`` says so.
- ``x_W`` spreads each metered event's tokens over its calls' span (``usage_meter.fraction_in``) and
  weighs cache reads at ``READ_WEIGHT``. A window needs ``MIN_WINDOW_TOKENS`` to count.
- The event records the rate, the read weight, the method, the window that set it and how many were
  considered. With no calibration yet the provisional constant stands in, marked ``~``.

Finding the newest calibration without walking the log: each ``usage_rolled`` event carries the
calibration in force when it was written, so ``calibration`` reads back to whichever of the two
comes first, which on an active seat is within a minute of events.

The account's own movement is kept only as a sanity mark. When this agent's points over a window
exceed what the account moved plus 1, the figure is shown as it is, marked ``!`` on the hook line,
and ``budget me`` explains it. Within ``LOOSE_WITHIN_H`` hours of a calibration it says the calibrated
bound is loose for this hour (an upper bound, tightened by recalibrating after heavy hours); after that
it says the calibration looks stale and names ``budget calibrate``. Nothing is capped.
"""

import datetime as dt
import math
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from macf import usage_meter
from macf.agent_events_log import append_event, read_events

CALIBRATION_EVENT = "usage_rate_calibrated"
METHOD = "lower_envelope"
HOUR = 3600.0
LOOKBACK_DAYS = 14
MAX_WINDOW_H = 12
#: The cache-read weight, relative to an uncached input token. A constant, not fitted each time: a
#: grid fit on spread data on 2026-11-28 chose 0.1 over 48h and 96h windows (0 over 168h, so the
#: error surface is nearly flat there), and 0.1 is also the price list's ratio.
READ_WEIGHT = 0.1
#: A window counts only with at least this many of this agent's weighted tokens. Its bound is then
#: at least 1/x, about 25 times the provisional rate, so the floor never decides the minimum: it keeps
#: windows in which this agent was idle out of the count. It is kept low on purpose, since a higher one
#: drops real windows (on 2026-11-28 a floor of one provisional point, 2.5e7, dropped the tightest).
MIN_WINDOW_TOKENS = 1e6
#: The counter moves in whole percents: its measured rise can understate the account's use by this.
GAUGE_STEP = 1.0
STALE_MARK = "!"
#: Within this many hours of a calibration, me above the account + 1 means the bound is loose for that
#: hour, not that the calibration has gone stale: it is an upper bound from the start.
LOOSE_WITHIN_H = 6.0
HOUR_WINDOW = "hour"  # a window of whole hours, its ends read from the newest sample at each boundary
STEP_WINDOW = "step"  # a window from a step-up sample to the sample before a later step-up
PROVISIONAL = "provisional"
CALIBRATED = "calibrated"


@dataclass(frozen=True, kw_only=True)
class Calibration:
    rate: float  # points per weighted token
    read_weight: float
    at: float  # when it was computed
    method: str = METHOD
    windows: int = 0  # windows considered
    window: Optional[dict] = None  # the window that set it: start, end, hours, delta, tokens
    lookback_days: float = LOOKBACK_DAYS
    #: the tightest window not overlapping ``window``, with its ``rate``: a check on whether the minimum
    #: went to one window's measurement error. None when every other window overlaps it.
    runner_up: Optional[dict] = None


@dataclass(frozen=True, kw_only=True)
class CalibrationAttempt:
    calibration: Optional[Calibration]
    reason: Optional[str] = None  # set when there is none
    refused: tuple = ()  # windows whose bound was at or below zero, each with its ``bound``


@dataclass(frozen=True, kw_only=True)
class Share:
    window_h: float
    weighted_tokens: float
    rate: float
    rate_source: str  # "calibrated" or "provisional"
    points: float
    account: Optional[float]  # None when the account's movement is unknown
    remainder: Optional[float]
    read_weight: Optional[float] = None  # the calibration's; None is the price list's
    stale: bool = False  # points exceed the account's movement plus GAUGE_STEP


def is_stale(points: float, account: Optional[float]) -> bool:
    """Whether ``points`` are more than the account moved plus the counter's step; False unknown."""
    return account is not None and points > account + GAUGE_STEP


def _event_weighted(ev: dict, read_weight: Optional[float] = None) -> float:
    return sum(usage_meter.weighted(row, read_weight)
               for row in ((ev.get("data") or {}).get("by_model") or {}).values())


def _reset_time(value) -> Optional[float]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError as e:
        print(f"⚠️ MACF: usage share: unreadable reset time {value!r} ({e})", file=sys.stderr)
        return None


def _weekly_points(since: float, now: float) -> List[dict]:
    """``weekly_all`` samples, oldest first, as ``{t, pct, reset}``."""
    from macf import budget
    out = []
    for s in budget.samples(since=since, now=now):
        w = next((l for l in s["limits"] if l.get("kind") == "weekly_all"), None)
        if w is not None and w.get("percent") is not None:
            out.append({"t": s["t"], "pct": float(w["percent"]), "reset": _reset_time(w.get("resets_at"))})
    return out


def _point_at(points: List[dict], t: float) -> Optional[dict]:
    """The newest sample at or before ``t``, if under an hour old at ``t``."""
    best = None
    for p in points:
        if p["t"] <= t:
            best = p
        else:
            break
    return best if best is not None and t - best["t"] < HOUR else None


# ── the calibration ───────────────────────────────────────────────────────────

def _hour_tokens(start: float, hours: int) -> List[float]:
    """This agent's weighted tokens per whole hour from ``start``, each event spread over its span."""
    end = start + hours * HOUR
    xs = [0.0] * hours
    for ev in read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=start - HOUR):
        first, last = usage_meter.event_span(ev)
        if last < start or first >= end:
            continue
        w = _event_weighted(ev, READ_WEIGHT)
        for k in range(max(0, int((first - start) // HOUR)), min(hours, int((last - start) // HOUR) + 1)):
            xs[k] += usage_meter.fraction_in(ev, start + k * HOUR, start + (k + 1) * HOUR) * w
    return xs


def _same_week(a: dict, b: dict) -> bool:
    return a["reset"] is None or b["reset"] is None or abs(a["reset"] - b["reset"]) < HOUR


@dataclass(frozen=True, kw_only=True)
class _Windows:
    """The windows one set considered, each a dict with its ``bound``. ``envelope`` chooses among them
    and refuses any bound at or below zero; ``bound`` and ``window`` here are the raw minimum."""
    windows: tuple = ()

    @property
    def considered(self) -> int:
        return len(self.windows)

    @property
    def window(self) -> Optional[dict]:
        return min(self.windows, key=lambda w: w["bound"], default=None)

    @property
    def bound(self) -> Optional[float]:
        w = self.window
        return None if w is None else w["bound"]


def _gap_tokens(times: List[float]) -> List[float]:
    """This agent's weighted tokens in each gap ``[times[k], times[k+1])`` between samples, each event
    spread over its span. One read of the log for all the gaps."""
    import bisect
    xs = [0.0] * max(0, len(times) - 1)
    if not xs:
        return xs
    lo, hi = times[0], times[-1]
    for ev in read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=lo - HOUR):
        first, last = usage_meter.event_span(ev)
        if last < lo or first >= hi:
            continue
        w = _event_weighted(ev, READ_WEIGHT)
        k0 = max(0, bisect.bisect_right(times, first) - 1)
        k1 = min(len(xs) - 1, bisect.bisect_right(times, last) - 1)
        for k in range(k0, k1 + 1):
            xs[k] += usage_meter.fraction_in(ev, times[k], times[k + 1]) * w
    return xs


def _step_windows(start: float, now: float) -> _Windows:
    """The smallest bound over windows from a step-up sample to the sample just before a later step-up.

    Every sample bounds the true counter ``C`` from both sides: a reading ``v`` means ``v <= C < v + 1``.
    So between any two samples ``C`` rose by less than ``v_end + 1 - v_start``, the hour windows'
    formula. What changes is where the ends sit. At a step-up sample (the first reading of ``N`` after
    a lower one) ``C`` has only just passed ``N``; at the sample before a step-up ``C`` is just short
    of ``v_end + 1``. There the ``+ 1`` is almost all real movement instead of rounding. Among windows
    sharing their two readings, these ends also hold the most tokens, so they set the tightest bound
    any pair of samples can give. No margin is needed and none is assumed: the bound holds however the
    account moved inside a sample gap. Spans of 1 to ``MAX_WINDOW_H`` hours.

    Any fall of the counter between the two ends breaks the window, as in the hour windows, whatever the
    samples say about reset times: a stale low reading or a weekly reset whose samples carry no
    ``resets_at`` would otherwise end a window below its start and give a bound at or below zero. A
    change of reset time between the ends breaks it too."""
    pts = [p for p in _weekly_points(start, now) if p["t"] >= start]
    n = len(pts)
    if n < 3:
        return _Windows()
    times = [p["t"] for p in pts]
    cum = [0.0]
    for x in _gap_tokens(times):
        cum.append(cum[-1] + x)
    week = [0] * n  # a new segment at every fall of the counter or change of reset time
    for k in range(1, n):
        broken = pts[k]["pct"] < pts[k - 1]["pct"] or not _same_week(pts[k - 1], pts[k])
        week[k] = week[k - 1] + (1 if broken else 0)
    ups = [k for k in range(1, n) if pts[k]["pct"] > pts[k - 1]["pct"]]
    befores = [k for k in range(n - 1) if pts[k + 1]["pct"] > pts[k]["pct"]]
    out = []
    for i in ups:
        for j in befores:
            span = times[j] - times[i]
            if span < HOUR:
                continue
            if span > MAX_WINDOW_H * HOUR:
                break
            if week[j] != week[i] or not _same_week(pts[i], pts[j]):
                continue
            x = cum[j] - cum[i]
            if x < MIN_WINDOW_TOKENS:
                continue
            delta = pts[j]["pct"] - pts[i]["pct"]
            out.append({"kind": STEP_WINDOW, "start": times[i], "end": times[j], "hours": span / HOUR,
                        "delta": delta, "tokens": x, "bound": (delta + GAUGE_STEP) / x})
    return _Windows(windows=tuple(out))


def envelope(now: float, lookback_days: float = LOOKBACK_DAYS) -> CalibrationAttempt:
    """The smallest ``(delta_W + 1) / x_W`` over the windows of the last ``lookback_days``: the whole-hour
    windows and the step windows (``_step_windows``), so adding the second set can only tighten it."""
    end = math.floor(now / HOUR) * HOUR
    hours = int(round(lookback_days * 24))
    start = end - hours * HOUR
    windows = list(_hour_windows(start, hours, now).windows) + list(_step_windows(start, now).windows)
    # A second line of defence behind the windows' own reset checks: a bound at or below zero is never
    # a measurement (the counter fell inside the window), so it is refused and named, never chosen.
    usable = [w for w in windows if w["bound"] > 0]
    refused = tuple(w for w in windows if not w["bound"] > 0)
    if not windows:
        return CalibrationAttempt(calibration=None, reason=(
            f"no window of 1 to {MAX_WINDOW_H}h in the last {lookback_days:g} days has a counter at both "
            f"ends and {MIN_WINDOW_TOKENS:.3g} weighted tokens"))
    if not usable:
        return CalibrationAttempt(calibration=None, refused=refused, reason=(
            f"all {len(windows)} windows have a bound at or below zero, which is never a measurement "
            f"(the counter fell inside them: a stale reading or an unmarked reset)"))
    pick = min(usable, key=lambda w: w["bound"])  # ties go to the hour windows, listed first
    apart = [w for w in usable if w["end"] <= pick["start"] or w["start"] >= pick["end"]]
    runner = min(apart, key=lambda w: w["bound"], default=None)
    return CalibrationAttempt(refused=refused, calibration=Calibration(
        rate=pick["bound"], read_weight=READ_WEIGHT, at=now, windows=len(windows), window=_bare(pick),
        lookback_days=lookback_days, runner_up=None if runner is None else {**_bare(runner), "rate": runner["bound"]}))


def _bare(w: dict) -> dict:
    return {k: v for k, v in w.items() if k != "bound"}


def _hour_windows(start: float, hours: int, now: float) -> _Windows:
    """The windows of 1 to ``MAX_WINDOW_H`` whole hours from ``start``, each with its bound."""
    pts = _weekly_points(start - HOUR, now)
    bounds = [_point_at(pts, start + k * HOUR) for k in range(hours + 1)]
    xs = _hour_tokens(start, hours)
    out = []
    for i in range(hours):
        a = bounds[i]
        if a is None:
            continue
        x, prev = 0.0, a
        for j in range(i + 1, min(hours, i + MAX_WINDOW_H) + 1):
            x += xs[j - 1]
            b = bounds[j]
            if b is None:
                continue
            if b["pct"] < prev["pct"] or not _same_week(a, b):
                break  # a weekly reset: this window and every longer one from i hold it
            prev = b
            if x < MIN_WINDOW_TOKENS:
                continue
            delta = b["pct"] - a["pct"]
            out.append({"kind": HOUR_WINDOW, "start": start + i * HOUR, "end": start + j * HOUR,
                        "hours": j - i, "delta": delta, "tokens": x, "bound": (delta + GAUGE_STEP) / x})
    return _Windows(windows=tuple(out))


def _calibration_data(c: Calibration) -> dict:
    return {"rate": c.rate, "read_weight": c.read_weight, "method": c.method, "at": c.at,
            "windows": c.windows, "window": c.window, "lookback_days": c.lookback_days,
            "runner_up": c.runner_up}


def record_calibration(c: Calibration, refused: tuple = ()) -> None:
    append_event(CALIBRATION_EVENT, {**_calibration_data(c), "refused": [_bare(w) for w in refused]})


def _calibration_from(d) -> Optional[Calibration]:
    if not d:
        return None
    try:
        return Calibration(rate=float(d["rate"]), read_weight=float(d["read_weight"]), at=float(d["at"]),
                           method=str(d.get("method", METHOD)), windows=int(d.get("windows", 0)),
                           window=d.get("window"), lookback_days=float(d.get("lookback_days", LOOKBACK_DAYS)),
                           runner_up=d.get("runner_up"))
    except (KeyError, TypeError, ValueError) as e:
        print(f"⚠️ MACF: usage share: unreadable calibration ({e}); using the provisional rate", file=sys.stderr)
        return None


def calibration(now: Optional[float] = None) -> Optional[Calibration]:
    """The newest calibration at ``now``, or None. Stops at the first calibration event or rolled event
    (which carries the calibration in force when it was written), whichever is newer."""
    now = now or time.time()
    for ev in read_events(reverse=True, scope="all", only=(CALIBRATION_EVENT, ROLLED_EVENT)):
        if ev.get("timestamp", 0) > now:
            continue
        d = ev.get("data") or {}
        return _calibration_from(d if ev.get("event") == CALIBRATION_EVENT else d.get("calibration"))
    return None


# ── the share ─────────────────────────────────────────────────────────────────

def _account_movement(window_h: float, now: float) -> Optional[float]:
    """Rise of the weekly counter over the window: the sum of its non-negative steps, which
    skips a weekly reset. None with fewer than two samples."""
    start = now - window_h * HOUR
    pts = _weekly_points(start - HOUR, now)
    inside = [p for p in pts if p["t"] >= start]
    before = [p for p in pts if p["t"] < start]
    chain = ([before[-1]] if before else []) + inside
    if len(chain) < 2:
        return None
    return sum(max(0.0, b["pct"] - a["pct"]) for a, b in zip(chain, chain[1:]))


@dataclass(frozen=True, kw_only=True)
class RateInUse:
    rate: float
    read_weight: Optional[float]  # None is the price list's
    source: str  # CALIBRATED or PROVISIONAL


def _rate_of(cal: Optional[Calibration]) -> RateInUse:
    """The calibration's rate and read weight, else the provisional constant's."""
    if cal is not None:
        return RateInUse(rate=cal.rate, read_weight=cal.read_weight, source=CALIBRATED)
    return RateInUse(rate=usage_meter.POINTS_PER_WEIGHTED_TOKEN, read_weight=None, source=PROVISIONAL)


def share(window_h: float = 24.0, now: Optional[float] = None, cal: Optional[Calibration] = None) -> Share:
    """This agent's points over the last ``window_h`` hours: its own tokens times the newest calibration
    (``cal`` overrides it), set against the account's movement. The remainder is what others and
    unmetered use spent; it is None, not zero, when the account's movement is unknown."""
    now = now or time.time()
    r = _rate_of(cal if cal is not None else calibration(now))
    rate, rw, source = r.rate, r.read_weight, r.source
    begin = now - window_h * HOUR
    wt = 0.0
    for ev in read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=begin - HOUR):
        f = usage_meter.fraction_in(ev, begin, now)
        if f > 0:
            wt += f * _event_weighted(ev, rw)
    account = _account_movement(window_h, now)
    points = wt * rate
    return Share(window_h=window_h, weighted_tokens=wt, rate=rate, rate_source=source, points=points,
                 account=account, remainder=None if account is None else account - points,
                 read_weight=rw, stale=is_stale(points, account))


# ── views ─────────────────────────────────────────────────────────────────────

def _when(t: float) -> str:
    return dt.datetime.fromtimestamp(t).astimezone().isoformat(timespec="minutes")


#: budget calibrate refuses a rate more than this factor from the provisional constant, either way.
SANITY_FACTOR = 4.0
REFUSED_SHOWN = 3  # refused windows named one by one; the rest are counted


def band_refusal(rate: float) -> Optional[str]:
    """Why ``rate`` is outside ``SANITY_FACTOR`` of the provisional constant, or None inside it."""
    ratio = rate / usage_meter.POINTS_PER_WEIGHTED_TOKEN
    if 1 / SANITY_FACTOR <= ratio <= SANITY_FACTOR:
        return None
    return (f"the rate is {ratio:.3g}x the provisional {usage_meter.POINTS_PER_WEIGHTED_TOKEN:.3g}, outside a "
            f"factor of {SANITY_FACTOR:g}: more likely a meter fault or one window's tokens over-counted than "
            f"a measurement")


def _window_line(w: dict) -> str:
    return (f"a {w.get('kind', HOUR_WINDOW)} window, {_when(w['start'])} to {_when(w['end'])}"
            f" ({w['hours']:.3g}h): account {w['delta']:+g}, {w['tokens']:.3g} weighted tokens")


def _refused_lines(refused: tuple) -> List[str]:
    if not refused:
        return []
    lines = [f"  refused {len(refused)} window(s) with a bound at or below zero (never a measurement):"]
    lines += [f"    {_window_line(w)}" for w in refused[:REFUSED_SHOWN]]
    if len(refused) > REFUSED_SHOWN:
        lines.append(f"    and {len(refused) - REFUSED_SHOWN} more")
    return lines


def format_calibration(att: CalibrationAttempt, recorded: bool, dry_run: bool = True) -> str:
    if att.calibration is None:
        return "\n".join([f"no calibration: {att.reason}", *_refused_lines(att.refused),
                          f"provisional rate {usage_meter.POINTS_PER_WEIGHTED_TOKEN:.3g} points/weighted token stands"])
    c, w, r = att.calibration, att.calibration.window, att.calibration.runner_up
    band = band_refusal(c.rate)
    if recorded:
        last = f"recorded as {CALIBRATION_EVENT}"
    elif band is None:
        last = "dry run: nothing recorded"
    else:
        head = "dry run: nothing recorded; a real run would be refused" if dry_run else "refused, nothing recorded"
        last = f"{head}: {band}"
    return "\n".join([
        f"calibrated rate {c.rate:.3g} points/weighted token (lower envelope)",
        (f"  set by a {w.get('kind', HOUR_WINDOW)} window, {_when(w['start'])} to {_when(w['end'])}"
         f" ({w['hours']:.3g}h):"),
        f"    account +{w['delta']:g}, {w['tokens']:.3g} weighted tokens",
        *([f"  next tightest window not overlapping it: rate {r['rate']:.3g}, {r['rate'] / c.rate:.3g}x the chosen",
           f"    {_window_line(r)}"] if r is not None else ["  no other window that does not overlap it"]),
        (f"  windows considered {c.windows} (whole-hour and step-to-step), last {c.lookback_days:g} days,"
         f" 1 to {MAX_WINDOW_H}h"),
        *_refused_lines(att.refused),
        f"  cache read weight {c.read_weight:g}",
        (f"  {c.rate / usage_meter.POINTS_PER_WEIGHTED_TOKEN:.3g}x the provisional rate"
         f" {usage_meter.POINTS_PER_WEIGHTED_TOKEN:.3g}: {'outside' if band else 'inside'} the band of"
         f" {SANITY_FACTOR:g}x either way"),
        last,
    ])


def is_loose(cal: Optional[Calibration], now: Optional[float]) -> bool:
    """Whether a ``!`` at ``now`` reads as a loose bound rather than a stale calibration: the
    calibration is under ``LOOSE_WITHIN_H`` hours old."""
    return cal is not None and now is not None and now - cal.at < LOOSE_WITHIN_H * HOUR


#: The calibrated rate is the smallest of upper bounds, so me errs high: seats' figures added together
#: come to more than the account moved.
UPPER_BOUND_LINE = "  me is an upper bound: rate = min of upper bounds"


def format_share(s: Share, cal: Optional[Calibration] = None, now: Optional[float] = None) -> str:
    rate = (f"calibrated {_when(cal.at)}" if cal is not None
            else "calibrated" if s.rate_source == CALIBRATED else "provisional rate")
    lines = [f"share, last {s.window_h:g}h ({rate})",
             f"  me    {STALE_MARK if s.stale else ' '} {s.points:6.2f}"]
    if s.account is None:
        lines += ["  account unknown (too few samples)", "  others  unknown"]
    else:
        lines += [f"  account {s.account:6.2f}", f"  others  {s.remainder:6.2f}"]
        if s.account > 0 and not s.stale:
            lines.append(f"  my share {100 * s.points / s.account:.0f}%")
    if s.rate_source == CALIBRATED:
        lines.append(UPPER_BOUND_LINE)
    if s.stale and is_loose(cal, now):
        lines += [f"  {STALE_MARK} me is above the account + {GAUGE_STEP:g}: the calibrated",
                  "    rate is an upper bound, loose for this hour;",
                  "    recalibrating after heavy hours tightens it"]
    elif s.stale:
        lines += [f"  {STALE_MARK} me is above the account + {GAUGE_STEP:g}: the",
                  "    calibration looks stale; run budget calibrate"]
    if s.read_weight is not None:
        lines.append(f"  cache read weight {s.read_weight:g}")
    lines.append("  others = other agents + unmetered use")
    return "\n".join(lines)


@dataclass(frozen=True, kw_only=True)
class CalibrateOutcome:
    text: str
    recorded: bool
    refused: bool  # a calibration was found and its rate fell outside the sanity band


def calibrate(dry_run: bool = False, now: Optional[float] = None) -> CalibrateOutcome:
    """Find the calibration and record it unless ``dry_run``, or its rate is outside ``SANITY_FACTOR``
    of the provisional constant, which is refused and never recorded."""
    att = envelope(now or time.time())
    refused = att.calibration is not None and band_refusal(att.calibration.rate) is not None
    recorded = att.calibration is not None and not refused and not dry_run
    if recorded:
        record_calibration(att.calibration, att.refused)
    return CalibrateOutcome(text=format_calibration(att, recorded, dry_run), recorded=recorded, refused=refused)


def run_calibrate(dry_run: bool = False, now: Optional[float] = None) -> str:
    return calibrate(dry_run, now).text


def me_lines(window_h: float) -> str:
    """The share block for ``budget me``; reads the newest calibration, never computes one."""
    now = time.time()
    cal = calibration(now)
    return format_share(share(window_h, now=now, cal=cal), cal, now)


# ── hook line ─────────────────────────────────────────────────────────────────

ROLLED_EVENT = "usage_rolled"
ROLL_EVERY_S = 60.0
ROLLED_FRESH_S = 900.0


@dataclass(frozen=True, kw_only=True)
class HourPoints:
    points: float  # this agent's points over the last hour
    calls: int
    rate: float
    calibrated: bool
    partial: bool = False  # metering is under an hour old, or the hour holds under THIN_CALLS calls
    account: Optional[float] = None  # the account's movement over the same hour; None when unknown


#: An hour with fewer metered calls than this is a sample, not a rate.
THIN_CALLS = 3
PARTIAL_MARK = " part"


def _hour_points(now: float, cal: Optional[Calibration] = None) -> HourPoints:
    """Points over the last hour at the newest calibration (``cal`` when given). With no metered
    events in the hour it returns zero points and reads nothing more."""
    metered = list(read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=now - HOUR))
    if not metered:
        return HourPoints(points=0.0, calls=0, rate=0.0, calibrated=False, partial=True)
    r = _rate_of(cal if cal is not None else calibration(now))
    rate, rw, source = r.rate, r.read_weight, r.source
    wt = 0.0
    calls = 0.0
    began: Optional[float] = None
    for ev in metered:
        f = usage_meter.fraction_in(ev, now - HOUR, now)
        wt += f * _event_weighted(ev, rw)
        calls += f * int((ev.get("data") or {}).get("calls") or 0)
        ms = (ev.get("data") or {}).get("metering_since")
        if isinstance(ms, (int, float)) and (began is None or ms < began):
            began = ms
    partial = (began is not None and now - began < HOUR) or calls < THIN_CALLS
    return HourPoints(points=wt * rate, calls=round(calls), rate=rate, calibrated=source == CALIBRATED,
                      partial=partial, account=_account_movement(1.0, now))


def roll(now: Optional[float] = None) -> bool:
    """Record the last hour's points as a ``usage_rolled`` event, at most once a minute, so the hook
    line reads one event instead of an hour. The event carries the calibration it used, which is how
    ``calibration`` finds it without walking back to the calibration event. Returns whether it wrote."""
    now = now or time.time()
    for ev in read_events(reverse=True, scope="all", only=ROLLED_EVENT, since=now - ROLL_EVERY_S):
        return False
    cal = calibration(now)
    h = _hour_points(now, cal)
    append_event(ROLLED_EVENT, {"points_1h": h.points, "calls_1h": h.calls, "rate": h.rate,
                                "calibrated": h.calibrated, "partial": h.partial, "account_1h": h.account,
                                "at": now, "calibration": None if cal is None else _calibration_data(cal)})
    return True


def _newest_rolled(now: float) -> Optional[HourPoints]:
    """The newest ``usage_rolled`` event of the last ``ROLLED_FRESH_S``; stops at the first match."""
    for ev in read_events(reverse=True, scope="all", only=ROLLED_EVENT, since=now - ROLLED_FRESH_S):
        d = ev.get("data") or {}
        try:
            account = d.get("account_1h")
            return HourPoints(points=float(d["points_1h"]), calls=int(d["calls_1h"]), rate=float(d["rate"]),
                              calibrated=bool(d["calibrated"]), partial=bool(d.get("partial", False)),
                              account=None if account is None else float(account))
        except (KeyError, TypeError, ValueError) as e:
            print(f"⚠️ MACF: usage share: unreadable rolled event ({e}); computing the hour instead",
                  file=sys.stderr)
            return None
    return None


def hook_suffix(now: Optional[float] = None) -> Optional[str]:
    """``· me 0.21%/1h``: this agent's points over the last hour, or None with no metered events.

    The window is written out (``/1h``) because the weekly field beside it is a two-hour smoothed
    rate, and the two are not the same measurement. Points above the account's own movement over the
    hour plus ``GAUGE_STEP`` are shown as they are and marked ``!``; ``budget me`` says what it means
    (a loose bound within ``LOOSE_WITHIN_H`` hours of calibrating, a stale calibration after).

    Reads the newest rolled event of the last 15 minutes and stops there. With none that recent
    (ticks are sparse) it computes the hour itself, as ``roll`` does, so the figure stays right.
    A provisional rate is marked ``~``; an hour that is not fully metered (metering under an hour
    old) or is thin (under ``THIN_CALLS`` calls) ends with ``part``, since the figure is then a sample.
    """
    now = now or time.time()
    h = _newest_rolled(now) or _hour_points(now)
    if h.points <= 0:
        return None
    from macf.budget import format_rate
    return (f"· me {STALE_MARK if is_stale(h.points, h.account) else ''}{'' if h.calibrated else '~'}"
            f"{format_rate(h.points)}%/1h{PARTIAL_MARK if h.partial else ''}")
