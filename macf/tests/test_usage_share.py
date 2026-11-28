"""Usage share: the frozen calibration and its envelope, the share and remainder, the hook suffix, the views.

Events are synthetic and written straight into the isolated log with chosen timestamps.
"""

import json
import math
import time
from datetime import datetime, timezone

import pytest

from macf import usage_meter, usage_share
from macf.agent_events_log import get_log_path, read_events

HOUR = 3600.0
P = usage_meter.POINTS_PER_WEIGHTED_TOKEN


def _main(argv):
    from macf.cli import main
    try:
        main(argv)
    except SystemExit as e:
        assert e.code in (0, None)


def _hour_end():
    return math.floor(time.time() / HOUR) * HOUR


def _write(rows):
    with open(get_log_path(), "a") as f:
        for r in sorted(rows, key=lambda r: r["timestamp"]):
            f.write(json.dumps({**r, "hook_input": {}}) + "\n")


def _metered(t, tokens):
    return {"timestamp": t, "event": usage_meter.EVENT,
            "data": {"by_model": {"m": {"input_tokens": tokens, "calls": 1}}, "calls": 5, "cause": "operator"}}


def _metered_rows(t, rest=0.0, reads=0.0, first=None):
    data = {"by_model": {"m": {"input_tokens": rest, "cache_read_input_tokens": reads, "calls": 1}},
            "calls": 5, "cause": "operator"}
    if first is not None:  # the event's calls span [first, t]
        data["first_ts"] = datetime.fromtimestamp(first, timezone.utc).isoformat()
        data["last_ts"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
    return {"timestamp": t, "event": usage_meter.EVENT, "data": data}


def _sample(t, pct, reset=None):
    return {"timestamp": t, "event": "budget_sampled",
            "data": {"source": "endpoint", "limits": [{"kind": "weekly_all", "percent": pct, "resets_at": reset}]}}


def _calibrated(t, rate, read_weight=usage_share.READ_WEIGHT):
    return {"timestamp": t, "event": usage_share.CALIBRATION_EVENT,
            "data": {"rate": rate, "read_weight": read_weight, "method": usage_share.METHOD, "at": t,
                     "windows": 9, "window": None, "lookback_days": 14}}


def _fmt(x):
    from macf.budget import format_rate
    return format_rate(x)


def _hours(specs, end):
    """One whole hour per spec ``(this agent's tokens, counter change)``, ending at ``end``: the
    tokens mid-hour, the counter sampled at every boundary."""
    rows, pct = [], 10.0
    for k, (tok, dy) in enumerate(specs):
        start = end - (len(specs) - k) * HOUR
        rows.append(_sample(start, pct))
        if tok:
            rows.append(_metered(start + 1800, tok))
        pct += dy
    rows.append(_sample(end, pct))
    return rows


# ── the envelope ──────────────────────────────────────────────────────────────

def test_the_envelope_is_the_tightest_window_and_a_busy_hour_from_others_only_loosens_its_own():
    """Hours of 4e7 tokens at 4e-8 points each; in one of them others added 5 points. That hour's
    window bounds the rate at (6 + 1) / 4e7, loose, and is not the one chosen: the quiet 12-hour
    stretch gives the tightest bound."""
    end = _hour_end() - 86400
    specs = [(4e7, 2.0)] * 12 + [(4e7, 7.0)] + [(4e7, 2.0)] * 3  # 1.6 own points an hour, shown as 2
    _write(_hours(specs, end))
    c = usage_share.envelope(end + 60).calibration
    assert c is not None and c.read_weight == 0.1 and c.method == "lower_envelope"
    assert math.isclose(c.rate, (24.0 + 1.0) / (12 * 4e7))  # the 12 quiet hours: delta 24, x 4.8e8
    assert c.window["hours"] == 12 and c.window["end"] == end - 4 * HOUR and c.window["delta"] == 24.0
    assert c.window["kind"] == "hour"  # the step windows here start an hour later and hold fewer tokens
    # hour windows: 16 starts, each with up to 12: 12 for the first five starts, then 11, 10 .. 1;
    # step windows: from the step-up samples 1..15 to the pre-step samples up to 15, 1 to 12h apart
    assert c.windows == (5 * 12 + sum(range(1, 12))) + (3 * 12 + sum(range(0, 12)))
    busy = (7.0 + 1.0) / 4e7
    assert busy > c.rate
    # the same history without the other agents' 5 points calibrates to the same rate
    _clear()
    _write(_hours([(4e7, 2.0)] * 16, end))
    assert math.isclose(usage_share.envelope(end + 60).calibration.rate, c.rate)


def _clear():
    open(get_log_path(), "w").close()


def test_the_envelope_skips_a_window_holding_a_weekly_reset():
    end = _hour_end() - 86400
    rows = [_sample(end - 3 * HOUR, 80.0, "2026-11-25T20:00:00+00:00"), _metered(end - 2.5 * HOUR, 4e7),
            _sample(end - 2 * HOUR, 0.0, "2026-12-02T20:00:00+00:00"), _metered(end - 1.5 * HOUR, 4e7),
            _sample(end - HOUR, 3.0, "2026-12-02T20:00:00+00:00")]
    _write(rows)
    c = usage_share.envelope(end).calibration
    assert c.windows == 1 and c.window["delta"] == 3.0  # only the hour after the reset


# ── the frozen rate ───────────────────────────────────────────────────────────

def test_the_rate_is_the_newest_calibration_and_the_hook_and_stop_paths_never_compute_one(tmp_path, monkeypatch):
    from unittest.mock import patch
    from macf.hooks.handle_stop import run
    now = time.time()
    _write([_calibrated(now - 9 * 86400, 1e-7), _calibrated(now - 8 * 86400, 2e-7), _metered(now - 600, 5e6)])
    assert usage_share.calibration(now).rate == 2e-7
    assert usage_share.hook_suffix(now) == f"· me {_fmt(5e6 * 2e-7)}%/1h"
    calls = []
    monkeypatch.setattr(usage_share, "envelope", lambda *a, **k: calls.append(1))
    t = tmp_path / "s.jsonl"
    t.write_text("")
    stdin = json.dumps({"stop_reason": "end_turn", "session_id": "sid", "transcript_path": str(t)})
    with patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(False, "test")):
        run(stdin)
    assert usage_share.roll(now) is True
    assert usage_share.hook_suffix(now + 5).startswith(f"· me {_fmt(5e6 * 2e-7)}%/1h")  # the Stop began metering
    assert calls == [] and len(list(read_events(reverse=False, scope="all", only=usage_share.CALIBRATION_EVENT))) == 2


