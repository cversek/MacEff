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


# --- the scheduler: the daemon runs what the schedules owe ----------------------

import os  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

from macf.pd import scheduler as sc  # noqa: E402
from macf.pd.interface import CommandRun, Declaration, PromptRun, Schedule  # noqa: E402

CARD = "Tester@abc123"


class Log:
    """An event log in a list, read newest first as the daemon reads it."""

    def __init__(self):
        self.rows = []

    def append(self, event, data):
        self.rows.append({"event": event, "data": data})
        return True

    def read(self):
        return list(reversed(self.rows))

    def of(self, event):
        return [r["data"] for r in self.rows if r["event"] == event]


def command_schedule(command, name="check", cron="*/5 * * * *", kind="skip", timeout_s=30.0,
                     wake_when="exit_code"):
    return Schedule(name=name, cron=cron, missed_run=policy(kind), target="isolated",
                    run=CommandRun(command=command, wake_when=wake_when), timeout_s=timeout_s)


def make_scheduler(tmp_path, schedules, log, now):
    decl = Declaration(version=1, agent=CARD, timezone="UTC", schedules=schedules)
    s = sc.Scheduler(decl, CARD, {"agent_home": str(tmp_path)}, work_dir=tmp_path / "runs",
                     append=log.append, events=log.read, now=lambda: now[0])
    s.boot()
    return s


def finish(s, timeout=10.0):
    deadline = time.monotonic() + timeout
    while s.running and time.monotonic() < deadline:
        s.tick()
        time.sleep(0.02)
    assert not s.running, "a run never ended"


def test_advance_before_run(tmp_path, monkeypatch):
    """The run's record, which moves the next run time on, is written before the run starts
    (R26): before the record of its process, which exists only once the process does."""
    log, now = Log(), [at("2026-10-14 12:00")]
    seen = tmp_path / "seen"
    s = make_scheduler(tmp_path, [command_schedule(
        [sys.executable, "-c", f"open({str(seen)!r}, 'w').write('ran')"])], log, now)
    recorded_at_spawn, real_popen = [], subprocess.Popen

    def popen(*args, **kwargs):
        if args and args[0] and args[0][0] == sys.executable:     # the run, not a ps it reads
            recorded_at_spawn.append(bool(log.of(sc.EVENT_STARTED)))
        return real_popen(*args, **kwargs)
    monkeypatch.setattr(sc.subprocess, "Popen", popen)
    now[0] = at("2026-10-14 12:05")
    s.tick()
    assert [d["scheduled_for"] for d in log.of(sc.EVENT_STARTED)] == ["2026-10-14T12:05:00+00:00"]
    assert recorded_at_spawn == [True], "the run started before its record"
    finish(s)
    assert seen.read_text() == "ran"
    s.tick()                                                    # the same firing is not run twice
    assert len(log.of(sc.EVENT_STARTED)) == 1


def test_late_run_says_so(tmp_path):
    """A due run that starts late records how late (R34)."""
    log, now = Log(), [at("2026-10-14 12:00")]
    s = make_scheduler(tmp_path, [command_schedule(["/usr/bin/true"])], log, now)
    now[0] = at("2026-10-14 12:07:30")
    s.tick()
    assert log.of(sc.EVENT_STARTED)[0]["late_s"] == 150.0
    finish(s)


def test_wall_clock_cap(tmp_path):
    """A run past its limit has its process group killed, and says so (R36)."""
    log, now = Log(), [at("2026-10-14 12:00")]
    s = make_scheduler(tmp_path, [command_schedule(
        ["/bin/sh", "-c", "trap '' TERM; sleep 60 & wait"], timeout_s=0.3)], log, now)
    now[0] = at("2026-10-14 12:05")
    s.tick()
    finish(s, timeout=15.0)
    done = log.of(sc.EVENT_DONE)[0]
    assert done["outcome"].startswith("killed: past its 0.3 s limit") and done["wake"] is False


def test_leases_released(tmp_path):
    """A run still in flight when the daemon restarted is ended by the next daemon: stopped
    if it is still that process, and recorded, so nothing it held outlives its daemon (R28)."""
    log, now = Log(), [at("2026-10-14 12:00")]
    first = make_scheduler(tmp_path, [command_schedule(["/bin/sleep", "60"])], log, now)
    now[0] = at("2026-10-14 12:05")
    first.tick()
    pid = first.running["check"].proc.pid
    second = make_scheduler(tmp_path, [command_schedule(["/bin/sleep", "60"])], log, now)   # restarted
    done = log.of(sc.EVENT_DONE)
    assert len(done) == 1 and done[0]["outcome"].startswith("abandoned")
    assert "its process group was stopped" in done[0]["outcome"]
    first.running["check"].proc.wait(timeout=5)
    second.tick()                                               # the abandoned firing is not run again
    assert len(log.of(sc.EVENT_STARTED)) == 1
    assert pid


def test_a_condition_decides_the_wake(tmp_path):
    """exit_code: 0 wakes, 1 says nothing, other codes fail. stdout: output wakes."""
    cases = [(["/bin/sh", "-c", "exit 0"], "exit_code", True, "ok: its condition holds"),
             (["/bin/sh", "-c", "exit 1"], "exit_code", False, "ok: nothing to say"),
             (["/bin/sh", "-c", "exit 3"], "exit_code", False, "failed: exit 3"),
             (["/bin/sh", "-c", "echo 2 new"], "stdout", True, "ok: it had something to say"),
             (["/bin/sh", "-c", "true"], "stdout", False, "ok: nothing to say")]
    for i, (command, when, wake, outcome) in enumerate(cases):
        log, now = Log(), [at("2026-10-14 12:00")]
        s = make_scheduler(tmp_path / str(i), [command_schedule(command, wake_when=when)], log, now)
        now[0] = at("2026-10-14 12:05")
        s.tick()
        finish(s)
        done = log.of(sc.EVENT_DONE)[0]
        assert (done["wake"], done["outcome"]) == (wake, outcome), (command, when)


