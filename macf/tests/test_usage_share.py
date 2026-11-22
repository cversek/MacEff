"""Usage share: the fitted rate, the share and remainder, the hook suffix, and the two views.

Events are synthetic and written straight into the isolated log with chosen timestamps.
"""

import argparse
import json
import math
import time
from datetime import datetime, timezone

import pytest

from macf import usage_meter, usage_share
from macf.agent_events_log import get_log_path

TRUE_RATE = 4e-8  # points per weighted token
HOUR = 3600.0


def _main(argv):
    from macf.cli import main
    try:
        main(argv)
    except SystemExit as e:
        assert e.code in (0, None)


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
            "data": {"by_model": {"m": {"input_tokens": tokens, "calls": 1}}, "calls": 5, "cause": "operator"}}


def _sample(t, pct):
    return {"timestamp": t, "event": "budget_sampled",
            "data": {"source": "endpoint", "limits": [{"kind": "weekly_all", "percent": pct, "resets_at": None}]}}


def _history(hours, rate=TRUE_RATE, with_samples=True, end=None):
    """`hours` whole hours ending at `end` (default the last hour boundary): tokens mid-hour, counter at boundaries."""
    end, rows, pct = end or _hour_end(), [], 10.0
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
    rows.append(_metered(now - 5400, 5e6))  # 90 minutes old: outside the hour
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


# ── the fit's statistics and which hours count ────────────────────────────────

def _shaped(specs, end):
    """One hour per spec ``(tokens split across events, counter change)``; a negative change is a reset
    (the counter drops to the stated level). Tokens sit mid-hour; the counter is sampled at boundaries."""
    rows, pct = [], 50.0
    for k, (events, dy) in enumerate(specs):
        start = end - (len(specs) - k) * HOUR
        rows.append(_sample(start, pct))
        for j, tok in enumerate(events):
            rows.append(_metered(start + 600 + 600 * j, tok))
        pct = pct + dy if dy >= 0 else 2.0
    rows.append(_sample(end, pct))
    return rows


def test_fit_matches_a_hand_computation_and_counts_the_right_hours():
    end = _hour_end() - 5 * 86400  # the clock is a parameter: a far-past `now` must be honoured
    # (tokens, dy). Two events in one hour add; a flat hour and an empty hour are kept; the reset hour
    # (counter falls) is dropped; the huge event outside the window changes nothing.
    xs = [2e6, 3e6, 1e6, 4e6, 2.5e6, 3.5e6, 1.5e6]
    noise = [0.01, -0.02, 0.015, -0.01, 0.02, -0.015, 0.0]
    specs = [([x / 2, x / 2], TRUE_RATE * x + n) for x, n in zip(xs, noise)]
    specs += [([1e6], 0.0), ([], 0.05), ([4e6], -1.0)]  # flat, empty, reset
    rows = _shaped(specs, end)
    rows.append(_metered(end - 60 * HOUR, 9e9))
    _write(rows)
    ys = [TRUE_RATE * x + n for x, n in zip(xs, noise)] + [0.0, 0.05]
    xk = xs + [1e6, 0.0]
    rate = sum(x * y for x, y in zip(xk, ys)) / sum(x * x for x in xk)
    mean = sum(ys) / len(ys)
    r2 = 1 - sum((y - rate * x) ** 2 for x, y in zip(xk, ys)) / sum((y - mean) ** 2 for y in ys)
    a = usage_share.try_fit(now=end + 100)
    assert a.fit is not None
    assert math.isclose(a.fit.rate, rate, rel_tol=1e-9) and math.isclose(a.fit.r2, r2, rel_tol=1e-9)
    assert a.fit.hours == 9  # 7 + flat + empty; the reset hour is out
    assert a.fit.low < a.fit.rate < a.fit.high or a.fit.low <= a.fit.rate <= a.fit.high
    assert a.fit.low < a.fit.high
    assert usage_share.try_fit(now=end + 100) == a  # fixed seed


