"""The scheduler's core: when a schedule fires, and what a downtime's missed runs become.

Pure functions driven by explicit times; no test waits real time (MIS-0002 step 2).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from macf.pd.interface import MissedRunPolicy, Window
from macf.pd.schedule import CronExpr, plan_runs

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def at(text, tz=UTC):
    return datetime.fromisoformat(text).replace(tzinfo=tz)


def policy(kind, window=None):
    return MissedRunPolicy(kind=kind, window=Window(start=window[0], end=window[1]) if window else None)


def test_cron_steps_ranges_and_lists():
    """Steps, ranges and lists read as cron reads them, across a weekend."""
    business = CronExpr.parse("*/15 9-17 * * 1-5")
    assert business.next_after(at("2026-10-09 17:50")) == at("2026-10-12 09:00")  # Friday to Monday
    assert CronExpr.parse("0,30 * * * *").next_after(at("2026-10-10 10:10")) == at("2026-10-10 10:30")
    assert CronExpr.parse("0 12 * * 7").next_after(at("2026-10-10 00:00")) == at("2026-10-11 12:00")  # 7 is Sunday


def test_cron_day_of_month_or_day_of_week():
    """With both day fields restricted, either one matching fires it, as cron does."""
    cron = CronExpr.parse("0 0 13 * 5")
    first = cron.next_after(at("2026-10-01 00:00"))  # a Thursday
    assert first == at("2026-10-02 00:00")  # the Friday
    assert cron.next_after(at("2026-10-09 00:00")) == at("2026-10-13 00:00")  # the 13th, a Tuesday


@pytest.mark.parametrize("text, field", [
    ("61 * * * *", "minute"),
    ("* 24 * * *", "hour"),
    ("* * 0 * *", "day of month"),
    ("*/0 * * * *", "minute"),
    ("* * * *", "five fields"),
    ("a * * * *", "minute"),
    ("0 0 30 2 *", "never fires"),
])
def test_cron_refuses_what_it_cannot_read_or_never_fires(text, field):
    """A cron that cannot be read, or can never fire, is refused when it is loaded, naming why."""
    with pytest.raises(ValueError, match=field):
        CronExpr.parse(text)


def test_cron_across_daylight_saving():
    """A wall-clock time that does not exist is skipped, and one that happens twice fires once."""
    spring = CronExpr.parse("30 2 * * *", tz=NY)  # 2026-03-08 has no 02:30
    assert spring.next_after(at("2026-03-07 03:00", NY)) == at("2026-03-09 02:30", NY)
    autumn = CronExpr.parse("30 1 * * *", tz=NY)  # 2026-11-01 has 01:30 twice
    first = autumn.next_after(at("2026-11-01 00:00", NY))
    assert first.astimezone(UTC) == at("2026-11-01 05:30")  # the first 01:30, still EDT
    assert autumn.next_after(first) == at("2026-11-02 01:30", NY)
    # From inside the repeated hour, the first 01:30 has already passed.
    second_pass = datetime(2026, 11, 1, 1, 10, tzinfo=NY, fold=1)
    assert autumn.next_after(second_pass) == at("2026-11-02 01:30", NY)


def test_missed_runs_follow_their_policy():
    """A downtime's missed runs are skipped, run once, or reported, as the schedule declared (R25)."""
    hourly = CronExpr.parse("0 * * * *")
    down = {"last_due": at("2026-10-10 06:00"), "boot": at("2026-10-10 09:20"), "now": at("2026-10-10 09:20")}

    skipped = plan_runs(hourly, policy("skip"), **down)
    assert (skipped.run_at, skipped.missed) == (None, 3)
    assert (skipped.first_missed, skipped.last_missed) == (at("2026-10-10 07:00"), at("2026-10-10 09:00"))

    once = plan_runs(hourly, policy("run_once"), **down)
    assert (once.run_at, once.scheduled_for, once.missed) == (down["now"], at("2026-10-10 09:00"), 2)
    assert once.late_s == 20 * 60

    reported = plan_runs(hourly, policy("report_only"), **down)
    assert (reported.run_at, reported.missed) == (None, 3)
    assert reported.next_regular == at("2026-10-10 10:00")


def test_run_once_in_window_waits_for_its_window():
    """A missed run declared run-once-in-window is made up at the window's next opening,
    unless the next regular run comes first."""
    nightly = CronExpr.parse("0 3 * * *")
    down = {"last_due": at("2026-10-09 03:00"), "boot": at("2026-10-10 10:00"), "now": at("2026-10-10 10:00")}

    later = plan_runs(nightly, policy("run_once_in_window", ("01:00", "05:00")), **down)
    assert (later.run_at, later.scheduled_for) == (at("2026-10-11 01:00"), at("2026-10-10 03:00"))

    superseded = plan_runs(nightly, policy("run_once_in_window", ("04:00", "05:00")), **down)
    assert (superseded.run_at, superseded.next_regular) == (None, at("2026-10-11 03:00"))  # 03:00 comes first

    now = plan_runs(nightly, policy("run_once_in_window", ("09:00", "12:00")), **down)
    assert now.run_at == down["now"]

    across_midnight = plan_runs(nightly, policy("run_once_in_window", ("22:00", "02:00")), **down)
    assert across_midnight.run_at == at("2026-10-10 22:00")
    late_evening = {**down, "boot": at("2026-10-10 23:30"), "now": at("2026-10-10 23:30")}
    inside = plan_runs(nightly, policy("run_once_in_window", ("22:00", "02:00")), **late_evening)
    assert inside.run_at == late_evening["now"]


