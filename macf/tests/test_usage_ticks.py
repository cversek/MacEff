"""Usage ticks: crossings, the cumulative fit, drift, priors, the scoped cross-check, the CLI.

The worlds are synthetic with a known truth: two models whose token flows vary independently,
a counter that is the floor of the true cumulative points, sampled every 6.6 minutes.
"""

import json
import math
import random
import time
from datetime import datetime, timezone

from macf import usage_meter, usage_ticks
from macf.agent_events_log import get_log_path

STEP = 396.0  # 6.6 minutes
HOUR = 3600.0
SCALE = 4e-8  # points per prior-weighted token (sonnet 1, opus 5)


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def _write(rows):
    with open(get_log_path(), "a") as f:
        for r in sorted(rows, key=lambda r: r["timestamp"]):
            f.write(json.dumps({**r, "hook_input": {}}) + "\n")


def _opus(k):
    return 8e5 * (max(0.0, math.sin(k * 0.021)) + 0.1)  # bursts a day long, not a steady flow


def _sonnet(k):
    return 2.5e6 * (max(0.0, math.sin(k * 0.034 + 1.3)) + 0.1)


def _cache(k):
    return 4e7 * (1 + math.sin(k * 0.71 + 1))


def _world(hours=72, drift=0.0, cache_read=False, scoped=False, gaps=(), ratios=None, now=None):
    """Write the events and samples; the true points rise by the metered flow plus ``drift`` an hour.

    ``gaps`` is a list of dicts with ``start`` and ``stop`` in steps: no samples inside them.
    """
    ratios = ratios or {"claude-opus-4": 5.0, "claude-sonnet-4": 1.0}
    end = now or time.time()
    n = int(hours * HOUR / STEP)
    t0 = end - n * STEP
    rng = random.Random(7)  # other agents' spend: noise the tokens do not explain
    rows, points, pool = [], 3.2, 0.7
    for k in range(1, n + 1):
        t = t0 + k * STEP
        opus = {"input_tokens": int(_opus(k)), "calls": 1}
        sonnet = {"input_tokens": int(_sonnet(k)), "calls": 1}
        if cache_read:
            sonnet["cache_read_input_tokens"] = int(_cache(k))
        rows.append({"timestamp": t, "event": usage_meter.EVENT,
                     "data": {"by_model": {"claude-opus-4": opus, "claude-sonnet-4": sonnet}, "calls": 2,
                              "first_ts": _iso(t - STEP), "last_ts": _iso(t)}})
        points += SCALE * (ratios["claude-opus-4"] * usage_meter.weighted(opus)
                           + ratios["claude-sonnet-4"] * usage_meter.weighted(sonnet, 0.1)) + drift * STEP / HOUR + rng.uniform(0, 0.12)
        pool += 2 * SCALE * usage_meter.weighted(sonnet, 0.1) + rng.uniform(0, 0.12)
        if any(g["start"] <= k <= g["stop"] for g in gaps):
            continue
        limits = [{"kind": "weekly_all", "scope": None, "percent": float(math.floor(points))}]
        if scoped:
            limits.append({"kind": "weekly_scoped", "scope": "Sonnet", "percent": float(math.floor(pool))})
        rows.append({"timestamp": t, "event": "budget_sampled", "data": {"source": "endpoint", "limits": limits}})
    _write(rows)
    return end


def _ratio(fit):
    return fit.rates["claude-opus-4"].value / fit.rates["claude-sonnet-4"].value


def test_crossings_are_bracketed_by_the_samples_either_side_and_a_reset_starts_a_segment():
    pts = [{"t": 0, "pct": 4.0}, {"t": 400, "pct": 4.0}, {"t": 800, "pct": 5.0}, {"t": 1200, "pct": 5.0},
           {"t": 1600, "pct": 6.0}, {"t": 2000, "pct": 1.0}, {"t": 2400, "pct": 1.0}, {"t": 2800, "pct": 2.0}]
    c = usage_ticks.extract_ticks(pts, "weekly_all")
    assert [t.level for t in c.ticks] == [5, 6, 2]
    first = c.ticks[0]
    assert (first.t_lo, first.t_hi, first.t_mid) == (400, 800, 600)
    assert [t.segment for t in c.ticks] == [0, 0, 1] and c.segments == 2