@pytest.mark.parametrize("token_hours,fits", [(5, False), (6, True)])
def test_the_minimum_is_six_hours_with_tokens(token_hours, fits):
    end = _hour_end() - 2 * 86400
    specs = [([_x(k)], TRUE_RATE * _x(k) + _noise(k)) for k in range(token_hours)]
    specs += [([], 0.01)] * 4  # empty hours do not count toward the minimum
    _write(_shaped(specs, end))
    a = usage_share.try_fit(now=end + 10)
    assert (a.fit is not None) is fits
    if not fits:
        assert f"{token_hours} hours with metered tokens" in a.reason


def test_a_failed_attempt_is_recorded_and_budget_rate_prints_it(capsys):
    main = _main
    _history(3)
    main(["budget", "rate"])
    out = capsys.readouterr().out
    assert out.startswith("no fit: 3 hours with metered tokens") and "provisional rate 4.08e-08" in out
    main(["budget", "rate", "--window", "24"])  # an integer window parses, and a no-fit run records nothing


# ── the account's movement and the share's window ─────────────────────────────

def test_account_movement_uses_the_sample_before_the_window_and_skips_resets():
    now = _hour_end() - 3 * 86400 + 900
    rows = [_sample(now - 4 * HOUR, 10.0), _sample(now - 2.5 * HOUR, 12.0),
            _sample(now - 1.5 * HOUR, 3.0), _sample(now - 0.5 * HOUR, 5.0)]
    inside = [_metered(now - 3 * HOUR + 60, 1e6), _metered(now - 600, 2e6), _metered(now - 600 + 1, 3e6),
              _metered(now - 3 * HOUR - 60, 9e9)]  # the last is just outside
    _write(rows + inside)
    fit = usage_share.RateFit(rate=1e-7, low=5e-8, high=2e-7, hours=10, r2=0.5)
    s = usage_share.share(3, now=now, fit=fit)
    assert s.account == 4.0  # 10->12 (+2), 12->3 reset (0), 3->5 (+2)
    assert s.weighted_tokens == 6e6
    assert math.isclose(s.points, 0.6) and math.isclose(s.remainder, 3.4)
    assert math.isclose(s.remainder_low, 4.0 - 6e6 * 2e-7) and math.isclose(s.remainder_high, 4.0 - 6e6 * 5e-8)
    assert usage_share.share(3, now=now, fit=fit).rate_source == "fit"
    assert usage_share.share(now=now, fit=fit).window_h == 24.0


def test_two_samples_are_the_minimum_for_a_movement():
    now = _hour_end() - 86400 + 900
    _write([_sample(now - 600, 40.0), _metered(now - 300, 1e6)])
    assert usage_share.share(2, now=now).account is None


# ── reads cross cycle boundaries, honour `now`, read last_ts ──────────────────

def _boundary(t):
    return {"timestamp": t, "event": "compaction_detected", "data": {}}


def test_reads_cross_a_cycle_boundary():
    end = _hour_end()
    _history(30, end=end)
    _write([_boundary(end + 5), _metered(end + 10, 4e6)])
    now = end + 20
    assert usage_share.try_fit(now=now).fit is not None
    assert usage_share.share(30, now=now, fit=usage_share.RateFit(rate=1e-8, low=1e-8, high=1e-8, hours=9, r2=1)).weighted_tokens > 4e6 * 2
    z = now + 10 * HOUR
    _write([_metered(z + 1, 1e6), _boundary(z + 2), _metered(z + 3, 1e6)])
    assert usage_share.hook_suffix(z + 4) == f"· me ~{usage_share_fmt(2e6 * usage_meter.POINTS_PER_WEIGHTED_TOKEN)}%/h"