def test_the_rolled_event_carries_the_calibration_so_the_read_stops_there(monkeypatch):
    now = time.time()
    _write([_calibrated(now - 3 * 86400, 2e-7)] + [_metered(now - 3 * 86400 + i, 1e3) for i in range(2000)]
           + [_metered(now - 600, 5e6)])
    assert usage_share.roll(now) is True
    seen = []
    real = usage_share.read_events

    def counting(*a, **kw):
        for ev in real(*a, **kw):
            seen.append(ev["event"])
            yield ev
    monkeypatch.setattr(usage_share, "read_events", counting)
    assert usage_share.calibration(now + 5).rate == 2e-7
    assert seen == [usage_share.ROLLED_EVENT]


def test_me_does_not_change_when_other_agents_move_the_counter():
    """The same own tokens under two counter traces, one quiet and one with other agents busy: the
    calibrated me is the same, and only the account and the remainder differ."""
    now = _hour_end() - 2 * 86400 + 1800
    own = [_calibrated(now - 86400, 5e-8), _metered(now - 1200, 2e7)]
    _write(own + [_sample(now - 3000, 30.0), _sample(now - 60, 31.0)])
    quiet = usage_share.share(1, now=now)
    _clear()
    _write(own + [_sample(now - 3000, 30.0), _sample(now - 60, 38.0)])
    busy = usage_share.share(1, now=now)
    assert quiet.points == busy.points == pytest.approx(2e7 * 5e-8)
    assert quiet.rate_source == busy.rate_source == "calibrated"
    assert (quiet.account, busy.account) == (1.0, 8.0) and busy.remainder == pytest.approx(7.0)
    assert not quiet.stale and not busy.stale


