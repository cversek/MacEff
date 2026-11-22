"""Usage share: the fitted rate, the share and remainder, the hook suffix, and the two views.

Events are synthetic and written straight into the isolated log with chosen timestamps.
"""

import argparse
import json
import math
import time

from macf import usage_meter, usage_share
from macf.agent_events_log import get_log_path

TRUE_RATE = 4e-8  # points per weighted token
HOUR = 3600.0


def _hour_end():
    return math.floor(time.time() / HOUR) * HOUR


def _x(k):
    return 1e6 + 7e5 * ((k * 37) % 11)  # varied, deterministic tokens per hour


def _noise(k):
    return 0.03 * (((k * 53) % 7) / 6) - 0.015  # other agents' points: small, varied, zero mean


def _write(rows):
    with open(get_log_path(), "a") as f:
        for r in sorted(rows, key=lambda r: r["timestamp"]):
            f.write(json.dumps({**r, "hook_input": {}}) + "\n")


def _metered(t, tokens):
    return {"timestamp": t, "event": usage_meter.EVENT,
            "data": {"by_model": {"m": {"input_tokens": tokens, "calls": 1}}, "calls": 1, "cause": "operator"}}


def _sample(t, pct):
    return {"timestamp": t, "event": "budget_sampled",
            "data": {"source": "endpoint", "limits": [{"kind": "weekly_all", "percent": pct, "resets_at": None}]}}


def _history(hours, rate=TRUE_RATE, with_samples=True):
    """`hours` whole hours ending at the last hour boundary: tokens mid-hour, counter at boundaries."""
    end, rows, pct = _hour_end(), [], 10.0
    for k in range(hours):
        start = end - (hours - k) * HOUR
        if with_samples:
            rows.append(_sample(start, pct))
        rows.append(_metered(start + 1800, _x(k)))
        pct += rate * _x(k) + _noise(k)
    if with_samples:
        rows.append(_sample(end, pct))
    _write(rows)


def test_clean_fit_recovers_the_known_rate_within_its_interval():
    _history(30)
    fit = usage_share.fit_rate()
    assert fit is not None and fit.hours == 30
    assert fit.low <= TRUE_RATE <= fit.high
    assert abs(fit.rate - TRUE_RATE) / TRUE_RATE < 0.15
    assert fit.high - fit.low > 0 and fit.r2 > 0.8


def test_too_few_hours_is_no_fit_with_a_reason():
    _history(4)
    att = usage_share.try_fit()
    assert att.fit is None and "hours with metered tokens" in att.reason
    assert usage_share.fit_rate() is None


def test_share_and_remainder_add_up_to_the_account_movement():
    _history(30)
    s = usage_share.share(10)
    assert s.rate_source == "fit" and s.points > 0
    assert s.account > s.points > 0 or s.account > 0
    assert math.isclose(s.points + s.remainder, s.account, rel_tol=1e-9)
    assert math.isclose(s.points_low + s.remainder_high, s.account, rel_tol=1e-9)
    assert s.points_low <= s.points <= s.points_high


def test_share_without_samples_labels_the_constant_and_leaves_the_remainder_unknown():
    _history(30, with_samples=False)
    s = usage_share.share(10)
    assert s.rate_source == "provisional" and s.rate == usage_meter.POINTS_PER_WEIGHTED_TOKEN
    assert s.account is None and s.remainder is None
    assert "unknown" in usage_share.format_share(s)


def test_hook_suffix_shows_with_recent_events_and_ignores_old_ones():
    now = time.time()
    assert usage_share.hook_suffix(now) is None
    _write([_metered(now - 3 * HOUR, 9e9)])  # old: must not count
    assert usage_share.hook_suffix(now) is None
    _write([_metered(now - 600, 5e6)])
    want = usage_share.hook_suffix(now)
    assert want == f"· me ~{usage_share_fmt(5e6 * usage_meter.POINTS_PER_WEIGHTED_TOKEN)}%/h"


def usage_share_fmt(x):
    from macf.budget import format_rate
    return format_rate(x)


def test_hook_suffix_uses_a_fit_from_the_last_hour():
    now = time.time()
    _write([_metered(now - 600, 5e6)])
    usage_share.record_fit(usage_share.RateFit(rate=1e-7, low=9e-8, high=1.1e-7, hours=20, r2=0.9), 48)
    assert usage_share.hook_suffix(now) == f"· me {usage_share_fmt(0.5)}%/h"


def test_budget_me_prints_the_share_lines(capsys):
    _history(30)
    out = usage_meter.run_me("10h")
    assert "share, last" in out and "others" in out and "me " in out
    assert max(len(l) for l in out.splitlines()) <= 60


def test_budget_rate_prints_a_fit_and_caches_it(capsys):
    from macf.cli import cmd_budget_rate
    _history(30)
    assert cmd_budget_rate(argparse.Namespace(window=48.0)) == 0
    out = capsys.readouterr().out
    assert "points/weighted token" in out and "90%" in out and "30 hours" in out
    assert usage_share.refresh_fit() is False  # the fit just written is under an hour old


def test_hook_path_reads_only_the_last_hour(monkeypatch):
    """Thousands of old events and an old fit sit behind the window: the hook line must not walk them."""
    now = time.time()
    rows = [_metered(now - 5 * 86400 + i, 1e3) for i in range(3000)]
    rows.append({"timestamp": now - 3 * 86400, "event": usage_share.FIT_EVENT,
                 "data": {"rate": 1e-7, "low": 9e-8, "high": 1.1e-7, "hours": 20, "r2": 0.9}})
    rows.append(_metered(now - 300, 5e6))
    _write(rows)
    seen = []
    real = usage_share.read_events

    def counting(*a, **kw):
        for ev in real(*a, **kw):
            seen.append(ev)
            yield ev
    monkeypatch.setattr(usage_share, "read_events", counting)
    assert usage_share.hook_suffix(now).startswith("· me ~")  # the old fit is not used
    assert len(seen) == 1


def test_refresh_fit_runs_once_an_hour_even_when_there_is_no_fit():
    _history(3)
    assert usage_share.refresh_fit() is True
    assert usage_share.refresh_fit() is False


def test_one_token_hour_among_many_usable_hours_is_no_fit():
    """21 usable hours, one with tokens: the shape that gave a zero-width interval and a negative r2."""
    end, rows, pct = _hour_end(), [], 10.0
    for k in range(21):
        start = end - (21 - k) * HOUR
        rows.append(_sample(start, pct))
        if k == 20:
            rows.append(_metered(start + 1800, 1.5e5))
            pct += 1.0
    rows.append(_sample(end, pct))
    _write(rows)
    att = usage_share.try_fit()
    assert att.fit is None and "1 hours with metered tokens" in att.reason


def test_a_rate_far_from_the_provisional_one_is_refused():
    _history(30, rate=100 * TRUE_RATE)
    att = usage_share.try_fit()
    assert att.fit is None and "degenerate" in att.reason and "provisional" in att.reason
