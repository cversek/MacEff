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


def _mode(t, mode, target=None):
    return {"timestamp": t, "event": "budget_mode_set",
            "data": {"mode": mode, "target": target, "by": None, "scope": None}}


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


# ── each hook uses the bounds ─────────────────────────────────────────────────

def _old_and_new_samples(now):
    """Three samples a day or more old and the newest ten minutes ago: a hook that uses its horizon consumes the
    newest only (and one more to learn there is a budget); a read of the history window consumes all four."""
    return [_sample(now - 5 * DAY, 10), _sample(now - 2 * DAY, 20), _sample(now - DAY, 30), _sample(now - 600, 41)]


def _sample_reads():
    return YIELDED.count("budget_sampled")


def test_the_prompt_notice_uses_its_horizon(reads):
    now = time.time()
    _write(_old_and_new_samples(now))
    budget.prompt_notice(now)
    assert _sample_reads() <= 2


def test_the_wall_line_uses_its_horizon(reads):
    now = time.time()
    _write(_old_and_new_samples(now))
    budget.wall_warning(now)
    assert _sample_reads() <= 2


def test_the_burn_gate_uses_its_horizon_and_the_mode_it_already_read(reads, monkeypatch):
    now = time.time()
    monkeypatch.setattr(budget, "open_work", lambda: [{"id": "1", "type": "TASK", "status": "pending",
                                                       "scoped": True, "subject": "x"}])
    _write(_old_and_new_samples(now) + [_mode(now - 3600, "burn", 95)])
    budget.burn_gate(True, now)
    assert _sample_reads() <= 2
    assert len([only for only, _ in reads if only == ("budget_mode_set",)]) == 1


def test_without_samples_no_hook_reaches_for_the_status(reads, monkeypatch):
    def refuse(*a, **kw):
        raise AssertionError("status was called with no budget in use")
    monkeypatch.setattr(budget, "status", refuse)
    now = time.time()
    assert budget.prompt_notice(now) is None
    assert budget.wall_warning(now) is None
    _write([_mode(now - 3600, "burn", 95)])
    assert budget.burn_gate(True, now)["block"] is False


def test_the_hook_horizon_is_four_time_constants():
    assert budget.hook_horizon_h() == 4 * budget._tau_hours()


def test_a_sample_inside_the_horizon_is_read_and_one_outside_is_not(reads):
    now = time.time()
    tau = budget._tau_hours()
    _write([_sample(now - 5 * tau * HOUR, 10), _sample(now - 3 * tau * HOUR, 20), _sample(now - 600, 30)])
    YIELDED.clear()
    budget.status(now, horizon_h=budget.hook_horizon_h())
    assert _sample_reads() == 2  # the one at 3 time constants and the newest, not the one at 5


def test_a_hook_status_with_no_samples_says_what_to_do(reads):
    with pytest.raises(budget.BudgetError):
        budget.status(time.time(), horizon_h=budget.hook_horizon_h())


# ── the notice and the mode are read within the window that can hold them, then reasserted ─────────────────

def _weekly_sample(t, pct, resets_in_days, kind="weekly_all"):
    reset = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(t + resets_in_days * DAY))
    return {"timestamp": t, "event": "budget_sampled",
            "data": {"source": "endpoint",
                     "limits": [{"kind": kind, "percent": pct, "resets_at": reset,
                                 "scope": None, "severity": "normal"}]}}


def test_a_notice_is_read_within_its_window_and_an_old_one_is_reasserted(reads):
    now = time.time()
    _write([_weekly_sample(now - 60, 80, 2)])  # a week-long window that opened five days ago
    key = budget._key(budget.status(now)["limits"][0], "band")
    _write([{"timestamp": now - 4 * DAY, "event": "budget_notice", "data": {"key": key, "value": 75.0}},
            {"timestamp": now - 7 * DAY, "event": "budget_notice", "data": {"key": "band:old:window", "value": 50.0}}])
    assert budget.prompt_notice(now) is None  # the band 75 was shown in this window: nothing to say
    floors = [since for only, since in reads if only == ("budget_notice",)]
    assert floors and all(since >= now - 5 * DAY - 2 * HOUR for since in floors)  # not the 8-day history window
    reasserted = [e for e in _events_of("budget_notice") if e["data"].get("reasserted")]
    assert [e["data"]["key"] for e in reasserted] == [key] and reasserted[0]["data"]["value"] == 75.0
    YIELDED.clear()
    assert budget.prompt_notice(now + 60) is None  # same answer, and the read stops at the reasserted event
    assert YIELDED.count("budget_notice") == 1