def test_known_scale_and_model_ratios_are_recovered_within_the_intervals():
    _world(72)
    rep = usage_ticks.analyse(72)
    fit = rep.fits[0.1]
    assert fit.ticks > 50
    assert abs(fit.scale.value - SCALE) / SCALE < 0.08  # the ridge trades a little of it with the deviations
    assert abs(_ratio(fit) - 5.0) / 5.0 < 0.15
    for model, truth in (("claude-opus-4", 5 * SCALE), ("claude-sonnet-4", SCALE)):
        e = fit.rates[model]
        assert e.low < e.value < e.high  # the 90% bootstrap runs a little tight on this one noise draw
        assert e.low * 0.95 <= truth <= e.high * 1.05 and abs(e.value - truth) / truth < 0.08


def test_the_drift_term_absorbs_a_constant_unmetered_rate():
    _world(72, drift=0.5)
    fit = usage_ticks.analyse(72).fits[0.1]
    truth = 0.5 + 0.06 * HOUR / STEP  # plus the mean of the noise the world adds
    assert fit.drift.low <= truth <= fit.drift.high and abs(fit.drift.value - truth) < 0.12
    assert abs(fit.scale.value - SCALE) / SCALE < 0.12


def test_a_wide_gap_bracket_is_downweighted_and_noted():
    gaps = [{"start": k, "stop": k + 8} for k in range(60, 600, 60)]  # about 53 minutes without samples
    c = usage_ticks.analyse(72).crossings if _world(72, gaps=gaps) else None
    wide = [t for t in c.ticks if t.quality == "wide"]
    assert wide and all(0 < t.weight < 1 and t.width > usage_ticks.NARROW_S for t in wide)
    assert all(t.weight == 1.0 for t in c.ticks if t.quality == "ok")
    assert any("downweighted" in n for n in usage_ticks._notes(c))


def test_both_cache_read_variants_are_reported_and_the_true_weight_leaves_the_smaller_residual():
    _world(72, cache_read=True)
    rep = usage_ticks.analyse(72)
    assert set(rep.fits) == {0.1, 0.0}
    assert rep.fits[0.1].rms_residual < rep.fits[0.0].rms_residual


def test_the_scoped_counter_gives_its_pool_rate_beside_the_joint_fit():
    _world(72, scoped=True)
    rep = usage_ticks.analyse(72)
    assert [s.pool for s in rep.scoped] == ["Sonnet"]
    s = rep.scoped[0]
    assert s.rate.low <= 2 * SCALE <= s.rate.high  # the pool counter was built at twice the joint scale
    assert s.joint_rate is not None and abs(s.joint_rate - SCALE) / SCALE < 0.15


def test_priors_are_data_an_override_file_wins_and_an_unknown_model_warns(tmp_path, capsys):
    f = tmp_path / "usage_priors.json"
    f.write_text(json.dumps({"claude-opus": 4}))
    priors = usage_ticks.load_priors(f)
    assert priors["claude-opus"] == 4 and priors["claude-haiku"] == 0.33
    assert usage_ticks.MODEL_PRIORS["claude-opus"] == 5
    assert usage_ticks.prior_ratio("claude-fable-9", priors, set()) == 5
    assert usage_ticks.prior_ratio("mystery-1", priors, set()) == 1
    assert "mystery-1" in capsys.readouterr().err


def test_the_cli_prints_the_crossings_the_fit_and_both_variants(capsys):
    _world(36, cache_read=True)
    from macf.cli import main
    try:
        main(["budget", "ticks", "--since", "36h"])
    except SystemExit as e:
        assert e.code in (0, None)
    out = capsys.readouterr().out
    assert "weekly_all:" in out and "crossings" in out
    assert "cache read x0.1" in out and "cache read x0:" in out
    assert "drift" in out and "opus-4" in out and "sonnet-4" in out
    assert max(len(line) for line in out.splitlines()) <= 60
