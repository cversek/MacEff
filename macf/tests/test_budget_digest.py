"""The hourly spend digest, the sprint budget records and the mode line.

Events are synthetic, written straight into the isolated log with chosen timestamps.
"""

import json
import time

import pytest

from macf import budget, budget_digest, usage_meter
from macf.agent_events_log import get_log_path, read_events

P = usage_meter.POINTS_PER_WEIGHTED_TOKEN
HOUR = 3600.0
RESET = "2099-01-01T00:00:00+00:00"


def _write(rows):
    with open(get_log_path(), "a") as f:
        for r in sorted(rows, key=lambda r: r["timestamp"]):
            f.write(json.dumps({**r, "hook_input": {}}) + "\n")


def _metered(t, calls=10, cause="operator", **tokens):
    row = {"input_tokens": 0, "cache_read_input_tokens": 400_000, "output_tokens": 0, **tokens, "calls": calls}
    return {"timestamp": t, "event": usage_meter.EVENT,
            "data": {"by_model": {"m": row}, "calls": calls, "cause": cause}}


def _sample(t, pct):
    return {"timestamp": t, "event": "budget_sampled",
            "data": {"source": "endpoint",
                     "limits": [{"kind": "weekly_all", "percent": pct, "resets_at": RESET,
                                "scope": None, "severity": "normal"}]}}


def _events(name):
    return list(read_events(reverse=False, scope="all", only=name))


def test_digest_appears_once_per_hour_when_there_is_new_spend():
    now = time.time()
    _write([_metered(now - 600, cause="operator"), _metered(now - 500, cause="cron"), _sample(now - 60, 40)])
    first = budget_digest.digest(now)
    assert first and "last hour" in first and "by cause" in first
    assert max(len(l) for l in first.splitlines()) <= 60
    assert budget_digest.digest(now + 60) is None  # inside the hour
    later = now + HOUR + 120
    _write([_metered(later - 300)])
    assert budget_digest.digest(later)  # an hour on, with new spend
    assert len(_events(budget_digest.DIGEST_EVENT)) == 2


def test_no_digest_when_nothing_was_metered():
    now = time.time()
    assert budget_digest.digest(now) is None
    baseline = _metered(now - 100, calls=0)  # a baseline event meters nothing
    baseline["data"]["by_model"] = {}
    _write([baseline, _metered(now - 3 * HOUR)])  # and old spend is not this hour's
    assert budget_digest.digest(now) is None
    assert _events(budget_digest.DIGEST_EVENT) == []


def test_the_largest_driver_is_context_times_turns():
    now = time.time()
    _write([_metered(now - 600, calls=10)])  # 400k read per 10 calls: 40k each
    text = budget_digest.digest(now)
    assert "driver: context × turns, 40k × 10 (" in text
    other = now + 2 * HOUR
    _write([_metered(other - 600, calls=2, cache_read_input_tokens=1000, output_tokens=500_000)])
    assert "driver: output," in budget_digest.digest(other)


def test_the_cost_of_one_more_turn_uses_the_latest_call():
    now = time.time()
    _write([_metered(now - 900, calls=10),
            _metered(now - 100, calls=2, input_tokens=200, cache_read_input_tokens=80_000, output_tokens=400)])
    # latest call: 100 in, 40k read, 200 out -> 100 + 4000 + 1000 weighted
    expect = budget.format_rate(5100 * P)
    text = budget_digest.digest(now)
    assert f"one more turn at 40k context: ~{expect}" in text


def test_sprint_start_and_end_events_carry_the_deltas():
    now = time.time()
    _write([_sample(now - 60, 50), _metered(now - 3000)])
    start_line = budget_digest.sprint_started("77", now)
    assert "week 50%" in start_line
    start = _events(budget_digest.START_EVENT)[0]["data"]
    assert start["task_id"] == "77" and start["percent"] == 50 and start["resets_at"] == RESET
    end_now = now + 1800
    _write([_metered(now + 900, calls=10), _sample(end_now - 60, 53)])
    end_line = budget_digest.sprint_ended("77", end_now)
    end = _events(budget_digest.END_EVENT)[0]["data"]
    assert end["account_points_delta"] == pytest.approx(3.0)
    assert end["agent_points_delta"] == pytest.approx(40_000 * P, rel=1e-6)
    assert "account +3" in end_line


def test_the_mode_line_says_who_set_it_and_when(monkeypatch):
    monkeypatch.setattr("macf.utils.identity.get_agent_identity", lambda: "Card@abc123")
    now = time.time()
    _write([_sample(now - 60, 40)])
    budget.set_mode("conserve")
    st = budget.status(now + 5)
    text = budget.mode_text(st["mode"])
    assert text.startswith("conserve, set ") and text.endswith("by Card@abc123")
    assert text in budget.format_status(st, brief=True)
    assert f"budget mode: {text}" in budget.format_status(st)


def test_a_lapsed_mode_is_shown_with_its_date():
    now = time.time()
    _write([_sample(now - 60, 40),
            {"timestamp": now - 9 * 86400, "event": "budget_mode_set",
             "data": {"mode": "conserve", "target": None, "by": None, "scope": None}}])
    st = budget.status(now, detail=True)
    assert st["lapsed"]["mode"] == "conserve"
    assert "conserve lapsed (set " in budget.format_status(st, brief=True)