def test_no_replayed_restart():
    """A missed run whose act restarts a unit is not replayed, whatever the policy (R27)."""
    hourly = CronExpr.parse("0 * * * *")
    plan = plan_runs(hourly, policy("run_once"), last_due=at("2026-10-10 06:00"),
                     boot=at("2026-10-10 09:20"), now=at("2026-10-10 09:20"), restarts_unit=True)
    assert (plan.run_at, plan.missed) == (None, 3)


def test_due_run_states_its_lateness():
    """A run that comes due while the daemon is up runs now and carries how late it is (R34);
    a new schedule owes nothing from before it was declared."""
    hourly = CronExpr.parse("0 * * * *")
    due = plan_runs(hourly, policy("skip"), last_due=at("2026-10-10 09:00"),
                    boot=at("2026-10-10 08:00"), now=at("2026-10-10 10:00:42"))
    assert (due.run_at, due.scheduled_for, due.late_s, due.missed) == (
        at("2026-10-10 10:00:42"), at("2026-10-10 10:00"), 42.0, 0)
    at_boot = plan_runs(hourly, policy("skip"), last_due=at("2026-10-10 09:00"),
                        boot=at("2026-10-10 10:00"), now=at("2026-10-10 10:00:05"))
    assert (at_boot.scheduled_for, at_boot.missed) == (at("2026-10-10 10:00"), 0)  # due, not missed
    # Two firings due while the daemon was up but stalled: the newer runs, the older is missed.
    stalled = plan_runs(hourly, policy("run_once"), last_due=at("2026-10-10 08:00"),
                        boot=at("2026-10-10 07:00"), now=at("2026-10-10 10:00:30"))
    assert (stalled.scheduled_for, stalled.missed, stalled.last_missed) == (
        at("2026-10-10 10:00"), 1, at("2026-10-10 09:00"))

    fresh = plan_runs(hourly, policy("run_once"), last_due=None, since=at("2026-10-10 09:30"),
                      boot=at("2026-10-10 09:30"), now=at("2026-10-10 09:45"))
    assert (fresh.run_at, fresh.missed, fresh.next_regular) == (None, 0, at("2026-10-10 10:00"))


@pytest.mark.parametrize("cron, window, why", [
    ("61 * * * *", None, "minute"),
    ("0 0 30 2 *", None, "never fires"),
    ("0 3 * * *", ("25:00", "05:00"), "window"),
])
def test_declaration_with_an_unusable_schedule_is_refused(tmp_path, cron, window, why):
    """A schedule that cannot fire, or a window that is not a time of day, refuses the
    whole declaration when it is loaded, not when the schedule comes due."""
    from macf.pd.core import DeclarationRefused, load_declaration
    from macf.pd.interface import Declaration, PromptRun, Schedule, declaration_path

    kind = "run_once_in_window" if window else "skip"
    schedule = Schedule(name="nightly", cron=cron, missed_run=policy(kind, window), target="isolated",
                        run=PromptRun(prompt_file="prompts/nightly.md"), timeout_s=600)
    path = declaration_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(Declaration(version=1, agent="Tester@abc123", timezone="UTC", schedules=[schedule]).model_dump_json())
    with pytest.raises(DeclarationRefused, match=why):
        load_declaration(tmp_path, "Tester@abc123")


# Each missed-run policy crossed with whether the schedule's act restarts a unit.
NIGHTLY_DOWN = {"last_due": at("2026-10-09 03:00"), "boot": at("2026-10-10 10:00"), "now": at("2026-10-10 10:00")}
POLICY_BY_RESTART = [
    # policy,                                   restarts_unit, run_at
    (("skip", None),                            False, None),
    (("run_once", None),                        False, NIGHTLY_DOWN["now"]),
    (("run_once_in_window", ("09:00", "12:00")), False, NIGHTLY_DOWN["now"]),
    (("run_once_in_window", ("01:00", "05:00")), False, at("2026-10-11 01:00")),
    (("report_only", None),                     False, None),
    (("skip", None),                            True,  None),
    (("run_once", None),                        True,  None),
    (("run_once_in_window", ("09:00", "12:00")), True,  None),
    (("run_once_in_window", ("01:00", "05:00")), True,  None),
    (("report_only", None),                     True,  None),
]


@pytest.mark.parametrize("declared, restarts_unit, run_at", POLICY_BY_RESTART)
def test_missed_run_by_policy_and_restart(declared, restarts_unit, run_at):
    """A missed nightly run is made up exactly when its policy says so, and never when its
    act restarts a unit, whatever the policy (R25, R27)."""
    plan = plan_runs(CronExpr.parse("0 3 * * *"), policy(*declared), restarts_unit=restarts_unit,
                     **NIGHTLY_DOWN)
    assert plan.run_at == run_at
    assert plan.missed == (0 if run_at else 1)


def test_schedules_name_their_timezone():
    """A declaration with schedules says which timezone its crons are read in, and a name
    that is not a timezone is refused, so the same declaration fires at the same moments
    on a host and in a container."""
    from pydantic import ValidationError
    from macf.pd.interface import Declaration, PromptRun, Schedule

    schedule = Schedule(name="nightly", cron="0 3 * * *", missed_run=policy("skip", None),
                        target="isolated", run=PromptRun(prompt_file="p.md"), timeout_s=600)
    with pytest.raises(ValidationError, match="names the timezone"):
        Declaration(version=1, agent="Tester@abc123", schedules=[schedule])
    with pytest.raises(ValidationError, match="unknown timezone"):
        Declaration(version=1, agent="Tester@abc123", timezone="Mars/Olympus", schedules=[schedule])
    declared = Declaration(version=1, agent="Tester@abc123", timezone="America/New_York", schedules=[schedule])
    assert declared.schedules[0].restarts_unit is False
    assert Declaration(version=1, agent="Tester@abc123").timezone is None