def test_the_mode_is_reasserted_without_changing_what_it_says(reads):
    now = time.time()
    _write([_sample(now - 60, 50), _mode(now - 3 * DAY, "conserve")])
    first = budget.mode_state(now, reassert=True)
    YIELDED.clear()
    second = budget.mode_state(now + 5, reassert=True)
    assert second == first and first[0]["mode"] == "conserve" and first[0]["set_at"] == pytest.approx(now - 3 * DAY)
    assert "reasserted" not in first[0]
    copies = [e for e in _events_of("budget_mode_set") if e["data"].get("reasserted")]
    assert len(copies) == 1  # written once; the second read found it and wrote nothing
    assert copies[0]["data"]["set_at"] == pytest.approx(now - 3 * DAY)


def test_a_reasserted_mode_still_lapses_by_its_original_time(reads):
    now = time.time()
    _write([_mode(now - 9 * DAY, "conserve")])
    cur, lapsed = budget.mode_state(now, reassert=True)
    assert cur["mode"] == "normal" and lapsed["mode"] == "conserve"
    cur2, lapsed2 = budget.mode_state(now + 2 * HOUR, reassert=True)  # reads the reasserted copy
    assert cur2["mode"] == "normal" and lapsed2["set_at"] == pytest.approx(now - 9 * DAY)
    assert budget.mode_state(now + 8 * DAY, reassert=True) == (cur2, None)  # past two windows from the original set


def test_no_mode_is_remembered_so_the_next_read_stops(reads):
    now = time.time()
    assert budget.mode_state(now, reassert=True)[0]["mode"] == "normal"
    YIELDED.clear()
    assert budget.mode_state(now + 5, reassert=True) == (budget.mode_state(now)[0], None)
    assert YIELDED.count("budget_mode_set") >= 1
    assert budget.current_mode(now + 5)["mode"] == "normal" and budget.current_mode(now + 5).get("set_at") is None


def _events_of(name):
    from macf.agent_events_log import read_events
    return list(read_events(reverse=False, scope="all", only=name))


def test_an_expired_mode_is_replaced_by_the_marker_not_copied_again(reads):
    now = time.time()
    _write([_mode(now - 3600 * 3, "conserve") | {"data": {"mode": "conserve", "target": None, "by": None, "scope": None,
                                                           "set_at": now - 20 * DAY, "reasserted": True}}])
    assert budget.mode_state(now, reassert=True) == (budget._NO_MODE, None)
    written = [e for e in _events_of("budget_mode_set") if e["timestamp"] > now - 60]
    assert [e["data"].get("absent") for e in written] == [True]  # the marker, not a fresh copy of the dead mode
    assert budget.mode_state(now + 10, reassert=True) == (budget._NO_MODE, None)
    assert len([e for e in _events_of("budget_mode_set") if e["timestamp"] > now - 60]) == 1  # nothing more within the hour


def test_the_read_only_callers_never_write(reads):
    now = time.time()
    _write([_weekly_sample(now - 60, 95, 0.1, "session"), _mode(now - 3 * DAY, "conserve"), _mode(now - 9 * DAY, "burn")])
    key = budget._key(budget.status(now, need_mode=False)["limits"][0], "wall")
    _write([{"timestamp": now - 3 * HOUR, "event": "budget_notice", "data": {"key": key, "value": 95}}])
    before = len(_events_of(None))  # the stale mode, the stale notice and the sample, all over an hour old
    budget.current_mode(now), budget.lapsed_mode(now), budget.status(now), budget.status(now, horizon_h=budget.hook_horizon_h())
    budget.wall_warning(now)
    budget.mode_state(now)
    assert len(_events_of(None)) == before