def test_missed_runs_are_reported_once(tmp_path):
    """A downtime's missed firings are recorded once by policy, not on every pass (R25)."""
    log, now = Log(), [at("2026-10-14 12:00")]
    make_scheduler(tmp_path, [command_schedule(["/usr/bin/true"], kind="report_only")], log, now)
    log.append(sc.EVENT_STARTED, {"agent": CARD, "schedule": "check", "scheduled_for": "2026-10-14T12:00:00+00:00"})
    log.append(sc.EVENT_DONE, {"agent": CARD, "schedule": "check", "scheduled_for": "2026-10-14T12:00:00+00:00"})
    now[0] = at("2026-10-14 13:02")                             # the daemon was down an hour
    s = make_scheduler(tmp_path, [command_schedule(["/usr/bin/true"], kind="report_only")], log, now)
    for _ in range(3):
        s.tick()
    missed = log.of(sc.EVENT_MISSED)
    assert len(missed) == 1 and missed[0]["policy"] == "report_only" and missed[0]["count"] == 12
    assert len(log.of(sc.EVENT_STARTED)) == 1, "report_only ran a missed firing"


def test_a_prompt_run_is_said_not_run_once(tmp_path):
    log, now = Log(), [at("2026-10-14 12:00")]
    prompt = Schedule(name="digest", cron="0 * * * *", missed_run=policy("skip"), target="isolated",
                      run=PromptRun(prompt_file="p.md"), timeout_s=60)
    s = make_scheduler(tmp_path, [prompt], log, now)
    now[0] = at("2026-10-14 13:00")
    s.tick()
    assert len(log.of(sc.EVENT_NOT_RUN)) == 1 and not log.of(sc.EVENT_STARTED)


def _alive(pid):
    """Whether ``pid`` runs: present and not a zombie, on Linux and macOS alike."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(state.stdout.strip()) and not state.stdout.strip().startswith("Z")


def _pid_in(path, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return int(path.read_text())
        time.sleep(0.05)
    raise AssertionError("the run never wrote its pid")


def _reap(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


# A child that ignores SIGTERM and writes its own pid. The \$\$ is escaped so that the
# outer shell passes it on and the child, not its leader, expands it.
_STUBBORN_CHILD = "trap '' TERM; echo \\$\\$ > {f}; while true; do sleep 1; done"


def test_a_run_past_its_limit_takes_its_group(tmp_path):
    """A run past its limit whose leader dies on SIGTERM still has the rest of its group
    killed, and is recorded ended only once the group has (R36)."""
    f = tmp_path / "child.pid"
    log, now = Log(), [at("2026-10-14 12:00")]
    cmd = ["/bin/sh", "-c", f'/bin/sh -c "{_STUBBORN_CHILD.format(f=f)}" & sleep 60']
    s = make_scheduler(tmp_path, [command_schedule(cmd, timeout_s=0.5)], log, now)
    now[0] = at("2026-10-14 12:05")
    s.tick()
    kid = _pid_in(f)
    try:
        finish(s, timeout=20.0)
        assert not _alive(kid), "the run's child outlived the run"
        assert log.of(sc.EVENT_DONE)[0]["outcome"].startswith("killed: past its 0.5 s limit")
    finally:
        _reap(kid)


def test_a_daemon_stop_ends_a_run_that_ignores_sigterm(tmp_path):
    """The daemon's stop escalates to SIGKILL after the grace, so no run outlives it (R48)."""
    f = tmp_path / "run.pid"
    log, now = Log(), [at("2026-10-14 12:00")]
    cmd = ["/bin/sh", "-c", f"trap '' TERM; echo $$ > {f}; while true; do sleep 1; done"]
    s = make_scheduler(tmp_path, [command_schedule(cmd, timeout_s=600)], log, now)
    now[0] = at("2026-10-14 12:05")
    s.tick()
    run = _pid_in(f)
    try:
        s.shutdown()
        assert not _alive(run), "the run outlived the daemon's stop"
        assert log.of(sc.EVENT_DONE)[0]["outcome"] == "stopped: the daemon stopped"
    finally:
        _reap(run)


def test_an_abandoned_run_whose_leader_exited_is_stopped(tmp_path):
    """A run whose leader exited, leaving a member that ignores SIGTERM, is still ended by
    the next daemon: the group is the run's while its number leads nothing else (R28)."""
    f = tmp_path / "child.pid"
    log, now = Log(), [at("2026-10-14 12:00")]
    cmd = ["/bin/sh", "-c", f'/bin/sh -c "{_STUBBORN_CHILD.format(f=f)}" & sleep 1']
    first = make_scheduler(tmp_path, [command_schedule(cmd, timeout_s=600)], log, now)
    now[0] = at("2026-10-14 12:05")
    first.tick()
    kid = _pid_in(f)
    try:
        first.running["check"].proc.wait(timeout=5)
        make_scheduler(tmp_path, [command_schedule(cmd, timeout_s=600)], log, now)   # restarted
        assert not _alive(kid), "the abandoned run's child outlived the daemon that started it"
        done = log.of(sc.EVENT_DONE)
        assert len(done) == 1 and "its process group was stopped" in done[0]["outcome"]
    finally:
        _reap(kid)
