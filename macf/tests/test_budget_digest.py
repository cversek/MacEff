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
    assert text.startswith("conserve, set by Card@abc123 at ") and len(text.rsplit(" ", 1)[1]) == 5
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


# ── the CLI paths ─────────────────────────────────────────────────────────────

def _sprint_args():
    import argparse
    return argparse.Namespace(title="t", goal=None, scoped=None, children=None, parent=None, repo=None,
                              no_auto_start=False, json=False, timer=None)


def _fake_created(monkeypatch):
    monkeypatch.setattr("macf.task.create.create_sprint", lambda **kw: {
        "task_id": 91, "ca_path": "x.md", "scope": [], "auto_start_completed": True})


def test_task_create_sprint_records_and_prints_the_budget_line(monkeypatch, capsys):
    from macf.cli import cmd_task_create_sprint
    _write([_sample(time.time() - 60, 44)])
    _fake_created(monkeypatch)
    assert cmd_task_create_sprint(_sprint_args()) == 0
    out = capsys.readouterr().out
    assert "budget at start: week 44%" in out
    assert _events(budget_digest.START_EVENT)[0]["data"]["task_id"] == "91"


def test_a_budget_failure_does_not_block_sprint_create(monkeypatch, capsys):
    from macf.cli import cmd_task_create_sprint
    _fake_created(monkeypatch)
    monkeypatch.setattr("macf.budget.samples", lambda **kw: (_ for _ in ()).throw(OSError("log unreadable")))
    assert cmd_task_create_sprint(_sprint_args()) == 0
    cap = capsys.readouterr()
    assert "Created SPRINT task #91" in cap.out
    assert "sprint budget start not recorded for #91" in cap.err and "log unreadable" in cap.err


def _complete(tmp_path, notes, task_type="SPRINT", note_ok=True):
    from contextlib import ExitStack
    from unittest.mock import patch
    from macf.cli import cmd_task_complete
    from test_task_complete_smart import _make_args, _make_fake_task, _make_reader, _std_patches
    sprint = _make_fake_task(42, task_type=task_type, custom={"goal": "g"})
    patches = _std_patches(_make_reader(sprint, [], tmp_path))
    patches.append(patch("macf.task.reader.add_task_note",
                          lambda *a, **kw: notes.append({"args": a, "kw": kw}) or note_ok))
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return cmd_task_complete(_make_args(42, report="done"))


def test_task_complete_records_prints_and_notes_the_sprint_budget(tmp_path, capsys):
    now = time.time()
    _write([_sample(now - 60, 50)])
    budget_digest.sprint_started("42", now)
    _write([_sample(now + 1, 52), _metered(now + 2, calls=10)])
    notes = []
    assert _complete(tmp_path, notes) == 0
    out = capsys.readouterr().out
    assert "sprint budget: account +2" in out
    end = _events(budget_digest.END_EVENT)[0]["data"]
    assert end["task_id"] == "42" and end["account_points_delta"] == pytest.approx(2.0)
    assert len(notes) == 1 and notes[0]["kw"]["agent"] == "PA"
    assert notes[0]["args"][0] == "42"
    assert notes[0]["args"][1].startswith("sprint budget: account +2 points, me +")
    assert notes[0]["args"][1].endswith("points metered") and "💳" not in notes[0]["args"][1]


