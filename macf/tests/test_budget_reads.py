"""What the budget hooks read from the event log (#1127).

The prompt and tool-call hooks run budget code on every turn, against a log of hundreds of megabytes. A read that
stops only when it finds an event walks the whole window when the event is absent, so each hook path is checked for
how far back it reads, not only for what it answers. Events are written straight into the isolated log.
"""

import time

import pytest

from macf import budget
from test_budget_digest import RESET, _sample, _write

HOUR = 3600.0
DAY = 86400.0


@pytest.fixture
def reads(monkeypatch, isolated_events_log):
    """Every read_events call the budget module makes, as ``(only, since)`` with the clock's now to compare."""
    seen = []
    real = budget.read_events

    def watch(*args, **kw):
        seen.append((tuple(kw.get("only") or ()), kw.get("since")))
        for e in real(*args, **kw):
            YIELDED.append(e.get("event"))
            yield e
    YIELDED.clear()
    monkeypatch.setattr(budget, "read_events", watch)
    return seen


#: The event names every watched read handed back, so a test can tell a read that stopped at the first match
#: from one that went on through the window (the ``only`` filter hides the difference in what is returned).
YIELDED = []


def _mode(t, mode):
    return {"timestamp": t, "event": "budget_mode_set",
            "data": {"mode": mode, "target": None, "by": None, "scope": None}}


def test_the_newest_sample_is_found_without_reading_the_week(reads):
    now = time.time()
    _write([_sample(now - 6 * DAY, 10), _sample(now - 3 * HOUR, 30), _sample(now - 300, 41)])
    latest = budget.latest_sample(now)
    assert latest["t"] == pytest.approx(now - 300) and latest["limits"][0]["percent"] == 41
    assert YIELDED == ["budget_sampled"]  # stopped at the first one it met
    assert budget.latest_sample(now + 9 * DAY) is None  # both are past the history window by then


def test_a_hook_reads_hours_of_samples_not_the_week(reads):
    now = time.time()
    _write([_sample(now - 5 * DAY, 10), _sample(now - 2 * HOUR, 40), _sample(now - 600, 41)])
    st = budget.status(now, horizon_h=budget.hook_horizon_h())
    assert st["limits"][0]["percent"] == 41
    floor = now - budget.hook_horizon_h() * HOUR
    sample_reads = [since for only, since in reads if only == ("budget_sampled",)]
    assert sample_reads and all(since is not None and since >= floor - 1 for since in sample_reads)


def test_a_hook_still_answers_from_a_sample_older_than_its_horizon(reads):
    now = time.time()
    _write([_sample(now - 3 * DAY, 33)])
    st = budget.status(now, horizon_h=budget.hook_horizon_h())
    assert st["limits"][0]["percent"] == 33
    assert budget.status(now)["limits"][0]["percent"] == 33  # and without a horizon, the same sample


def test_the_horizon_leaves_the_readings_a_week_long_status_gives_when_the_samples_are_recent(reads):
    now = time.time()
    _write([_sample(now - 3 * HOUR + i * 600, 20 + i) for i in range(10)])
    full, hooked = budget.status(now), budget.status(now, horizon_h=budget.hook_horizon_h())
    for key in ("percent", "rate_last_hour", "rate_window", "rate_ewma", "projected_at_reset"):
        assert hooked["limits"][0][key] == full["limits"][0][key]


def test_the_next_autosample_reads_only_the_newest_sample(reads):
    now = time.time()
    _write([_sample(now - 2 * DAY, 20), _sample(now - 3 * HOUR, 30), _sample(now - 600, 40)])
    assert budget.next_autosample(now) == pytest.approx(now - 600 + 600)
    assert YIELDED.count("budget_sampled") == 1  # not the week's samples
    sample_reads = [since for only, since in reads if only == ("budget_sampled",)]
    assert len(sample_reads) == 1  # one read, which stops at the first sample it meets


def test_the_wall_line_never_reads_the_mode(reads):
    now = time.time()
    _write([_sample(now - 60, 50)])
    budget.wall_warning(now)
    assert not [only for only, _ in reads if only == ("budget_mode_set",)]


def test_the_prompt_notice_reads_the_mode_events_once(reads):
    now = time.time()
    _write([_sample(now - 60, 50), _mode(now - 20 * DAY, "conserve")])
    budget.prompt_notice(now)
    assert len([only for only, _ in reads if only == ("budget_mode_set",)]) == 1


@pytest.mark.parametrize("age_days, mode, current, lapsed", [
    (None, None, "normal", None),            # never set
    (2, "conserve", "conserve", None),       # within the weekly window: the intent stands
    (2, "normal", "normal", None),           # set back to normal within it
    (10, "conserve", "normal", "conserve"),  # aged out: lapsed to normal, and said
    (10, "normal", "normal", None),          # an old normal has nothing to announce
    (20, "conserve", "normal", None),        # older than two windows: not worth announcing
])
def test_mode_state_gives_the_current_mode_and_the_lapse_from_one_read(reads, age_days, mode, current, lapsed):
    now = time.time()
    if age_days is not None:
        _write([_mode(now - age_days * DAY, mode)])
    cur, lap = budget.mode_state(now)
    assert cur["mode"] == current
    assert (lap["mode"] if lap else None) == lapsed
    assert budget.current_mode(now)["mode"] == current
    assert (budget.lapsed_mode(now) or {}).get("mode") == lapsed
    mode_reads = [since for only, since in reads if only == ("budget_mode_set",)]
    assert all(since is not None and since >= now - 2 * budget.HISTORY.total_seconds() - 1 for since in mode_reads)


def test_a_sample_fetch_looks_back_only_as_far_as_its_interval(reads):
    now = time.time()
    _write([_sample(now - 2 * DAY, 10)])
    budget.sample(fetch=lambda: {"limits": [{"kind": "weekly_all", "percent": 11, "severity": "normal",
                                             "resets_at": RESET, "scope": None}]}, now=now)
    floor = now - budget.MIN_FETCH_INTERVAL
    sample_reads = [since for only, since in reads if only == ("budget_sampled",)]
    assert sample_reads and all(since is not None and since >= floor - 1 for since in sample_reads)