def test_now_is_honoured_by_the_fit_share_and_hook_suffix():
    far = _hour_end() - 4 * 86400
    _history(30, end=far)
    assert usage_share.try_fit(now=far).fit is not None
    assert usage_share.try_fit().fit is None  # at the real time those hours are out of the window
    assert usage_share.share(30, now=far).weighted_tokens > 0
    assert usage_share.share(30).weighted_tokens == 0
    _write([_metered(far + 600, 5e6)])
    assert usage_share.hook_suffix(far + 900) is not None and usage_share.hook_suffix() is None


@pytest.mark.parametrize("data,expect", [
    ({"last_ts": "2026-11-22T10:00:00Z"}, datetime(2026, 11, 22, 10, tzinfo=timezone.utc).timestamp()),
    ({"last_ts": "2026-11-22T10:00:00+00:00"}, datetime(2026, 11, 22, 10, tzinfo=timezone.utc).timestamp()),
    ({"last_ts": "not a time"}, 77.0),
    ({}, 77.0),
])
def test_event_time_prefers_last_ts_and_falls_back_loudly(data, expect, capsys):
    assert usage_share._event_time({"timestamp": 77, "data": data}) == expect
    assert ("unreadable last_ts" in capsys.readouterr().err) == (data.get("last_ts") == "not a time")


def test_an_events_models_add():
    ev = {"data": {"by_model": {"a": {"input_tokens": 100}, "b": {"output_tokens": 10}}}}
    assert usage_share._event_weighted(ev) == 100 + 50


# ── the hook line ─────────────────────────────────────────────────────────────

def test_hook_suffix_adds_events_reads_newest_fit_and_survives_an_unreadable_one(capsys):
    now = time.time()
    fit = lambda t, r: {"timestamp": t, "event": usage_share.FIT_EVENT,
                        "data": {"rate": r, "low": r, "high": r, "hours": 9, "r2": 0.5}}
    _write([_metered(now - 1000, 2e6), _metered(now - 500, 3e6), fit(now - 900, 1e-7), fit(now - 800, 2e-7)])
    assert usage_share.hook_suffix(now) == f"· me {usage_share_fmt(5e6 * 2e-7)}%/h"  # newest fit, events summed
    _write([{"timestamp": now - 100, "event": usage_share.FIT_EVENT, "data": {"rate": 1e-7}}])
    assert usage_share.hook_suffix(now) == f"· me ~{usage_share_fmt(5e6 * usage_meter.POINTS_PER_WEIGHTED_TOKEN)}%/h"
    assert "unreadable cached fit" in capsys.readouterr().err
    _write([{"timestamp": now - 50, "event": usage_share.FIT_EVENT, "data": {"rate": None, "reason": "x"}}])
    assert usage_share.hook_suffix(now).startswith("· me ~")  # a recorded no-fit means provisional
    z = now + 10 * HOUR
    _write([_metered(z - 10, 0)])
    assert usage_share.hook_suffix(z) is None  # tokens of zero show nothing


def test_the_weekly_line_joins_the_suffix_and_survives_one_that_raises(monkeypatch, capsys):
    from macf import budget
    now = time.time()
    _write([_sample(now - 60, 41.0), _metered(now - 300, 5e6)])
    line = budget.weekly_usage(now)
    want = usage_share.hook_suffix(now)
    assert line == f"41% {want}" and "  " not in line
    monkeypatch.setattr(usage_share, "hook_suffix", lambda n=None: (_ for _ in ()).throw(RuntimeError("boom")))
    assert budget.weekly_usage(now) == "41%"
    assert "own-rate suffix skipped" in capsys.readouterr().err


# ── the views and the commands ────────────────────────────────────────────────

