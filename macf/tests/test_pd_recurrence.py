"""Calendar-shaped recurrence for agents' entries: the RRULE subset (design 3.1)."""
from datetime import datetime, timezone
from itertools import islice
from zoneinfo import ZoneInfo

import pytest

from macf.pd.recurrence import Recurrence

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")


def at(text, tz=UTC):
    return datetime.fromisoformat(text).replace(tzinfo=tz)


def firings(rule, n=12):
    return [w.isoformat() for w in islice(rule.iter_after(rule.start.replace(year=rule.start.year - 1)), n)]


def test_weekly_days_with_an_interval_and_a_count():
    """Every other week on Monday and Wednesday, four times, from Monday 19 October 2026."""
    rule = Recurrence.parse("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;COUNT=4", at("2026-10-19T09:00"))
    assert firings(rule) == ["2026-10-19T09:00:00+00:00", "2026-10-21T09:00:00+00:00",
                             "2026-11-02T09:00:00+00:00", "2026-11-04T09:00:00+00:00"]


def test_month_shapes_cron_can_only_fake():
    """The last weekday of each month, the first Monday, and the 31st, which a short month
    doesn't have and so skips."""
    last = Recurrence.parse("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=3", at("2026-10-01T17:00"))
    assert firings(last) == ["2026-10-30T17:00:00+00:00", "2026-11-30T17:00:00+00:00",
                             "2026-12-31T17:00:00+00:00"]
    first_monday = Recurrence.parse("FREQ=MONTHLY;BYDAY=1MO;COUNT=2", at("2026-10-01T08:00"))
    assert firings(first_monday) == ["2026-10-05T08:00:00+00:00", "2026-11-02T08:00:00+00:00"]
    the_31st = Recurrence.parse("FREQ=MONTHLY;BYMONTHDAY=31;COUNT=3", at("2026-10-31T06:00"))
    assert firings(the_31st) == ["2026-10-31T06:00:00+00:00", "2026-12-31T06:00:00+00:00",
                                 "2027-01-31T06:00:00+00:00"]


def test_an_exception_removes_an_occurrence_and_still_counts():
    """EXDATE takes an occurrence out; COUNT counts the rule's occurrences before that, as
    RFC 5545 does, so three days with the middle one excepted fire twice."""
    rule = Recurrence.parse("FREQ=DAILY;COUNT=3", at("2026-10-19T09:00"), exceptions=[at("2026-10-20T09:00")])
    assert firings(rule) == ["2026-10-19T09:00:00+00:00", "2026-10-21T09:00:00+00:00"]


def test_wall_clock_time_holds_across_daylight_saving():
    """09:00 in New York stays 09:00 when the clocks go back on 1 November 2026, so the instant
    moves; 02:30, which doesn't exist on 8 March 2026, is skipped that day."""
    nine = Recurrence.parse("FREQ=DAILY;COUNT=2", at("2026-10-31T09:00", NEW_YORK))
    assert [w.astimezone(UTC).isoformat() for w in nine.iter_after(at("2026-10-30T00:00"))] == \
        ["2026-10-31T13:00:00+00:00", "2026-11-01T14:00:00+00:00"]
    gap = Recurrence.parse("FREQ=DAILY;COUNT=2", at("2026-03-07T02:30", NEW_YORK))
    assert [w.date().isoformat() for w in gap.iter_after(at("2026-03-06T00:00"))] == ["2026-03-07", "2026-03-09"]


@pytest.mark.parametrize("text, start, says", [
    ("FREQ=YEARLY", at("2026-10-19T09:00"), "not supported"),
    ("FREQ=DAILY;BYHOUR=9", at("2026-10-19T09:00"), "BYHOUR is not supported"),
    ("FREQ=WEEKLY;BYDAY=1MO", at("2026-10-19T09:00"), "only a monthly rule"),
    ("FREQ=MONTHLY;BYMONTHDAY=31;UNTIL=20261130T000000Z", at("2026-11-01T09:00"), "never fires"),
    ("FREQ=DAILY;COUNT=2;UNTIL=20261130T000000Z", at("2026-11-01T09:00"), "can't both"),
    ("FREQ=DAILY", datetime(2026, 10, 19, 9), "no timezone"),
])
def test_a_rule_it_cannot_read_is_refused_by_name(text, start, says):
    """Anything outside the subset is refused, naming what isn't read, never half-read."""
    with pytest.raises(ValueError, match=says):
        Recurrence.parse(text, start)