def test_me_above_the_account_plus_one_is_shown_uncapped_and_marked_stale():
    now = time.time()
    _write([_calibrated(now - 86400, 1e-7), _metered_rows(now - 600, rest=3.6e7)])  # 3.6 points
    _write([_sample(now - 3000, 40.0), _sample(now - 60, 42.0)])  # the account rose 2
    assert usage_share.hook_suffix(now) == f"· me !{_fmt(3.6)}%/1h"
    assert usage_share.roll(now) is True  # the mark survives the rolled event the hook line reads
    assert usage_share.hook_suffix(now + 5) == f"· me !{_fmt(3.6)}%/1h"
    s = usage_share.share(1, now=now)
    assert s.stale and s.points == pytest.approx(3.6) and s.remainder == pytest.approx(-1.6)
    out = usage_share.format_share(s)
    assert "me    !   3.60" in out and "looks stale; run budget calibrate" in out and "my share" not in out
    assert max(len(l) for l in out.splitlines()) <= 60
    _write([_sample(now - 30, 42.6)])  # 3.6 is not above 2.6 + 1: no mark
    assert not usage_share.share(1, now=now + 6).stale


def test_budget_calibrate_records_and_dry_run_records_nothing(capsys):
    end = _hour_end()
    _write(_hours([(4e7, 2.0)] * 6, end))
    n = lambda: len(list(read_events(reverse=False, scope="all", only=usage_share.CALIBRATION_EVENT)))
    _main(["budget", "calibrate", "--dry-run"])
    out = capsys.readouterr().out
    assert out.startswith("calibrated rate") and "dry run: nothing recorded" in out and n() == 0
    assert "windows considered" in out and "(6h)" in out
    _main(["budget", "calibrate"])
    assert "recorded as usage_rate_calibrated" in capsys.readouterr().out and n() == 1
    assert math.isclose(usage_share.calibration().rate, (12.0 + 1.0) / (6 * 4e7))


def test_with_no_usable_window_calibrate_says_why_and_records_nothing(capsys):
    _write([_metered(time.time() - 600, 5e6)])
    _main(["budget", "calibrate"])
    out = capsys.readouterr().out
    assert out.startswith("no calibration: no window") and "provisional rate 4.08e-08" in out
    assert not list(read_events(reverse=False, scope="all", only=usage_share.CALIBRATION_EVENT))


# ── the share and its views ───────────────────────────────────────────────────

def test_share_without_samples_or_calibration_labels_the_constant_and_leaves_the_remainder_unknown():
    now = time.time()
    _write([_metered(now - 600, 1e6)])
    s = usage_share.share(10, now=now)
    assert s.rate_source == "provisional" and s.rate == P and s.read_weight is None
    assert s.account is None and s.remainder is None and not s.stale
    assert "unknown" in usage_share.format_share(s)


def test_account_movement_uses_the_sample_before_the_window_and_skips_resets():
    now = _hour_end() - 3 * 86400 + 900
    rows = [_sample(now - 4 * HOUR, 10.0), _sample(now - 2.5 * HOUR, 12.0),
            _sample(now - 1.5 * HOUR, 3.0), _sample(now - 0.5 * HOUR, 5.0)]
    inside = [_metered(now - 3 * HOUR + 60, 1e6), _metered(now - 600, 2e6), _metered(now - 600 + 1, 3e6),
              _metered(now - 3 * HOUR - 60, 9e9)]  # the last is just outside
    _write(rows + inside)
    cal = usage_share.Calibration(rate=1e-7, read_weight=0.1, at=now)
    s = usage_share.share(3, now=now, cal=cal)
    assert s.account == 4.0  # 10->12 (+2), 12->3 reset (0), 3->5 (+2)
    assert s.weighted_tokens == 6e6
    assert math.isclose(s.points, 0.6) and math.isclose(s.remainder, 3.4)
    assert usage_share.share(now=now, cal=cal).window_h == 24.0
    _clear()
    _write([_sample(now - 600, 40.0), _metered(now - 300, 1e6)])
    assert usage_share.share(2, now=now).account is None  # one sample is no movement


def test_points_use_the_calibrations_read_weight_in_share_and_on_the_hook_line():
    now = time.time()
    _write([_calibrated(now - 86400, 1e-7, read_weight=0.005), _metered_rows(now - 600, rest=1e6, reads=1e8)])
    s = usage_share.share(1, now=now)
    assert math.isclose(s.weighted_tokens, 1e6 + 0.005 * 1e8) and s.read_weight == 0.005
    assert usage_share.hook_suffix(now) == f"· me {_fmt(1e-7 * (1e6 + 0.005 * 1e8))}%/1h"


