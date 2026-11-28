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
- x is the weighted tokens of the ``usage_metered`` events in the hour, each event prorated over
  its calls' span (``usage_meter.fraction_in``); y is the counter's change over the hour.
- The cache-read weight is fitted, not taken from the price list. Cache reads are most of an
  agent's tokens, and at the list's 0.1 of an input token they swamped the rest, though the
  counter showed them costing far less: one hour of parallel subagents re-reading their context
  was metered at more points than the whole account moved (#1176). Each weight of ``READ_GRID``
  is tried and the one with the lowest residual sum of squares is kept, with its slope. With no
  cache reads in the window the weight cannot be told, and the list's stands. Every conversion of
  tokens to points with a fit uses the fit's weight; without a fit the provisional constant and
  the list's weights go together, as they were fitted.
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

No share above the account. An agent's points over a window cannot exceed what the whole account
moved over it; the counter's whole-percent step allows one point more. A share above that bound
is capped to it and marked (``≤`` on the hook line, a line in ``budget me``), so a rate that
overstates a burst cannot show one agent spending more than everyone. With the account's movement
unknown nothing is capped.
"""

import math
import random
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from macf import usage_meter
from macf.agent_events_log import append_event, read_events

FIT_EVENT = "usage_rate_fitted"
MIN_HOURS = 6
DEFAULT_WINDOW_H = 48.0
BOOTSTRAPS = 400
SANE_FACTOR = 10.0
HOUR = 3600.0
#: Cache-read weights tried by the fit, relative to an uncached input token.
READ_GRID = (0.0, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.1)
PRICE_READ_WEIGHT = usage_meter.WEIGHTS["cache_read_input_tokens"]
#: The counter moves in whole percents: the account's measured rise can understate its use by this.
GAUGE_STEP = 1.0
CAP_MARK = "≤"
PROVISIONAL = "provisional"
FITTED = "fit"


@dataclass(frozen=True, kw_only=True)
class RateFit:
    rate: float  # points per weighted token
    low: float  # 90% interval
    high: float
    hours: int
    r2: float
    read_weight: float = PRICE_READ_WEIGHT  # the cache-read weight the rate was fitted at


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
    read_weight: Optional[float] = None  # the fit's cache-read weight; None is the price list's
    capped: bool = False  # points were held to the account's movement plus GAUGE_STEP


def cap_points(points: float, account: Optional[float]) -> tuple:
    """``(points, capped)``: points held to ``account + GAUGE_STEP``; unchanged with no account."""
    if account is None or points <= account + GAUGE_STEP:
        return points, False
    return account + GAUGE_STEP, True


def _event_weighted(ev: dict, read_weight: Optional[float] = None) -> float:
    return sum(usage_meter.weighted(row, read_weight)
               for row in ((ev.get("data") or {}).get("by_model") or {}).values())


def _event_reads(ev: dict) -> float:
    return sum(row.get("cache_read_input_tokens", 0)
               for row in ((ev.get("data") or {}).get("by_model") or {}).values())


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
    """Per usable hour: ``rest`` (weighted tokens other than cache reads), ``reads`` (cache-read
    tokens) and ``y`` (the counter's change). Each event is spread over the hours its calls span."""
    end = math.floor(now / HOUR) * HOUR
    start = end - math.ceil(window_h) * HOUR
    pts = _weekly_points(start - HOUR, now)
    hours = int((end - start) // HOUR)
    rest: Dict[int, float] = {}
    reads: Dict[int, float] = {}
    for ev in read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=start - HOUR):
        first, last = usage_meter.event_span(ev)
        if last < start or first >= end:
            continue
        w, r = _event_weighted(ev, 0.0), _event_reads(ev)
        for k in range(max(0, int((first - start) // HOUR)), min(hours, int((last - start) // HOUR) + 1)):
            f = usage_meter.fraction_in(ev, start + k * HOUR, start + (k + 1) * HOUR)
            if f > 0:
                rest[k] = rest.get(k, 0.0) + f * w
                reads[k] = reads.get(k, 0.0) + f * r
    out: Dict[str, List[float]] = {"rest": [], "reads": [], "y": []}
    for k in range(hours):
        a, b = _percent_at(pts, start + k * HOUR), _percent_at(pts, start + (k + 1) * HOUR)
        if a is None or b is None or b < a:
            continue
        out["rest"].append(rest.get(k, 0.0))
        out["reads"].append(reads.get(k, 0.0))
        out["y"].append(b - a)
    return out


def _read_weight(rest: List[float], reads: List[float], ys: List[float]) -> float:
    """The weight of ``READ_GRID`` whose through-origin fit leaves the smallest residual sum of
    squares; the price list's when the window has no cache reads to tell them apart."""
    if not any(r > 0 for r in reads):
        return PRICE_READ_WEIGHT
    best, best_sse = PRICE_READ_WEIGHT, None
    for w in READ_GRID:
        xs = [q + w * r for q, r in zip(rest, reads, strict=True)]
        slope = _slope(xs, ys)
        if slope is None:
            continue
        sse = sum((y - slope * x) ** 2 for x, y in zip(xs, ys, strict=True))
        if best_sse is None or sse < best_sse:
            best, best_sse = w, sse
    return best


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
    ys = data["y"]
    n = len(ys)
    with_tokens = sum(1 for q, r in zip(data["rest"], data["reads"], strict=True) if q + r > 0)
    if with_tokens < MIN_HOURS:
        return FitAttempt(fit=None, reason=f"{with_tokens} hours with metered tokens ({n} usable) in the "
                                           f"last {window_h:g}h, need {MIN_HOURS}")
    read_weight = _read_weight(data["rest"], data["reads"], ys)
    xs = [q + read_weight * r for q, r in zip(data["rest"], data["reads"], strict=True)]
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
    return FitAttempt(fit=RateFit(rate=rate, low=low, high=high, hours=n, r2=r2, read_weight=read_weight))


def fit_rate(window_h: float = DEFAULT_WINDOW_H, now: Optional[float] = None) -> Optional[RateFit]:
    """The fit, or None when there are too few usable hours (``try_fit`` says why)."""
    return try_fit(window_h, now).fit


def record_fit(fit: RateFit, window_h: float) -> None:
    """Cache a fit as an event for the hooks to read."""
    append_event(FIT_EVENT, {"rate": fit.rate, "low": fit.low, "high": fit.high, "hours": fit.hours,
                             "r2": fit.r2, "read_weight": fit.read_weight, "window_h": window_h})


def _fit_from(ev: dict) -> Optional[RateFit]:
    d = ev.get("data") or {}
    if d.get("rate") is None:
        return None  # an attempt that found no fit
    try:
        return RateFit(rate=float(d["rate"]), low=float(d["low"]), high=float(d["high"]),
                       hours=int(d["hours"]), r2=float(d["r2"]),
                       read_weight=float(d.get("read_weight", PRICE_READ_WEIGHT)))
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
        rate, lo, hi, source, rw = fit.rate, fit.low, fit.high, FITTED, fit.read_weight
    else:
        rate = lo = hi = usage_meter.POINTS_PER_WEIGHTED_TOKEN
        source, rw = PROVISIONAL, None
    begin = now - window_h * HOUR
    wt = 0.0
    for ev in read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=begin - HOUR):
        f = usage_meter.fraction_in(ev, begin, now)
        if f > 0:
            wt += f * _event_weighted(ev, rw)
    account = _account_movement(window_h, now)
    points, capped = cap_points(wt * rate, account)
    p_low, p_high = cap_points(wt * lo, account)[0], cap_points(wt * hi, account)[0]
    return Share(window_h=window_h, weighted_tokens=wt, rate=rate, low_rate=lo, high_rate=hi, rate_source=source,
                 points=points, points_low=p_low, points_high=p_high, account=account,
                 remainder=None if account is None else account - points,
                 remainder_low=None if account is None else account - p_high,
                 remainder_high=None if account is None else account - p_low,
                 read_weight=rw, capped=capped)


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
        f"  cache read weight {f.read_weight:g} (fitted)",
    ])


def format_share(s: Share) -> str:
    def rng(lo, hi): return f"({lo:.2f} to {hi:.2f})"
    lines = [f"share, last {s.window_h:g}h ({'fitted rate' if s.rate_source == FITTED else 'provisional rate'})",
             f"  me    {CAP_MARK if s.capped else ' '} {s.points:6.2f}  {rng(s.points_low, s.points_high)}"]
    if s.account is None:
        lines += ["  account unknown (too few samples)", "  others  unknown"]
    else:
        lines += [f"  account {s.account:6.2f}",
                  f"  others  {s.remainder:6.2f}  {rng(s.remainder_low, s.remainder_high)}"]
        if s.account > 0 and not s.capped:  # capped, the ratio would claim over 100%
            lines.append(f"  my share {100 * s.points / s.account:.0f}%")
    if s.capped:
        lines += [f"  me capped at account + {GAUGE_STEP:g} (the counter's step):",
                  "  the rate put me above the whole account"]
    if s.read_weight is not None:
        lines.append(f"  cache read weight {s.read_weight:g} (fitted)")
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
    partial: bool = False  # metering is under an hour old, or the hour holds under THIN_CALLS calls
    account: Optional[float] = None  # the account's movement over the same hour; None when unknown


#: An hour with fewer metered calls than this is a sample, not a rate.
THIN_CALLS = 3
PARTIAL_MARK = " part"


def _hour_points(now: float) -> HourPoints:
    """Points over the last hour: one read of the last hour for the metered events and the newest
    fit event; never regresses. With no fit in that hour the provisional rate is used."""
    fit, fit_seen = None, False
    metered = []
    for ev in read_events(reverse=True, scope="all", only=(usage_meter.EVENT, FIT_EVENT), since=now - HOUR):
        if ev.get("event") == FIT_EVENT:
            if not fit_seen:  # newest first
                fit, fit_seen = _fit_from(ev), True
        else:
            metered.append(ev)
    rw = fit.read_weight if fit is not None else None
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
    rate = fit.rate if fit is not None else usage_meter.POINTS_PER_WEIGHTED_TOKEN
    return HourPoints(points=wt * rate, calls=round(calls), rate=rate, fitted=fit is not None, partial=partial,
                      account=_account_movement(1.0, now))


def roll(now: Optional[float] = None) -> bool:
    """Record the last hour's points as a ``usage_rolled`` event, at most once a minute, so the hook
    line reads one event instead of an hour. Returns whether it wrote."""
    now = now or time.time()
    for ev in read_events(reverse=True, scope="all", only=ROLLED_EVENT, since=now - ROLL_EVERY_S):
        return False
    h = _hour_points(now)
    append_event(ROLLED_EVENT, {"points_1h": h.points, "calls_1h": h.calls, "rate": h.rate,
                                "fitted": h.fitted, "partial": h.partial, "account_1h": h.account, "at": now})
    return True


def _newest_rolled(now: float) -> Optional[HourPoints]:
    """The newest ``usage_rolled`` event of the last ``ROLLED_FRESH_S``; stops at the first match."""
    for ev in read_events(reverse=True, scope="all", only=ROLLED_EVENT, since=now - ROLLED_FRESH_S):
        d = ev.get("data") or {}
        try:
            account = d.get("account_1h")
            return HourPoints(points=float(d["points_1h"]), calls=int(d["calls_1h"]), rate=float(d["rate"]),
                              fitted=bool(d["fitted"]), partial=bool(d.get("partial", False)),
                              account=None if account is None else float(account))
        except (KeyError, TypeError, ValueError) as e:
            print(f"⚠️ MACF: usage share: unreadable rolled event ({e}); computing the hour instead",
                  file=sys.stderr)
            return None
    return None


def hook_suffix(now: Optional[float] = None) -> Optional[str]:
    """``· me 0.21%/1h``: this agent's points over the last hour, or None with no metered events.

    The window is written out (``/1h``) because the weekly field beside it is a two-hour smoothed
    rate, and the two are not the same measurement. Points above the account's own movement over
    the hour plus ``GAUGE_STEP`` are capped to it and marked ``≤`` (``cap_points``).

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
    points, capped = cap_points(h.points, h.account)
    return (f"· me {CAP_MARK if capped else ''}{'' if h.fitted else '~'}{format_rate(points)}%/1h"
            f"{PARTIAL_MARK if h.partial else ''}")