@pytest.mark.parametrize("text", [
    "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;COUNT=9",
    "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=9",
    "FREQ=MONTHLY;BYDAY=-1FR;COUNT=9",
    "FREQ=MONTHLY;BYMONTHDAY=-1,15;COUNT=9",
    "FREQ=DAILY;INTERVAL=3;BYDAY=SA,SU;COUNT=9",
    "FREQ=MONTHLY;INTERVAL=2;BYMONTHDAY=13;BYDAY=FR;COUNT=4",
    "FREQ=MINUTELY;INTERVAL=50;COUNT=9",
    "FREQ=HOURLY;INTERVAL=7;COUNT=9",
])
def test_the_subset_agrees_with_dateutil(text):
    """Where dateutil is installed (it's optional, so CI may skip this), each rule's
    occurrences match its full RFC 5545 reading."""
    rrule = pytest.importorskip("dateutil.rrule")
    start = at("2026-10-19T09:00")
    ours = [w.isoformat() for w in Recurrence.parse(text, start).iter_after(at("2026-10-18T00:00"))]
    theirs = [w.isoformat() for w in rrule.rrulestr(text, dtstart=start)]
    assert ours == theirs


def test_a_minutely_rule_steps_by_elapsed_time_across_daylight_saving():
    """Every fifty minutes, the check-in a warm prompt cache needs. The clocks go back at 02:00
    on 1 November 2026 in New York, and the steps stay fifty minutes apart in elapsed time."""
    rule = Recurrence.parse("FREQ=MINUTELY;INTERVAL=50", at("2026-11-01T00:29", NEW_YORK))
    got = list(islice(rule.iter_after(at("2026-11-01T00:00", NEW_YORK)), 4))
    assert [w.astimezone(UTC).isoformat() for w in got] == [
        "2026-11-01T04:29:00+00:00", "2026-11-01T05:19:00+00:00",
        "2026-11-01T06:09:00+00:00", "2026-11-01T06:59:00+00:00"]


def test_a_sub_daily_rule_jumps_to_the_next_step_and_keeps_its_count():
    """Asked months after its start, a minutely rule answers the next step directly, strictly
    after the time asked, and COUNT still counts from the start."""
    rule = Recurrence.parse("FREQ=MINUTELY;INTERVAL=50", at("2026-01-01T00:00"))
    assert rule.next_after(at("2026-10-20T14:10")).isoformat() == "2026-10-20T14:30:00+00:00"
    assert rule.next_after(at("2026-10-20T14:30")).isoformat() == "2026-10-20T15:20:00+00:00"
    hourly = Recurrence.parse("FREQ=HOURLY;INTERVAL=2;COUNT=3", at("2026-10-20T09:00"))
    assert firings(hourly) == ["2026-10-20T09:00:00+00:00", "2026-10-20T11:00:00+00:00",
                               "2026-10-20T13:00:00+00:00"]
    assert hourly.next_after(at("2026-10-20T13:00")) is None
    until = Recurrence.parse("FREQ=HOURLY;UNTIL=20261020T113000Z", at("2026-10-20T09:00"),
                             exceptions=[at("2026-10-20T10:00")])
    assert firings(until) == ["2026-10-20T09:00:00+00:00", "2026-10-20T11:00:00+00:00"]


@pytest.mark.parametrize("text", ["FREQ=MINUTELY;INTERVAL=50;BYDAY=MO", "FREQ=HOURLY;BYMONTHDAY=1"])
def test_a_sub_daily_rule_refuses_day_parts_by_name(text):
    with pytest.raises(ValueError, match=r"is not read in a (minutely|hourly) rule"):
        Recurrence.parse(text, at("2026-10-20T09:00"))