def test_an_event_spanning_the_window_edge_counts_only_its_share_inside():
    now = _hour_end() - 3 * 86400 + 900
    # calls evenly from 90 to 30 minutes ago: half of them fell in the last hour
    _write([_metered_rows(now - 1800, rest=4e6, first=now - 5400)])
    cal = usage_share.Calibration(rate=1e-7, read_weight=0.1, at=now)
    assert math.isclose(usage_share.share(1, now=now, cal=cal).weighted_tokens, 2e6)
    assert math.isclose(usage_meter.summarize(now - HOUR).calls, 0.5)
    assert math.isclose(usage_share.share(2, now=now, cal=cal).weighted_tokens, 4e6)


def test_the_views_print_exactly_this():
    s = usage_share.Share(window_h=24, weighted_tokens=1e8, rate=4.5e-8, rate_source="calibrated", points=4.5,
                          account=12.0, remainder=7.5, read_weight=0.1)
    assert usage_share.format_share(s) == (
        "share, last 24h (calibrated)\n  me        4.50\n  account  12.00\n"
        "  others    7.50\n  my share 38%\n  me is an upper bound: rate = min of upper bounds\n"
        "  cache read weight 0.1\n  others = other agents + unmetered use")
    unknown = usage_share.Share(window_h=6, weighted_tokens=1e6, rate=P, rate_source="provisional", points=0.04,
                                account=None, remainder=None)
    assert usage_share.format_share(unknown) == (
        "share, last 6h (provisional rate)\n  me        0.04\n"
        "  account unknown (too few samples)\n  others  unknown\n  others = other agents + unmetered use")
    flat = usage_share.Share(**{**unknown.__dict__, "account": 0.0, "remainder": -0.04})
    assert "my share" not in usage_share.format_share(flat)  # no division by a zero account


def test_budget_me_prints_the_share_lines():
    now = time.time()
    _write([_calibrated(now - 86400, 5e-8), _metered(now - 600, 1e6), _sample(now - 3000, 30.0),
            _sample(now - 60, 31.0)])
    out = usage_meter.run_me("10h")
    assert "\n\nshare, last 10h (calibrated " in out and "others" in out and "me " in out
    assert max(len(l) for l in out.splitlines()) <= 60


# ── the hook line ─────────────────────────────────────────────────────────────

def test_hook_suffix_shows_with_recent_events_and_ignores_old_ones():
    now = time.time()
    assert usage_share.hook_suffix(now) is None
    _write([_metered(now - 3 * HOUR, 9e9), _metered(now - 5400, 5e6)])  # old: must not count
    assert usage_share.hook_suffix(now) is None
    _write([_metered(now - 600, 5e6)])
    assert usage_share.hook_suffix(now) == f"· me ~{_fmt(5e6 * P)}%/1h"
    z = now + 10 * HOUR
    _write([_metered(z - 10, 0)])
    assert usage_share.hook_suffix(z) is None  # tokens of zero show nothing


def _boundary(t):
    return {"timestamp": t, "event": "compaction_detected", "data": {}}


def test_reads_cross_a_cycle_boundary_and_honour_now():
    far = _hour_end() - 4 * 86400
    _write([_calibrated(far - 86400, 1e-7), _metered(far + 1, 1e6), _boundary(far + 2), _metered(far + 3, 1e6)])
    assert usage_share.hook_suffix(far + 4) == f"· me {_fmt(2e6 * 1e-7)}%/1h"
    assert usage_share.share(1, now=far + 4).weighted_tokens == 2e6
    assert usage_share.hook_suffix() is None and usage_share.share(1).weighted_tokens == 0
    _write([_calibrated(far + 100, 3e-7)])  # written after `now`: not yet in force at it
    assert usage_share.calibration(far + 4).rate == 1e-7


@pytest.mark.parametrize("data,expect", [
    ({"last_ts": "2026-11-22T10:00:00Z"}, datetime(2026, 11, 22, 10, tzinfo=timezone.utc).timestamp()),
    ({"last_ts": "2026-11-22T10:00:00+00:00"}, datetime(2026, 11, 22, 10, tzinfo=timezone.utc).timestamp()),
    ({"last_ts": "not a time"}, 77.0),
    ({}, 77.0),
])
def test_event_time_prefers_last_ts_and_falls_back_loudly(data, expect, capsys):
    assert usage_meter.event_span({"timestamp": 77, "data": data}) == (expect, expect)
    assert ("unreadable call time" in capsys.readouterr().err) == (data.get("last_ts") == "not a time")