def test_the_prompt_notice_asks_for_the_mode_to_be_reasserted(reads):
    now = time.time()
    _write([_sample(now - 60, 10), _mode(now - 3 * DAY, "conserve")])
    budget.prompt_notice(now)
    assert [e for e in _events_of("budget_mode_set") if e["data"].get("reasserted")]


def test_the_lapse_is_announced_once(reads):
    now = time.time()
    _write([_weekly_sample(now - 60, 10, 2), _mode(now - 10 * DAY, "conserve")])
    first = budget.prompt_notice(now)
    assert "lapsed" in first
    assert budget.prompt_notice(now + 60) is None
    assert "lapsed" not in (budget.prompt_notice(now + 2 * HOUR) or "")  # still once, after the reassertions


# ── the pieces of the notice bound ────────────────────────────────────────────

def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(t))


def _notice(t, key, value=75.0):
    return {"timestamp": t, "event": "budget_notice", "data": {"key": key, "value": value}}


def _copies():
    return [e for e in _events_of("budget_notice") if e["data"].get("reasserted")]


def test_a_notice_is_reasserted_only_when_over_an_hour_old(reads):
    now = time.time()
    _write([_notice(now - 600, "fresh"), _notice(now - 2 * HOUR, "stale")])
    floor = now - DAY
    budget._last_notices(now, {"fresh": floor}, reassert=True)
    assert _copies() == []  # ten minutes old: the next read already stops there
    budget._last_notices(now, {"stale": floor}, reassert=True)
    assert [e["data"]["key"] for e in _copies()] == ["stale"]


def test_a_session_window_opens_five_hours_before_its_reset_and_a_weekly_one_a_week(reads):
    now = time.time()
    slack = budget._WINDOW_SLACK
    session = {"kind": "session", "resets_at": _iso(now + HOUR)}
    weekly = {"kind": "weekly_all", "resets_at": _iso(now + DAY)}
    assert budget._window_start(session, now) == pytest.approx(now + HOUR - 5 * HOUR - slack, abs=2)
    assert budget._window_start(weekly, now) == pytest.approx(now + DAY - 7 * DAY - slack, abs=2)


def test_a_window_start_is_never_before_the_history_window_or_after_now(reads):
    now = time.time()
    floor = now - budget.HISTORY.total_seconds()
    assert budget._window_start({"kind": "weekly_all", "resets_at": _iso(now + 20 * DAY)}, now) == pytest.approx(floor)
    assert budget._window_start({"kind": "weekly_all", "resets_at": _iso(now - 20 * DAY)}, now) == pytest.approx(floor)
    assert budget._window_start({"kind": "weekly_all", "resets_at": "not a time"}, now) == pytest.approx(floor)


def test_a_notice_from_the_previous_window_does_not_count(reads):
    now = time.time()
    start = now - 2 * DAY
    _write([_notice(start - 60, "k"), _notice(now - 5 * DAY, "other")])
    # "other" lowers the read's floor below the old "k", so only the per-key check keeps it out
    assert budget._last_notices(now, {"k": start, "other": now - 6 * DAY}).keys() == {"other"}
    _write([_notice(start + 60, "k", 90.0)])
    assert budget._last_notices(now, {"k": start})["k"]["value"] == 90.0


def test_the_lapse_notice_is_looked_up_from_when_the_lapse_began(reads, monkeypatch):
    now = time.time()
    _write([_weekly_sample(now - 60, 10, 2), _mode(now - 9 * DAY, "conserve")])
    asked = []
    real = budget._last_notices
    monkeypatch.setattr(budget, "_last_notices", lambda n, wanted, **kw: asked.append(dict(wanted)) or real(n, wanted, **kw))
    budget.prompt_notice(now)
    lapse = [floor for wanted in asked for key, floor in wanted.items() if key.startswith("mode_lapse:")]
    assert lapse == [pytest.approx(now - 9 * DAY + budget.HISTORY.total_seconds(), abs=2)]  # a day ago, not eight
