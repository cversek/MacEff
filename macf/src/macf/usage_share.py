"""
An agent's share of the account's weekly counter.

The account reports one whole-percent counter for everyone on the login. The usage meter
knows this agent's own weighted tokens. Regressing the hourly change of the counter on the
hourly weighted tokens, through the origin, gives points per weighted token; the rest of the
counter's movement belongs to other agents and unmetered use.

Method:

- Hour boundaries are the whole hours inside the window. The counter at a boundary is the
  newest ``weekly_all`` sample at or before it, and only if that sample is under an hour old.
  An hour with a usable counter at both ends is a data point, even when the counter did not
  move: a whole-percent counter is coarse, and a flat hour is evidence about the rate.
- An hour in which the counter fell (a weekly reset) is dropped.
- x is the weighted tokens of the ``usage_metered`` events that fall in the hour (by ``last_ts``,
  else the event's own time); y is the counter's change over the hour.
- The slope is ``sum(xy) / sum(xx)``. Its 90% interval is a percentile bootstrap over hours
  (deterministic seed), chosen over the standard error because the noise is far from constant:
  hours with a lot of other agents' use scatter more than quiet ones. r² is the usual centred
  one, so it can be negative for a poor through-origin fit.
- Through the origin means other agents' use that is steady across hours (a positive mean, not
  tied to this agent's tokens) pushes the slope up a little; the interval does not cover that
  bias, only sampling scatter.
- Only hours with metered tokens count toward ``MIN_HOURS``: an hour with none carries no
  information about the rate. Fewer than that is no fit, and the reason is returned with it.
- A degenerate fit is refused too: a zero-width interval, an r² below zero, or a rate more than
  ``SANE_FACTOR`` (10) times away from the provisional constant either way. The band is wide on
  purpose, since the constant is itself provisional; it only catches a fit resting on one or two
  odd hours. No constant is substituted silently; ``share`` labels the provisional one when it
  has to use it.

The hooks never regress. The Stop hook refreshes the fit at most once an hour (``refresh_fit``),
writing a ``usage_rate_fitted`` event, with ``rate`` null and a reason when there is no fit so the
attempt is not repeated. The hook line reads the last hour of events once, for both kinds, and
uses the provisional rate (marked ``~``) when no fit is in it. Nothing else is stored.
"""

import math
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from macf import usage_meter
from macf.agent_events_log import append_event, read_events

FIT_EVENT = "usage_rate_fitted"
MIN_HOURS = 6
DEFAULT_WINDOW_H = 48.0
BOOTSTRAPS = 400
SANE_FACTOR = 10.0
HOUR = 3600.0
PROVISIONAL = "provisional"
FITTED = "fit"


@dataclass(frozen=True, kw_only=True)
class RateFit:
    rate: float  # points per weighted token
    low: float  # 90% interval
    high: float
    hours: int
    r2: float


@dataclass(frozen=True, kw_only=True)
class FitAttempt:
    fit: Optional[RateFit]
    reason: Optional[str] = None  # set when there is no fit


@dataclass(frozen=True, kw_only=True)
class Share:
    window_h: float
    weighted_tokens: float
    rate: float
    low_rate: float
    high_rate: float
    rate_source: str  # "fit" or "provisional"
    points: float
    points_low: float
    points_high: float
    account: Optional[float]  # None when the account's movement is unknown
    remainder: Optional[float]
    remainder_low: Optional[float]
    remainder_high: Optional[float]


def _event_time(ev: dict) -> float:
    d = ev.get("data") or {}
    stamp = d.get("last_ts")
    if stamp:
        try:
            return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
        except ValueError as e:
            print(f"⚠️ MACF: usage share: unreadable last_ts {stamp!r} ({e}); using the event's time",
                  file=sys.stderr)
    return float(ev.get("timestamp", 0))


def _event_weighted(ev: dict) -> float:
    return sum(usage_meter.weighted(row) for row in ((ev.get("data") or {}).get("by_model") or {}).values())