def test_an_unreadable_calibration_falls_back_to_the_provisional_rate_loudly(capsys):
    now = time.time()
    _write([{"timestamp": now - 100, "event": usage_share.CALIBRATION_EVENT, "data": {"rate": 1e-7}},
            _metered(now - 50, 5e6)])
    assert usage_share.hook_suffix(now) == f"· me ~{_fmt(5e6 * P)}%/1h"
    assert "unreadable calibration" in capsys.readouterr().err


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


def _with_metering_since(t, since, calls=5):
    ev = _metered(t, 2e6)
    ev["data"]["metering_since"] = since
    ev["data"]["calls"] = calls
    return ev


def test_part_marks_a_short_or_thin_hour_and_survives_the_rolled_event():
    now = time.time()
    _write([_with_metering_since(now - 300, now - 4 * 3600)])
    assert not usage_share.hook_suffix(now).endswith(usage_share.PARTIAL_MARK)  # a fully metered hour
    _write([_with_metering_since(now - 200, now - 600)])  # the earliest metering_since decides
    assert not usage_share.hook_suffix(now).endswith(usage_share.PARTIAL_MARK)
    _clear()
    _write([_with_metering_since(now - 300, now - 4 * 3600, calls=1)])
    assert usage_share.hook_suffix(now).endswith(usage_share.PARTIAL_MARK)  # one call is a sample
    _clear()
    _write([_with_metering_since(now - 300, now - 600)])
    assert usage_share.hook_suffix(now).endswith(usage_share.PARTIAL_MARK)  # metering ten minutes old
    assert usage_share.roll(now) is True
    rolled = [e["data"] for e in read_events(reverse=False, scope="all", only=usage_share.ROLLED_EVENT)]
    assert rolled[-1]["partial"] is True and rolled[-1]["calibration"] is None
    assert usage_share.hook_suffix(now + 5).endswith(usage_share.PARTIAL_MARK)


# ── step windows and the mark's wording ───────────────────────────────────────

TRUE_RATE = 5e-8


def _steady(begin, gaps, per_gap=6e6, c0=10.05, gap=600.0):
    """This agent alone on the account: ``per_gap`` tokens mid-way through each ``gap``-second gap, the
    true counter rising by ``per_gap * TRUE_RATE`` a gap from ``c0``, read as its floor at every sample."""
    rows = []
    for k in range(gaps + 1):
        rows.append(_sample(begin + k * gap, float(math.floor(round(c0 + k * per_gap * TRUE_RATE, 9)))))
        if k < gaps:
            rows.append(_metered(begin + k * gap + gap / 2, per_gap))
    return rows


def test_a_step_window_bounds_the_rate_tighter_than_the_whole_hours_and_the_minimum_takes_it():
    """Alone on the account at a true 5e-8 points a token, read every ten minutes as a whole percent.
    Every window's bound holds (none falls below the true rate), the step windows come closer to it
    than any whole-hour window, and the calibration is theirs. The trace is kind to the whole hours,
    whose best lands within about 1% of the truth; on real traces they come out far looser."""
    end = _hour_end() - 86400
    begin = end - 13 * HOUR
    _write(_steady(begin, 78))
    lookback_start = end - usage_share.LOOKBACK_DAYS * 24 * HOUR
    hour = usage_share._hour_windows(lookback_start, usage_share.LOOKBACK_DAYS * 24, end + 60)
    step = usage_share._step_windows(lookback_start, end + 60)
    assert TRUE_RATE <= step.bound < hour.bound
    c = usage_share.envelope(end + 60).calibration
    assert c.rate == step.bound and c.window["kind"] == "step"
    assert c.windows == hour.considered + step.considered
    assert usage_share.format_calibration(usage_share.CalibrationAttempt(calibration=c), False).splitlines()[1] \
        .startswith("  set by a step window, ")


