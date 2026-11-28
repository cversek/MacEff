"""
The hourly spend digest and the sprint budget records.

Both read the agent's own events and nothing else; no state is kept beside the log.

Digest: at most once an hour, and only when the agent metered new spend since the last one,
``digest`` returns a short block: the hour's points, the split by cause, the largest driver,
the agent's share of the account's movement and what one more turn costs at the current
context. It records a ``usage_digest`` event so it does not repeat. The rate is the newest
calibration (``usage_share.calibration``), else the provisional constant; nothing here computes one.

Sprint records: ``sprint_started`` and ``sprint_ended`` append ``sprint_budget_start`` and
``sprint_budget_end`` events holding the weekly percent and reset from the latest sample and
the agent's metered points this week. The end event carries the deltas between the two.
"""

import datetime as dt
import sys
import time
from dataclasses import dataclass
from typing import Dict, Optional

from macf import usage_meter
from macf.agent_events_log import append_event, read_events

DIGEST_EVENT = "usage_digest"
START_EVENT = "sprint_budget_start"
END_EVENT = "sprint_budget_end"
HOUR = 3600.0
WEEK = 7 * 86400.0
SPRINT_LOOKBACK = 30 * 86400.0
NAMES = {"input_tokens": "input", "cache_write_1h_tokens": "cache write",
         "cache_write_5m_tokens": "cache write", "cache_read_input_tokens": "cache read",
         "output_tokens": "output"}


@dataclass(frozen=True, kw_only=True)
class Rate:
    value: float  # points per weighted token
    calibrated: bool
    read_weight: Optional[float] = None  # the calibration's cache-read weight; None is the price list's


def current_rate(now: float) -> Rate:
    """The newest calibration (``usage_share.calibration``), else the provisional constant. Never
    computes one: the rate is frozen until ``budget calibrate`` records another."""
    from macf.usage_share import calibration
    cal = calibration(now)
    if cal is not None:
        return Rate(value=cal.rate, calibrated=True, read_weight=cal.read_weight)
    return Rate(value=usage_meter.POINTS_PER_WEIGHTED_TOKEN, calibrated=False)


def _short(x: float) -> str:
    x = float(x)
    return f"{x / 1e6:.1f}M" if x >= 1e6 else f"{x / 1e3:.0f}k" if x >= 1e3 else f"{x:.0f}"


def _points(x: float) -> str:
    from macf.budget import format_rate
    return format_rate(x)


# ── the digest ────────────────────────────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class Spend:
    kinds: Dict[str, float]  # weighted tokens by kind, each model's scaled by its price factor
    by_cause: Dict[str, float]
    calls: int
    cache_read: int
    latest_call: Dict[str, float]  # mean tokens per call of the newest event
    latest_priced: float = 0.0  # the same call's weighted tokens at its models' price factors


def _spend(now: float, read_weight: Optional[float] = None) -> Optional[Spend]:
    """The last hour's spend, each event prorated over its calls' span, cache reads weighed at
    ``read_weight`` (the calibration's) when given."""
    weights = dict(usage_meter.WEIGHTS)
    if read_weight is not None:
        weights["cache_read_input_tokens"] = read_weight
    kinds = {k: 0.0 for k in usage_meter.TOKEN_KINDS}
    by_cause: Dict[str, float] = {}
    calls = cache_read = 0
    latest = None
    latest_priced = 0.0
    for ev in read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=now - HOUR):
        d = ev.get("data") or {}
        rows = list((d.get("by_model") or {}).values())
        n = sum(r.get("calls", 0) for r in rows)
        if not n:
            continue  # a baseline event meters nothing
        f = usage_meter.fraction_in(ev, now - HOUR, now)
        if f <= 0:
            continue
        cause = d.get("cause") or "operator"
        by_model = d.get("by_model") or {}
        for model, r in by_model.items():
            factor = usage_meter.model_factor(model) if usage_meter.weighted(r) else 0.0
            for k in usage_meter.TOKEN_KINDS:
                kinds[k] += f * factor * weights[k] * r.get(k, 0)
            by_cause[cause] = by_cause.get(cause, 0.0) + f * usage_meter.priced(r, model, read_weight)
            cache_read += f * r.get("cache_read_input_tokens", 0)
        calls += f * n
        if latest is None:
            latest = {k: sum(r.get(k, 0) for r in rows) / n for k in usage_meter.TOKEN_KINDS}
            latest_priced = usage_meter.priced_models(by_model, read_weight) / n
    if not calls or sum(kinds.values()) <= 0 or latest is None:
        return None
    return Spend(kinds=kinds, by_cause=by_cause, calls=max(1, round(calls)), cache_read=round(cache_read),
                 latest_call=latest, latest_priced=latest_priced)


def _share_line(wt: float, rate: Rate, now: float) -> str:
    from macf import usage_share
    account = usage_share._account_movement(1.0, now)
    if account is None:
        return "share: account movement unknown"
    mine = wt * rate.value
    mark = usage_share.STALE_MARK if usage_share.is_stale(mine, account) else ""
    out = f"share: {mark}{_points(mine)} of {account:g} account"
    if not rate.calibrated:
        out += " (provisional rate)"
    elif mark:
        out += " (calibration looks stale: budget calibrate)"
    return out