def test_the_views_print_exactly_this():
    fit = usage_share.RateFit(rate=4.5e-8, low=3.9e-8, high=5.2e-8, hours=21, r2=0.87)
    assert usage_share.format_fit(usage_share.FitAttempt(fit=fit), 48) == (
        "rate, last 48h\n  4.5e-08 points/weighted token\n  90% 3.9e-08 to 5.2e-08\n  21 hours, r2 0.87")
    assert usage_share.format_fit(usage_share.FitAttempt(fit=None, reason="why"), 48) == (
        "no fit: why\nprovisional rate 4.08e-08 points/token")
    s = usage_share.Share(window_h=24, weighted_tokens=1e8, rate=4.5e-8, low_rate=3.9e-8, high_rate=5.2e-8,
                          rate_source="fit", points=4.5, points_low=3.9, points_high=5.2, account=12.0,
                          remainder=7.5, remainder_low=6.8, remainder_high=8.1)
    assert usage_share.format_share(s) == (
        "share, last 24h (fitted rate)\n  me        4.50  (3.90 to 5.20)\n  account  12.00\n"
        "  others    7.50  (6.80 to 8.10)\n  my share 38%\n  others = other agents + unmetered use")
    unknown = usage_share.Share(window_h=6, weighted_tokens=1e6, rate=4.08e-8, low_rate=4.08e-8, high_rate=4.08e-8,
                                rate_source="provisional", points=0.04, points_low=0.04, points_high=0.04,
                                account=None, remainder=None, remainder_low=None, remainder_high=None)
    assert usage_share.format_share(unknown) == (
        "share, last 6h (provisional rate)\n  me        0.04  (0.04 to 0.04)\n"
        "  account unknown (too few samples)\n  others  unknown\n  others = other agents + unmetered use")
    flat = usage_share.Share(**{**unknown.__dict__, "account": 0.0, "remainder": -0.04,
                                "remainder_low": -0.04, "remainder_high": -0.04})
    assert "my share" not in usage_share.format_share(flat)  # no division by a zero account


def test_the_commands_wire_the_window_and_the_cached_fit(capsys):
    main = _main
    _history(30)
    main(["budget", "rate"])
    assert "rate, last 48h" in capsys.readouterr().out
    main(["budget", "rate", "--window", "24"])
    assert "rate, last 24h" in capsys.readouterr().out
    n = lambda: sum(1 for _ in usage_share.read_events(reverse=False, scope="all", only=usage_share.FIT_EVENT))
    before = n()
    main(["budget", "me", "--since", "10h"])
    out = capsys.readouterr().out
    assert "share, last 10h (fitted rate)" in out and "\n\nshare" in out
    assert n() == before + 1  # budget me refreshes the cached fit


@pytest.mark.parametrize("rate,want", [(50.0, (6, 96)), (0.0, (0.0, 96)), (200.0, (6, 200.0))])
def test_the_interval_is_the_5th_to_95th_percentile_widened_to_the_rate(rate, want):
    assert usage_share._interval(list(range(100, 0, -1)), rate) == want  # sorted 1..100: indexes 5 and 95


@pytest.mark.parametrize("specs,words", [
    ([([2e6], 0.08)] * 7, "zero-width"),  # identical hours: every resampled slope is the same
    ([([x * 1e6], y) for x, y in zip(range(1, 7), (0.30, 0.25, 0.20, 0.15, 0.10, 0.05))], "below zero"),
])
def test_a_degenerate_fit_is_refused_with_its_reason(specs, words):
    end = _hour_end() - 86400
    _write(_shaped(specs, end))
    a = usage_share.try_fit(now=end + 10)
    assert a.fit is None and "degenerate" in a.reason and words in a.reason


def _fit_events():
    return [e["data"] for e in usage_share.read_events(reverse=False, scope="all", only=usage_share.FIT_EVENT)]


def test_refresh_fit_records_a_fit_once_an_hour_and_a_no_fit_attempt_too():
    _history(30)
    now = time.time()
    assert usage_share.refresh_fit(now) is True
    [d] = _fit_events()
    assert d["window_h"] == usage_share.DEFAULT_WINDOW_H and d["hours"] == 30 and 0 < d["r2"] <= 1
    assert d["low"] < d["rate"] < d["high"]
    assert usage_share.refresh_fit(now + 60) is False and len(_fit_events()) == 1
    assert usage_share.refresh_fit(now + 3700) is True and len(_fit_events()) == 2  # an hour on