def test_a_step_window_ends_before_the_closing_step_up_and_counts_the_end_reading_plus_one():
    """Readings 10, 11 (a step-up), 11, 11, 12 (a step-up), half an hour apart. The step window runs
    from the first 11 to the last 11, so the 5e6 tokens in the gap where the counter stepped to 12 are
    not in it, and its bound is (11 + 1 - 11) / 2e7: the end reading plus one, nothing more."""
    end = _hour_end() - 86400
    t = [end - 2 * HOUR + k * 1800 for k in range(5)]
    _write([_sample(t[0], 10.0), _sample(t[1], 11.0), _metered(t[1] + 900, 1e7), _sample(t[2], 11.0),
            _metered(t[2] + 900, 1e7), _sample(t[3], 11.0), _metered(t[3] + 900, 5e6), _sample(t[4], 12.0)])
    c = usage_share.envelope(end + 60).calibration
    assert c.window == {"kind": "step", "start": t[1], "end": t[3], "hours": 1.0, "delta": 0.0, "tokens": 2e7}
    assert c.rate == pytest.approx(1.0 / 2e7)
    hour = usage_share._hour_windows(end - usage_share.LOOKBACK_DAYS * 24 * HOUR,
                                     usage_share.LOOKBACK_DAYS * 24, end + 60)
    assert hour.bound == pytest.approx(3.0 / 2.5e7)  # 10 -> 12 over the two hours: looser


def _over_the_account(now, calibrated_at):
    _write([_calibrated(calibrated_at, 1e-7), _metered_rows(now - 600, rest=3.6e7),  # 3.6 points
            _sample(now - 3000, 40.0), _sample(now - 60, 42.0)])  # the account rose 2


def test_me_above_the_account_soon_after_calibrating_says_the_bound_is_loose_not_stale():
    now = time.time()
    _over_the_account(now, now - 2 * HOUR)
    assert usage_share.hook_suffix(now) == f"· me !{_fmt(3.6)}%/1h"  # the mark stays on the hook line
    out = usage_share.me_lines(1)
    assert "me    !   3.60" in out and "loose for this hour" in out and "upper bound" in out
    assert "recalibrating after heavy hours tightens it" in out and "stale" not in out
    assert max(len(l) for l in out.splitlines()) <= 60


def test_me_above_the_account_long_after_calibrating_says_the_calibration_looks_stale():
    now = time.time()
    _over_the_account(now, now - (usage_share.LOOSE_WITHIN_H + 1) * HOUR)
    assert usage_share.hook_suffix(now) == f"· me !{_fmt(3.6)}%/1h"
    out = usage_share.me_lines(1)
    assert "looks stale; run budget calibrate" in out and "loose" not in out


# ── falls inside a window, refused bounds, the next window and the sanity band ──

@pytest.mark.parametrize("readings,odd", [
    # a stale low reading: 37, 37, 36, 37 at samples 7 to 10
    ([35, 36, 36, 36, 36, 37, 37, 37, 37, 36, 37, 37, 37, 37, 38], 9),
    # a weekly reset whose samples carry no resets_at
    ([90, 91, 91, 91, 91, 92, 92, 92, 92, 0, 1, 1, 1, 1, 2], 9),
])
def test_a_fall_of_the_counter_inside_a_step_window_breaks_it_without_a_reset_time(readings, odd):
    """Samples every 20 minutes, none with a reset time, 2e6 tokens in each gap. Without the fall check a
    step window from the second step-up to the sample at ``odd`` ends below its start, bound at or below
    zero. With it, no window spans that sample and the calibration is the 1h window of delta 0."""
    end = _hour_end() - 86400
    begin = end - 5 * HOUR
    t = [begin + k * 1200 for k in range(len(readings))]
    rows = [_sample(tk, float(v)) for tk, v in zip(t, readings, strict=True)]
    rows += [_metered(tk + 600, 2e6) for tk in t[:-1]]
    _write(rows)
    step = usage_share._step_windows(end - usage_share.LOOKBACK_DAYS * 24 * HOUR, end + 60)
    assert step.windows and all(not (w["start"] <= t[odd] <= w["end"]) for w in step.windows)
    att = usage_share.envelope(end + 60)
    assert att.refused == () and att.calibration.rate == pytest.approx(1.0 / 6e6)
    w = att.calibration.window
    assert w["kind"] == "step" and w["delta"] == 0.0 and not (w["start"] <= t[odd] <= w["end"])