def test_a_budget_failure_does_not_block_sprint_complete(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("macf.budget.samples", lambda **kw: (_ for _ in ()).throw(OSError("log unreadable")))
    assert _complete(tmp_path, []) == 0
    cap = capsys.readouterr()
    assert "marked complete" in cap.out
    assert "sprint budget end not recorded for #42" in cap.err


# ── wiring, bounds and edges ──────────────────────────────────────────────────

def test_the_prompt_notice_carries_the_digest_once():
    now = time.time()
    _write([_sample(now - 60, 40), _metered(now - 600)])
    text = budget.prompt_notice(now)
    assert text and "spend, last hour" in text
    assert budget.prompt_notice(now + 60) is None


def test_the_end_delta_across_a_weekly_reset_is_unknown_not_negative():
    now = time.time()
    _write([_sample(now - 60, 90)])
    budget_digest.sprint_started("5", now)
    later = now + 1800
    sample = _sample(later - 60, 3)
    sample["data"]["limits"][0]["resets_at"] = "2099-02-01T00:00:00+00:00"
    _write([sample, _metered(now + 900, calls=10)])
    budget_digest.sprint_ended("5", later)
    end = _events(budget_digest.END_EVENT)[0]["data"]
    assert end["account_points_delta"] is None
    assert end["agent_points_delta"] == pytest.approx(40_000 * P, rel=1e-6)


def test_the_snapshot_counts_only_this_weeks_metered_points():
    import datetime as dt
    now = time.time()
    reset = dt.datetime.fromtimestamp(now + 5 * 86400, tz=dt.timezone.utc).isoformat()  # the week began 2 days ago
    s = _sample(now - 60, 40)
    s["data"]["limits"][0]["resets_at"] = reset
    _write([s, _metered(now - 3 * 86400), _metered(now - 86400)])
    snap = budget_digest._snapshot(now)
    assert snap["agent_points"] == pytest.approx(40_000 * P, rel=1e-6)


def test_current_rate_is_the_newest_calibration_however_old():
    now = time.time()
    assert not budget_digest.current_rate(now).calibrated
    cal = {"rate": 1e-6, "read_weight": 0.1, "method": "lower_envelope", "at": now - 9 * 86400}
    _write([{"timestamp": now - 9 * 86400, "event": "usage_rate_calibrated", "data": cal},
            {"timestamp": now - 8 * 86400, "event": "usage_rate_calibrated", "data": {**cal, "rate": 2e-6}}])
    rate = budget_digest.current_rate(now)
    assert rate.calibrated and rate.value == 2e-6 and rate.read_weight == 0.1


def test_the_digest_names_exactly_the_top_three_causes():
    now = time.time()
    _write([_metered(now - 500, cause="operator", cache_read_input_tokens=400_000),
            _metered(now - 400, cause="cron", cache_read_input_tokens=300_000),
            _metered(now - 300, cause="peer", cache_read_input_tokens=200_000),
            _metered(now - 200, cause="notice", cache_read_input_tokens=100_000)])
    line = next(l for l in budget_digest.digest(now).splitlines() if "by cause" in l)
    assert all(c in line for c in ("operator", "cron", "peer")) and "notice" not in line


def test_the_lapse_lookup_is_bounded_by_two_weekly_windows(monkeypatch):
    seen = []
    real = budget.read_events
    monkeypatch.setattr(budget, "read_events", lambda *a, **kw: seen.append(kw.get("since")) or real(*a, **kw))
    now = time.time()
    _write([{"timestamp": now - 20 * 86400, "event": "budget_mode_set",
             "data": {"mode": "conserve", "target": None, "by": None, "scope": None}}])
    assert budget.lapsed_mode(now) is None  # too old to announce
    assert seen and all(s is not None and s >= now - 2 * budget.HISTORY.total_seconds() - 1 for s in seen)


def test_completing_a_task_that_is_not_a_sprint_records_nothing(tmp_path, capsys):
    notes = []
    assert _complete(tmp_path, notes, task_type="TASK") == 0
    assert _events(budget_digest.END_EVENT) == [] and notes == []
    assert "sprint budget" not in capsys.readouterr().out


def test_a_refused_note_warns_and_the_event_stands(tmp_path, capsys):
    now = time.time()
    _write([_sample(now - 60, 50)])
    assert _complete(tmp_path, [], note_ok=False) == 0
    assert "sprint budget note not added to #42" in capsys.readouterr().err
    assert len(_events(budget_digest.END_EVENT)) == 1


def test_the_json_output_of_sprint_create_stays_json(monkeypatch, capsys):
    from macf.cli import cmd_task_create_sprint
    _fake_created(monkeypatch)
    args = _sprint_args()
    args.json = True
    assert cmd_task_create_sprint(args) == 0
    assert json.loads(capsys.readouterr().out)["task_id"] == 91
    assert len(_events(budget_digest.START_EVENT)) == 1


def test_the_digest_numbers_are_exact():
    now = time.time()
    _write([_metered(now - 600, calls=4, cause="operator", input_tokens=1000, cache_read_input_tokens=200_000,
                     output_tokens=100, cache_write_1h_tokens=500),
            _metered(now - 300, calls=6, cause="cron", cache_read_input_tokens=3_000_000, output_tokens=12_000,
                     cache_write_5m_tokens=1000)])
    # weighted: operator 1000 + 20000 + 500 + 1000 = 22500; cron 300000 + 60000 + 1250 = 361250
    # cache read is 320000 of 383750 (83%) over 10 calls; the newest call averages 500k read,
    # 2000 out and 166.7 written
    assert budget_digest.digest(now).splitlines() == [
        f"💳 spend, last hour: {budget.format_rate(383750 * P)} points, 10 calls",
        f"  by cause: cron {budget.format_rate(361250 * P)}, operator {budget.format_rate(22500 * P)}",
        "  driver: context × turns, 320k × 10 (83% of points)",
        "  share: account movement unknown",
        f"  one more turn at 500k context: ~{budget.format_rate((50000 + 10000 + 1000 / 6 * 1.25) * P)}",
    ]
    ev = _events(budget_digest.DIGEST_EVENT)[0]["data"]
    assert ev["points"] == pytest.approx(383750 * P) and ev["calls"] == 10


def test_the_prompt_notice_without_samples_is_the_digest_alone():
    now = time.time()
    assert budget.prompt_notice(now) is None
    _write([_metered(now - 600)])
    text = budget.prompt_notice(now)
    assert text.startswith("💳 spend") and "budget:" not in text


def test_the_prompt_notice_joins_the_line_before_the_digest():
    now = time.time()
    _write([_sample(now - 60, 60)])
    only_line = budget.prompt_notice(now)
    assert only_line.startswith("💳 budget:") and "spend" not in only_line
    _write([_sample(now - 30, 75), _metered(now - 600)])
    both = budget.prompt_notice(now)
    first, rest = both.split("\n", 1)
    assert first.startswith("💳 budget:") and rest.startswith("💳 spend, last hour")
    _write([_sample(now - 10, 75)])
    assert budget.prompt_notice(now + 60) is None  # the band was shown and the digest sent


def test_a_failing_digest_leaves_the_notice_and_warns(monkeypatch, capsys):
    now = time.time()
    _write([_sample(now - 60, 60)])
    monkeypatch.setattr(budget_digest, "digest", lambda n: (_ for _ in ()).throw(OSError("log unreadable")))
    text = budget.prompt_notice(now)
    assert text.startswith("💳 budget:") and "\n" not in text
    assert "spend digest skipped" in capsys.readouterr().err


def _start(t, task, pct, reset=RESET):
    return {"timestamp": t, "event": budget_digest.START_EVENT,
            "data": {"task_id": task, "percent": pct, "resets_at": reset, "agent_points": 0.0}}


def test_a_missing_start_records_the_end_without_deltas(capsys):
    now = time.time()
    _write([_sample(now - 60, 50), _start(now - 600, "8", 10)])  # another task's start does not count
    line = budget_digest.sprint_ended("9", now)
    end = _events(budget_digest.END_EVENT)[0]["data"]
    assert end["account_points_delta"] is None and end["agent_points_delta"] is None
    assert "no start record for #9" in capsys.readouterr().err
    assert "account unknown" in line and "me unknown" in line


def test_the_newest_start_within_thirty_days_is_the_one_used(capsys):
    now = time.time()
    _write([_start(now - 2 * HOUR, "9", 40), _start(now - HOUR, "9", 50), _sample(now - 60, 53)])
    budget_digest.sprint_ended("9", now)
    assert _events(budget_digest.END_EVENT)[0]["data"]["account_points_delta"] == pytest.approx(3.0)
    old = now + 40 * 86400  # a start 40 days back is past the lookup
    budget_digest.sprint_ended("9", old)
    assert _events(budget_digest.END_EVENT)[1]["data"]["account_points_delta"] is None
    assert "no start record" in capsys.readouterr().err


def test_an_unknown_counter_at_either_end_gives_no_account_delta():
    now = time.time()
    _write([_start(now - 600, "9", None)])  # the start had no reading
    budget_digest.sprint_ended("9", now)  # and the end has no sample
    assert _events(budget_digest.END_EVENT)[0]["data"]["account_points_delta"] is None
    _write([_sample(now - 30, 53)])
    budget_digest.sprint_ended("9", now)  # a reading at the end only
    assert _events(budget_digest.END_EVENT)[1]["data"]["account_points_delta"] is None