def _weekly_points(since: float, now: float) -> List[Dict[str, float]]:
    """``weekly_all`` samples, oldest first, as ``{t, pct}``."""
    from macf import budget
    out = []
    for s in budget.samples(since=since, now=now):
        w = next((l for l in s["limits"] if l.get("kind") == "weekly_all"), None)
        if w is not None and w.get("percent") is not None:
            out.append({"t": s["t"], "pct": float(w["percent"])})
    return out


def _percent_at(points: List[Dict[str, float]], t: float) -> Optional[float]:
    """The newest sample at or before ``t``, if under an hour old at ``t``."""
    best = None
    for p in points:
        if p["t"] <= t:
            best = p
        else:
            break
    return best["pct"] if best is not None and t - best["t"] < HOUR else None


def _slope(xs: List[float], ys: List[float]) -> Optional[float]:
    sxx = sum(x * x for x in xs)
    return sum(x * y for x, y in zip(xs, ys)) / sxx if sxx > 0 else None


def _hourly_data(window_h: float, now: float) -> Dict[str, List[float]]:
    end = math.floor(now / HOUR) * HOUR
    start = end - math.ceil(window_h) * HOUR
    pts = _weekly_points(start - HOUR, now)
    tokens: Dict[int, float] = {}
    for ev in read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=start - HOUR):
        t = _event_time(ev)
        if start <= t < end:
            k = int((t - start) // HOUR)
            tokens[k] = tokens.get(k, 0.0) + _event_weighted(ev)
    xs, ys = [], []
    for k in range(int((end - start) // HOUR)):
        a, b = _percent_at(pts, start + k * HOUR), _percent_at(pts, start + (k + 1) * HOUR)
        if a is None or b is None or b < a:
            continue
        xs.append(tokens.get(k, 0.0))
        ys.append(b - a)
    return {"x": xs, "y": ys}


def _interval(slopes: List[float], rate: float) -> tuple:
    """The 5th and 95th percentile of the resampled slopes, widened to include the rate itself."""
    ordered = sorted(slopes)
    low = ordered[int(0.05 * len(ordered))]
    high = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    return min(low, rate), max(high, rate)


def try_fit(window_h: float = DEFAULT_WINDOW_H, now: Optional[float] = None) -> FitAttempt:
    """Fit points per weighted token over the last ``window_h`` hours, or say why not."""
    now = now or time.time()
    data = _hourly_data(window_h, now)
    xs, ys = data["x"], data["y"]
    n = len(xs)
    with_tokens = sum(1 for x in xs if x > 0)
    if with_tokens < MIN_HOURS:
        return FitAttempt(fit=None, reason=f"{with_tokens} hours with metered tokens ({n} usable) in the "
                                           f"last {window_h:g}h, need {MIN_HOURS}")
    rate = _slope(xs, ys)
    if rate is None:
        return FitAttempt(fit=None, reason=f"no metered tokens in the {n} usable hours")
    rng = random.Random(0)
    slopes = []
    for _ in range(BOOTSTRAPS):
        idx = [rng.randrange(n) for _ in range(n)]
        s = _slope([xs[i] for i in idx], [ys[i] for i in idx])
        if s is not None:
            slopes.append(s)
    low, high = _interval(slopes, rate)
    mean_y = sum(ys) / n
    sse = sum((y - rate * x) ** 2 for x, y in zip(xs, ys))
    sst = sum((y - mean_y) ** 2 for y in ys)
    r2 = 1 - sse / sst if sst > 0 else 0.0
    prov = usage_meter.POINTS_PER_WEIGHTED_TOKEN
    if high <= low:
        return FitAttempt(fit=None, reason=f"degenerate fit: zero-width interval over {with_tokens} token hours")
    if r2 < 0:
        return FitAttempt(fit=None, reason=f"degenerate fit: r2 {r2:.2f} is below zero")
    if not prov / SANE_FACTOR <= rate <= prov * SANE_FACTOR:
        return FitAttempt(fit=None, reason=f"degenerate fit: rate {rate:.3g} is over {SANE_FACTOR:g}x "
                                           f"from the provisional {prov:.3g}")
    return FitAttempt(fit=RateFit(rate=rate, low=low, high=high, hours=n, r2=r2))


def fit_rate(window_h: float = DEFAULT_WINDOW_H, now: Optional[float] = None) -> Optional[RateFit]:
    """The fit, or None when there are too few usable hours (``try_fit`` says why)."""
    return try_fit(window_h, now).fit


def record_fit(fit: RateFit, window_h: float) -> None:
    """Cache a fit as an event for the hooks to read."""
    append_event(FIT_EVENT, {"rate": fit.rate, "low": fit.low, "high": fit.high, "hours": fit.hours,
                             "r2": fit.r2, "window_h": window_h})


def _fit_from(ev: dict) -> Optional[RateFit]:
    d = ev.get("data") or {}
    if d.get("rate") is None:
        return None  # an attempt that found no fit
    try:
        return RateFit(rate=float(d["rate"]), low=float(d["low"]), high=float(d["high"]),
                       hours=int(d["hours"]), r2=float(d["r2"]))
    except (KeyError, TypeError, ValueError) as e:
        print(f"⚠️ MACF: usage share: unreadable cached fit ({e}); using the provisional rate", file=sys.stderr)
        return None


def refresh_fit(now: Optional[float] = None) -> bool:
    """Refit and record, unless an attempt was recorded in the last hour. For the Stop hook: the
    check reads only the last hour of fit events. Returns whether it refitted."""
    now = now or time.time()
    for _ in read_events(reverse=True, scope="all", only=FIT_EVENT, since=now - HOUR):
        return False
    att = try_fit(now=now)
    if att.fit is not None:
        record_fit(att.fit, DEFAULT_WINDOW_H)
    else:
        append_event(FIT_EVENT, {"rate": None, "reason": att.reason, "window_h": DEFAULT_WINDOW_H})
    return True


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


def share(window_h: float = 24.0, now: Optional[float] = None, fit: Optional[RateFit] = None) -> Share:
    """This agent's points over the last ``window_h`` hours, set against the account's movement.

    ``fit`` defaults to a fresh fit over the default window; with none, the provisional constant
    stands in and ``rate_source`` says so. The remainder is what others and unmetered use spent;
    it is None, not zero, when the account's movement is unknown.
    """
    now = now or time.time()
    if fit is None:
        fit = fit_rate(now=now)
    if fit is not None:
        rate, lo, hi, source = fit.rate, fit.low, fit.high, FITTED
    else:
        rate = lo = hi = usage_meter.POINTS_PER_WEIGHTED_TOKEN
        source = PROVISIONAL
    wt = 0.0
    for ev in read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=now - window_h * HOUR - HOUR):
        if _event_time(ev) >= now - window_h * HOUR:
            wt += _event_weighted(ev)
    account = _account_movement(window_h, now)
    points = wt * rate
    return Share(window_h=window_h, weighted_tokens=wt, rate=rate, low_rate=lo, high_rate=hi, rate_source=source,
                 points=points, points_low=wt * lo, points_high=wt * hi, account=account,
                 remainder=None if account is None else account - points,
                 remainder_low=None if account is None else account - wt * hi,
                 remainder_high=None if account is None else account - wt * lo)


# ── views ─────────────────────────────────────────────────────────────────────

def format_fit(att: FitAttempt, window_h: float) -> str:
    if att.fit is None:
        return f"no fit: {att.reason}\nprovisional rate {usage_meter.POINTS_PER_WEIGHTED_TOKEN:.3g} points/token"
    f = att.fit
    return "\n".join([
        f"rate, last {window_h:g}h",
        f"  {f.rate:.3g} points/weighted token",
        f"  90% {f.low:.3g} to {f.high:.3g}",
        f"  {f.hours} hours, r2 {f.r2:.2f}",
    ])


def format_share(s: Share) -> str:
    def rng(lo, hi): return f"({lo:.2f} to {hi:.2f})"
    lines = [f"share, last {s.window_h:g}h ({'fitted rate' if s.rate_source == FITTED else 'provisional rate'})",
             f"  me      {s.points:6.2f}  {rng(s.points_low, s.points_high)}"]
    if s.account is None:
        lines += ["  account unknown (too few samples)", "  others  unknown"]
    else:
        lines += [f"  account {s.account:6.2f}",
                  f"  others  {s.remainder:6.2f}  {rng(s.remainder_low, s.remainder_high)}"]
        if s.account > 0:
            lines.append(f"  my share {100 * s.points / s.account:.0f}%")
    lines.append("  others = other agents + unmetered use")
    return "\n".join(lines)


def run_rate(window_h: float = DEFAULT_WINDOW_H) -> str:
    att = try_fit(window_h)
    if att.fit is not None:
        record_fit(att.fit, window_h)
    return format_fit(att, window_h)


def me_lines(window_h: float) -> str:
    """The share block for ``budget me``. Refreshes the cached fit as a side effect."""
    att = try_fit()
    if att.fit is not None:
        record_fit(att.fit, DEFAULT_WINDOW_H)
    return format_share(share(window_h, fit=att.fit))


# ── hook line ─────────────────────────────────────────────────────────────────

ROLLED_EVENT = "usage_rolled"
ROLL_EVERY_S = 60.0
ROLLED_FRESH_S = 900.0


@dataclass(frozen=True, kw_only=True)
class HourPoints:
    points: float  # this agent's points over the last hour
    calls: int
    rate: float
    fitted: bool


def _hour_points(now: float) -> HourPoints:
    """Points over the last hour: one read of the last hour for the metered events and the newest
    fit event; never regresses. With no fit in that hour the provisional rate is used."""
    wt = 0.0
    calls = 0
    fit, fit_seen = None, False
    for ev in read_events(reverse=True, scope="all", only=(usage_meter.EVENT, FIT_EVENT), since=now - HOUR):
        if ev.get("event") == FIT_EVENT:
            if not fit_seen:  # newest first
                fit, fit_seen = _fit_from(ev), True
        else:
            wt += _event_weighted(ev)
            calls += int((ev.get("data") or {}).get("calls") or 0)
    rate = fit.rate if fit is not None else usage_meter.POINTS_PER_WEIGHTED_TOKEN
    return HourPoints(points=wt * rate, calls=calls, rate=rate, fitted=fit is not None)


def roll(now: Optional[float] = None) -> bool:
    """Record the last hour's points as a ``usage_rolled`` event, at most once a minute, so the hook
    line reads one event instead of an hour. Returns whether it wrote."""
    now = now or time.time()
    for ev in read_events(reverse=True, scope="all", only=ROLLED_EVENT, since=now - ROLL_EVERY_S):
        return False
    h = _hour_points(now)
    append_event(ROLLED_EVENT, {"points_1h": h.points, "calls_1h": h.calls, "rate": h.rate,
                                "fitted": h.fitted, "at": now})
    return True


def _newest_rolled(now: float) -> Optional[HourPoints]:
    """The newest ``usage_rolled`` event of the last ``ROLLED_FRESH_S``; stops at the first match."""
    for ev in read_events(reverse=True, scope="all", only=ROLLED_EVENT, since=now - ROLLED_FRESH_S):
        d = ev.get("data") or {}
        try:
            return HourPoints(points=float(d["points_1h"]), calls=int(d["calls_1h"]), rate=float(d["rate"]),
                              fitted=bool(d["fitted"]))
        except (KeyError, TypeError, ValueError) as e:
            print(f"⚠️ MACF: usage share: unreadable rolled event ({e}); computing the hour instead",
                  file=sys.stderr)
            return None
    return None


def hook_suffix(now: Optional[float] = None) -> Optional[str]:
    """``· me 0.21%/h``: this agent's points over the last hour, or None with no metered events.

    Reads the newest rolled event of the last 15 minutes and stops there. With none that recent
    (ticks are sparse) it computes the hour itself, as ``roll`` does, so the figure stays right.
    A provisional rate is marked ``~``.
    """
    now = now or time.time()
    h = _newest_rolled(now) or _hour_points(now)
    if h.points <= 0:
        return None
    from macf.budget import format_rate
    return f"· me {'' if h.fitted else '~'}{format_rate(h.points)}%/h"