def _win(start, end, bound, kind="hour", delta=1.0, tokens=1e7):
    return {"kind": kind, "start": start, "end": end, "hours": (end - start) / HOUR, "delta": delta,
            "tokens": tokens, "bound": bound}


def _windows(monkeypatch, hour=(), step=()):
    monkeypatch.setattr(usage_share, "_hour_windows", lambda *a: usage_share._Windows(windows=tuple(hour)))
    monkeypatch.setattr(usage_share, "_step_windows", lambda *a: usage_share._Windows(windows=tuple(step)))


def test_the_envelope_refuses_a_bound_at_or_below_zero_names_it_and_never_returns_one(monkeypatch):
    now = _hour_end() - 86400
    zero = _win(now - 5 * HOUR, now - 4 * HOUR, 0.0, delta=-1.0)
    below = _win(now - 3 * HOUR, now - 2 * HOUR, -1e-7, kind="step", delta=-2.0)
    good = _win(now - 9 * HOUR, now - 8 * HOUR, 5e-8)
    _windows(monkeypatch, hour=[zero, good], step=[below])
    att = usage_share.envelope(now)
    assert att.calibration.rate == 5e-8 and att.calibration.windows == 3
    assert att.refused == (zero, below)
    out = usage_share.format_calibration(att, False)
    assert "refused 2 window(s) with a bound at or below zero" in out
    assert "a hour window" in out and "account -1," in out and "a step window" in out and "account -2," in out
    _windows(monkeypatch, hour=[zero], step=[below])
    att = usage_share.envelope(now)
    assert att.calibration is None and "at or below zero" in att.reason and len(att.refused) == 2
    out = usage_share.format_calibration(att, False)
    assert out.startswith("no calibration: all 2 windows have a bound at or below zero")
    assert "account -1," in out and "provisional rate" in out


def test_calibrate_reports_and_records_the_tightest_window_not_overlapping_the_chosen_one(monkeypatch):
    """The chosen window spans 0 to 2h; one at 1 to 3h is tighter than the third but overlaps it, so
    the next tightest is the window at 3 to 4h, which touches the chosen one without overlapping."""
    now = _hour_end() - 86400
    s = now - 10 * HOUR
    chosen, overlapping = _win(s, s + 2 * HOUR, 4e-8), _win(s + HOUR, s + 3 * HOUR, 4.4e-8, kind="step")
    apart = _win(s + 2 * HOUR, s + 3 * HOUR, 8e-8)
    _windows(monkeypatch, hour=[chosen, apart], step=[overlapping])
    out = usage_share.calibrate(dry_run=False, now=now)
    assert out.recorded and not out.refused
    assert "next tightest window not overlapping it: rate 8e-08, 2x the chosen" in out.text
    ev = list(read_events(reverse=False, scope="all", only=usage_share.CALIBRATION_EVENT))[-1]["data"]
    assert ev["runner_up"] == {**usage_share._bare(apart), "rate": 8e-8}
    assert usage_share.calibration().runner_up["rate"] == 8e-8
    _windows(monkeypatch, hour=[chosen], step=[overlapping])
    assert "no other window that does not overlap it" in usage_share.run_calibrate(dry_run=True, now=now)


@pytest.mark.parametrize("factor,refused", [(5.0, True), (1 / 5.0, True), (3.9, False), (1 / 3.9, False)])
def test_calibrate_refuses_a_rate_outside_a_factor_of_four_of_the_provisional_constant(monkeypatch, factor, refused):
    now = time.time()
    _windows(monkeypatch, hour=[_win(now - 5 * HOUR, now - 4 * HOUR, P * factor)])
    n = lambda: len(list(read_events(reverse=False, scope="all", only=usage_share.CALIBRATION_EVENT)))
    dry = usage_share.calibrate(dry_run=True)
    assert dry.refused is refused and not dry.recorded and n() == 0
    assert ("a real run would be refused" in dry.text) is refused and dry.text.startswith("calibrated rate")
    assert (f"outside the band of {usage_share.SANITY_FACTOR:g}x" in dry.text) is refused
    from macf.cli import main
    with pytest.raises(SystemExit) as e:
        main(["budget", "calibrate"])
    assert (e.value.code == 1) is refused and n() == (0 if refused else 1)