def digest(now: Optional[float] = None) -> Optional[str]:
    """The block, or None: within an hour of the last digest, or with nothing metered since."""
    now = now or time.time()
    for ev in read_events(reverse=True, scope="all", only=(DIGEST_EVENT,), since=now - HOUR):
        if ev.get("timestamp", 0) > now - HOUR:
            return None
        break
    rate = current_rate(now)
    sp = _spend(now, rate.read_weight)
    if sp is None:
        return None
    wt = sum(sp.kinds.values())
    pts = wt * rate.value
    top = sorted(sp.by_cause.items(), key=lambda kv: -kv[1])[:3]
    lines = [f"💳 spend, last hour: {_points(pts)} points, {sp.calls} calls",
             "  by cause: " + ", ".join(f"{c} {_points(w * rate.value)}" for c, w in top)]
    big = max(sp.kinds, key=lambda k: sp.kinds[k])
    pct = 100 * sp.kinds[big] / wt
    if big == "cache_read_input_tokens":
        lines.append(f"  driver: context × turns, {_short(sp.cache_read / sp.calls)} × {sp.calls}"
                     f" ({pct:.0f}% of points)")
    else:
        lines.append(f"  driver: {NAMES[big]}, {pct:.0f}% of points")
    lines.append("  " + _share_line(wt, rate, now))
    ctx = sum(v for k, v in sp.latest_call.items() if k != "output_tokens")
    nxt = sp.latest_priced * rate.value
    lines.append(f"  one more turn at {_short(ctx)} context: ~{_points(nxt)}")
    append_event(DIGEST_EVENT, {"points": pts, "calls": sp.calls, "window_h": 1})
    return "\n".join(lines)


# ── sprint budget records ─────────────────────────────────────────────────────

def _snapshot(now: float) -> dict:
    """The weekly percent and reset from the latest sample, and the agent's metered points this week."""
    from macf import budget
    hist = budget.samples(since=now - 2 * HOUR, now=now)
    pct = reset = None
    if hist:
        w = next((l for l in hist[-1]["limits"] if l.get("kind") == "weekly_all"), None)
        if w is not None:
            pct, reset = w.get("percent"), w.get("resets_at")
    since = now - WEEK
    if reset:
        try:
            began = dt.datetime.fromisoformat(str(reset)).timestamp() - WEEK
            if since <= began <= now:  # this week's start, when the reset makes sense
                since = began
        except ValueError as e:
            print(f"⚠️ MACF: sprint budget: unreadable reset {reset!r} ({e}); counting the last 7 days",
                  file=sys.stderr)
    rate = current_rate(now)
    s = usage_meter.summarize(since, rate.read_weight)
    points = sum(s.by_cause.values()) * rate.value
    return {"percent": pct, "resets_at": reset, "agent_points": points}


def sprint_started(task_id, now: Optional[float] = None) -> Optional[str]:
    """Append ``sprint_budget_start`` and return one line for the creation output; None on failure."""
    now = now or time.time()
    try:
        snap = _snapshot(now)
        append_event(START_EVENT, {"task_id": str(task_id), **snap})
    except Exception as e:  # noqa: BLE001 - GUARD: creating the task must not fail on its budget record
        print(f"⚠️ MACF: sprint budget start not recorded for #{task_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    pct = "unknown" if snap["percent"] is None else f"{snap['percent']:g}%"
    return f"💳 budget at start: week {pct}, me {_points(snap['agent_points'])} points this week"


def sprint_ended(task_id, now: Optional[float] = None) -> Optional[str]:
    """Append ``sprint_budget_end`` with the deltas since the matching start; return one line, None on failure."""
    now = now or time.time()
    try:
        snap = _snapshot(now)
        start = None
        for ev in read_events(reverse=True, scope="all", only=(START_EVENT,), since=now - SPRINT_LOOKBACK):
            if (ev.get("data") or {}).get("task_id") == str(task_id):
                start = ev["data"]
                break
        d_account = d_agent = None
        if start is None:
            print(f"⚠️ MACF: sprint budget: no start record for #{task_id} in 30 days; end recorded without deltas",
                  file=sys.stderr)
        else:
            if (snap["percent"] is not None and start.get("percent") is not None
                    and snap["resets_at"] == start.get("resets_at")):
                d_account = snap["percent"] - start["percent"]
            d_agent = snap["agent_points"] - start.get("agent_points", 0.0)
        append_event(END_EVENT, {"task_id": str(task_id), **snap,
                                 "account_points_delta": d_account, "agent_points_delta": d_agent})
    except Exception as e:  # noqa: BLE001 - GUARD: completing the task must not fail on its budget record
        print(f"⚠️ MACF: sprint budget end not recorded for #{task_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    acct = "account unknown" if d_account is None else f"account {d_account:+g}"
    mine = "me unknown" if d_agent is None else f"me {d_agent:+.3g}"
    return f"💳 sprint budget: {acct} points, {mine} points metered"