def test_refresh_fit_ignores_a_fit_older_than_an_hour_but_not_one_just_under():
    _history(30)
    now = time.time()
    _write([{"timestamp": now - 5400, "event": usage_share.FIT_EVENT,
             "data": {"rate": 1e-8, "low": 1e-8, "high": 1e-8, "hours": 9, "r2": 0.5}}])
    assert usage_share.refresh_fit(now) is True  # 90 minutes old counts as stale
    _write([{"timestamp": now + 3000, "event": usage_share.FIT_EVENT,
             "data": {"rate": 1e-8, "low": 1e-8, "high": 1e-8, "hours": 9, "r2": 0.5}}])
    assert usage_share.refresh_fit(now + 3400) is False


def test_a_no_fit_attempt_records_a_null_rate_and_its_reason():
    _history(3)
    assert usage_share.refresh_fit() is True
    [d] = _fit_events()
    assert d["rate"] is None and d["reason"].startswith("3 hours with metered tokens")
    assert d["window_h"] == usage_share.DEFAULT_WINDOW_H and set(d) == {"rate", "reason", "window_h"}


def test_the_stop_hook_refreshes_the_fit(tmp_path):
    from unittest.mock import patch
    from macf.hooks.handle_stop import run
    _history(30)
    t = tmp_path / "s.jsonl"
    t.write_text("")
    stdin = json.dumps({"stop_reason": "end_turn", "session_id": "sid", "transcript_path": str(t)})
    with patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(False, "test")):
        run(stdin)
        run(stdin)
    [d] = _fit_events()  # the second Stop is inside the hour
    assert d["rate"] is not None and d["hours"] == 30


def test_the_hook_line_ignores_a_metered_event_ninety_minutes_old():
    now = time.time()
    _write([_metered(now - 5400, 5e6)])
    assert usage_share.hook_suffix(now) is None


@pytest.mark.parametrize("factor,fits", [(1 / 20, False), (1 / 5, True), (5, True), (20, False)])
def test_the_rate_band_is_ten_times_either_way(factor, fits):
    end = _hour_end() - 86400
    rate = usage_meter.POINTS_PER_WEIGHTED_TOKEN * factor
    specs = [([_x(k)], rate * _x(k) * (1 + 0.2 * (((k * 53) % 7) - 3) / 3)) for k in range(9)]
    _write(_shaped(specs, end))
    a = usage_share.try_fit(now=end + 10)
    assert (a.fit is not None) is fits
    if not fits:
        assert "degenerate" in a.reason and "10x" in a.reason and "provisional" in a.reason


def test_hook_suffix_marks_a_window_shorter_than_an_hour():
    now = time.time()
    ev = _metered(now - 300, 2e6)
    ev["data"]["metering_since"] = now - 600               # metering is ten minutes old
    _write([ev])
    assert usage_share.hook_suffix(now).endswith(usage_share.PARTIAL_MARK)


def test_hook_suffix_leaves_a_fully_metered_busy_hour_unmarked():
    now = time.time()
    ev = _metered(now - 300, 2e6)
    ev["data"]["metering_since"] = now - 4 * 3600
    _write([ev])
    assert not usage_share.hook_suffix(now).endswith(usage_share.PARTIAL_MARK)


def test_hook_suffix_marks_a_one_call_hour():
    now = time.time()
    ev = _metered(now - 300, 2e6)
    ev["data"]["metering_since"] = now - 4 * 3600
    ev["data"]["calls"] = 1
    _write([ev])
    assert usage_share.hook_suffix(now).endswith(usage_share.PARTIAL_MARK)
