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


#: A declaration with an isolated prompt run routes the notice a denied run raises (R32).
ROUTED = {"pd_run_failed": "agent"}


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
    path.write_text(Declaration(version=1, agent="Tester@abc123", timezone="UTC", schedules=[schedule],
                               notice_routes=ROUTED).model_dump_json())
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
        Declaration(version=1, agent="Tester@abc123", schedules=[schedule], notice_routes=ROUTED)
    with pytest.raises(ValidationError, match="unknown timezone"):
        Declaration(version=1, agent="Tester@abc123", timezone="Mars/Olympus", schedules=[schedule],
                    notice_routes=ROUTED)
    declared = Declaration(version=1, agent="Tester@abc123", timezone="America/New_York", schedules=[schedule],
                           notice_routes=ROUTED)
    assert declared.schedules[0].restarts_unit is False
    assert Declaration(version=1, agent="Tester@abc123").timezone is None


# --- the scheduler: the daemon runs what the schedules owe ----------------------

import json  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402
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


def make_scheduler(tmp_path, schedules, log, now, **options):
    decl = Declaration(version=1, agent=CARD, timezone="UTC", schedules=schedules, notice_routes=ROUTED)
    s = sc.Scheduler(decl, CARD, {"agent_home": str(tmp_path)}, work_dir=tmp_path / "runs",
                     append=log.append, events=log.read, now=lambda: now[0], **options)
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


def test_a_command_runs_with_its_declared_environment(tmp_path):
    """A run gets PATH and HOME, plus what its CommandRun declares, rendered like a unit's
    environment; a declared PATH overrides the default; nothing else of the daemon's leaks in."""
    seen = tmp_path / "seen"
    command = ["/bin/sh", "-c", f"env > {seen}"]
    schedule = Schedule(name="check", cron="*/5 * * * *", missed_run=policy("skip"), target="isolated",
                        timeout_s=30.0, run=CommandRun(command=command, wake_when="exit_code", environment={
                            "TMUX_TMPDIR": "{agent_home}/tmux", "PATH": "/opt/bin:/usr/bin:/bin"}))
    log, now = Log(), [at("2026-10-14 12:00")]
    s = make_scheduler(tmp_path, [schedule], log, now)
    now[0] = at("2026-10-14 12:05")
    s.tick()
    finish(s)
    env = dict(line.split("=", 1) for line in seen.read_text().splitlines() if "=" in line)
    assert env["TMUX_TMPDIR"] == f"{tmp_path}/tmux"
    assert env["PATH"] == "/opt/bin:/usr/bin:/bin" and env["HOME"] == str(tmp_path)
    assert "MACF_EVENTS_LOG_PATH" not in env and "USER" not in env


def test_a_command_environment_names_only_known_placeholders():
    with pytest.raises(ValueError, match="unknown placeholder"):
        CommandRun(command=["true"], wake_when="exit_code", environment={"X": "{nonsense}"})


@pytest.mark.parametrize("name", ["", "A=B", "1ABC", "WITH SPACE", "DASH-ED"])
def test_an_environment_name_a_process_cant_carry_is_refused_at_load(name):
    """Loaded, it would fail every run in subprocess; refused, it fails where it's written.
    Units get the same check."""
    from macf.pd.interface import Unit
    with pytest.raises(ValueError, match="environment names"):
        CommandRun(command=["true"], wake_when="exit_code", environment={name: "x"})
    with pytest.raises(ValueError, match="environment names"):
        Unit(name="u", command=["true"], account="a", restart="always", liveness_interval_s=1,
             memory_limit_mb=1, environment={name: "x"})
    CommandRun(command=["true"], wake_when="exit_code", environment={"_OK_1": "x"})


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


def test_a_prompt_run_it_cannot_start_is_said_not_run_once(tmp_path, monkeypatch):
    """A prompt run into a named live session, and any prompt run where no client is on the
    daemon's PATH, is said not run once, with why, and never started."""
    monkeypatch.setattr(sc.shutil, "which", lambda name, path=None: None)
    log, now = Log(), [at("2026-10-14 12:00")]
    named = Schedule(name="digest", cron="0 * * * *", missed_run=policy("skip"), target="Other@def456",
                     run=PromptRun(prompt_file="p.md"), timeout_s=60)
    isolated = Schedule(name="sweep", cron="0 * * * *", missed_run=policy("skip"), target="isolated",
                        run=PromptRun(prompt_file="p.md"), timeout_s=60)
    s = make_scheduler(tmp_path, [named, isolated], log, now)
    now[0] = at("2026-10-14 13:00")
    s.tick()
    said = {d["schedule"]: d["reason"] for d in log.of(sc.EVENT_NOT_RUN)}
    assert "named live session" in said["digest"] and "no Claude Code client" in said["sweep"]
    assert len(log.of(sc.EVENT_NOT_RUN)) == 2 and not log.of(sc.EVENT_STARTED)


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


# --- R25 and R33 -----------------------------------------------------------------

@pytest.mark.parametrize("kind", ["skip", "run_once", "run_once_in_window", "report_only"])
def test_policy_values(kind):
    """MIS-0002-R25 (missed-run_policy_MUST_be_listed): the four listed policies are the
    only ones; any other value is refused, never mapped to the nearest."""
    window = Window(start="01:00", end="03:00") if kind == "run_once_in_window" else None
    assert MissedRunPolicy(kind=kind, window=window).kind == kind
    import typing
    kind_field = MissedRunPolicy.model_fields["kind"].annotation
    assert set(typing.get_args(kind_field)) == {"skip", "run_once", "run_once_in_window", "report_only"}
    for other in ("catch_up_all", "run_all", "", "Skip", "skip "):
        with pytest.raises(ValueError):
            MissedRunPolicy(kind=other)


def test_run_cannot_schedule(tmp_path):
    """MIS-0002-R33 (run_MUST-NOT_change_schedules), within one daemon's life: the scheduler
    holds the declaration it was given and reads no file again, so a run that rewrites the
    declaration on disk, adding a schedule and removing its own, changes nothing the
    scheduler runs. (Across a daemon restart the new daemon reads whatever the file says;
    that path is the declaration's owner's to close, not the scheduler's.)"""
    log, now = Log(), [at("2026-10-14 12:00")]
    from macf.pd.names import declaration_path
    on_disk = declaration_path(tmp_path)            # where a daemon over this home reads it
    on_disk.parent.mkdir(parents=True, exist_ok=True)
    rewritten = Declaration(version=1, agent=CARD, timezone="UTC",
                            schedules=[command_schedule(["/usr/bin/true"], name="planted", cron="* * * * *")])
    original = command_schedule([sys.executable, "-c",
                                 f"open({str(on_disk)!r}, 'w').write({rewritten.model_dump_json()!r})"])
    s = make_scheduler(tmp_path, [original], log, now)
    on_disk.write_text(s.declaration.model_dump_json())
    now[0] = at("2026-10-14 12:05")
    s.tick()
    finish(s)
    assert "planted" in on_disk.read_text()                     # the run did rewrite the file
    assert [x.name for x in s.declaration.schedules] == ["check"]
    for minute in ("12:06", "12:07", "12:08", "12:09", "12:10"):
        now[0] = at(f"2026-10-14 {minute}")
        s.tick()
        finish(s)
    started = [d["schedule"] for d in log.of(sc.EVENT_STARTED)]
    assert started == ["check", "check"]                        # 12:05 and 12:10, and nothing planted

    # Across a restart, on a host: the next daemon reads the rewritten file. It runs only
    # what pd install recorded, and says the rest isn't run until installed again.
    installed = sc.schedule_digests(Declaration(version=1, agent=CARD, timezone="UTC", schedules=[original],
                                                notice_routes=ROUTED))
    owed, after = [], Log()
    after.append(sc.EVENT_INSTALLED, {"agent": CARD, "digests": installed})
    restarted = sc.Scheduler(Declaration.model_validate_json(on_disk.read_text()), CARD,
                             {"agent_home": str(tmp_path)}, work_dir=tmp_path / "runs", append=after.append,
                             events=after.read, now=lambda: now[0], check_installed=True,
                             on_notice=lambda source, nid: owed.append(source) or True)
    restarted.boot()
    now[0] = at("2026-10-14 12:11")
    restarted.tick()
    assert not after.of(sc.EVENT_STARTED) and "planted" not in restarted.runnable
    assert "added since the last pd install" in after.of(sc.EVENT_NOT_RUN)[0]["reason"]
    assert owed == ["pd_schedule_changed"]


def _fake_client(tmp_path, denials):
    """A stand-in for the Claude Code client: it records what it was started with and the
    settings it was handed, reads its prompt, and answers as print mode does in JSON."""
    client = tmp_path / "claude"
    client.write_text(f"""#!{sys.executable}
import json, os, sys
argv = sys.argv[1:]
settings = json.load(open(argv[argv.index("--settings") + 1]))
json.dump({{"argv": argv, "settings": settings, "prompt": sys.stdin.read(), "cwd": os.getcwd(),
           "found": sorted(os.listdir(".")), "env": sorted(os.environ), "path": os.environ.get("PATH")}}, open({str(tmp_path / "started.json")!r}, "w"))
os.makedirs(".claude", exist_ok=True)              # a run that leaves project settings behind
open(".claude/settings.json", "w").write('{{"permissions": {{"allow": ["Bash"]}}}}')
json.dump([{{"type": "system"}}, {{"type": "assistant"}},
           {{"type": "result", "is_error": False, "result": "done", "permission_denials": {denials!r}}}],
          sys.stdout)
""")
    client.chmod(0o755)
    (tmp_path / "p.md").write_text("Sweep the open pull requests.\n")
    return str(client)


def _prompt_schedule(allowed=("Bash(gh pr list:*)",)):
    return Schedule(name="sweep", cron="0 * * * *", missed_run=policy("skip"), target="isolated",
                    run=PromptRun(prompt_file="p.md", allowed_tools=list(allowed)), timeout_s=60)


def test_permissions_settled(tmp_path):
    """MIS-0002-R31 (schedule_MUST_settle_permission_at_creation): a prompt run's client loads
    the schedule's declared tools and nothing else. No user, project or local settings, no MCP
    server, no prompt answerer, and anything undeclared denied without asking. The settings
    are written again from the declaration before every run, so a run that widened them on
    disk, or left project settings in its working directory, has widened nothing for the next."""
    log, now = Log(), [at("2026-10-14 12:00")]
    s = make_scheduler(tmp_path, [_prompt_schedule()], log, now, client=_fake_client(tmp_path, []))
    for hour in ("13:00", "14:00"):
        now[0] = at(f"2026-10-14 {hour}")
        s.tick()
        finish(s)
        started = json.loads((tmp_path / "started.json").read_text())
        assert started["found"] == []          # a fresh directory each run: nothing a run left loads
        assert started["settings"] == {"permissions": {"allow": ["Bash(gh pr list:*)"], "defaultMode": "dontAsk"}}
        settings = Path(started["argv"][started["argv"].index("--settings") + 1])
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash"], "defaultMode": "bypassPermissions"}}))
    argv = started["argv"]
    for flag, value in (("--setting-sources", "project"), ("--permission-mode", "dontAsk"),
                        ("--permission-prompts", "none")):
        assert argv[argv.index(flag) + 1] == value
    assert "--strict-mcp-config" in argv and "--print" in argv
    assert not any("dangerously" in a or a.startswith("--allowed") for a in argv)
    assert started["prompt"] == "Sweep the open pull requests.\n"
    assert Path(started["cwd"]).resolve() == (tmp_path / "runs" / "sweep").resolve()
    assert [d["outcome"] for d in log.of(sc.EVENT_DONE)] == ["ok: the prompt ran"] * 2


def test_prompt_fails_run(tmp_path):
    """MIS-0002-R32 (run_MUST_fail_on_prompt): a prompt run the client denied anything met a
    permission prompt. It fails, naming the tools but never the result's text, and the agent
    is owed the pd_run_failed notice, once per run. A run denied nothing raises no notice."""
    log, now = Log(), [at("2026-10-14 12:00")]
    owed = []
    client = _fake_client(tmp_path, [{"tool_name": "Write", "tool_use_id": "t1", "tool_input": {"file_path": "/x"}},
                                     {"tool_name": "Bash", "tool_use_id": "t2", "tool_input": {"command": "rm -rf ~"}}])
    s = make_scheduler(tmp_path, [_prompt_schedule()], log, now, client=client,
                       on_notice=lambda source, nid: owed.append((source, nid)) or True)
    now[0] = at("2026-10-14 13:00")
    s.tick()
    finish(s)
    done = log.of(sc.EVENT_DONE)[0]
    assert done["outcome"].startswith("failed: met a permission prompt for Bash, Write")
    assert "rm -rf" not in json.dumps(log.rows) and "done" not in done["outcome"]
    assert owed == [("pd_run_failed", "sweep:2026-10-14T13:00:00+00:00")]

    quiet = Log()
    s = make_scheduler(tmp_path, [_prompt_schedule()], quiet, now, client=_fake_client(tmp_path, []),
                       on_notice=lambda source, nid: owed.append((source, nid)) or True)
    now[0] = at("2026-10-14 14:00")
    s.tick()
    finish(s)
    assert quiet.of(sc.EVENT_DONE)[0]["outcome"] == "ok: the prompt ran" and len(owed) == 1


def test_an_isolated_prompt_run_routes_its_failure_notice():
    """R32's notice must reach someone: a declaration with an isolated prompt run is refused at
    load unless it routes pd_run_failed where the notice is delivered, to the agent."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="pd_run_failed"):
        Declaration(version=1, agent=CARD, timezone="UTC", schedules=[_prompt_schedule()])
    for nobody in ("operator", "held_until_present"):    # routes no daemon notice is delivered on yet
        with pytest.raises(ValidationError, match="'agent' or 'both'"):
            Declaration(version=1, agent=CARD, timezone="UTC", schedules=[_prompt_schedule()],
                        notice_routes={"pd_run_failed": nobody})
    for heard in ("agent", "both"):
        Declaration(version=1, agent=CARD, timezone="UTC", schedules=[_prompt_schedule()],
                    notice_routes={"pd_run_failed": heard})


def test_the_client_is_found_on_the_session_units_path(tmp_path, monkeypatch):
    """Review of #712. A daemon under launchd, or one linger starts before any login, has a PATH
    without the client. The scheduler looks where the core looks for the session's own client:
    the session unit's declared PATH, filled in from the placeholders, and the run gets that PATH."""
    from macf.pd.interface import Unit
    client = _fake_client(tmp_path, [])
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").symlink_to(client)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")                    # the service manager's
    session = Unit(name="session", kind="session", command=["/usr/bin/true"], account="tester",
                   restart="always", liveness_interval_s=10, memory_limit_mb=64,
                   environment={"PATH": "{agent_home}/bin:/usr/bin:/bin"})
    log, now = Log(), [at("2026-10-14 12:00")]
    decl = Declaration(version=1, agent=CARD, timezone="UTC", units=[session], schedules=[_prompt_schedule()],
                       notice_routes=ROUTED)
    s = sc.Scheduler(decl, CARD, {"agent_home": str(tmp_path)}, work_dir=tmp_path / "runs",
                     append=log.append, events=log.read, now=lambda: now[0])
    s.boot()
    assert s.client == str(bin_dir / "claude") and not log.of(sc.EVENT_NOT_RUN)
    now[0] = at("2026-10-14 13:00")
    s.tick()
    finish(s)
    assert json.loads((tmp_path / "started.json").read_text())["path"] == f"{tmp_path}/bin:/usr/bin:/bin"

    bare = Log()
    plain = sc.Scheduler(decl.model_copy(update={"units": []}), CARD, {"agent_home": str(tmp_path)},
                         work_dir=tmp_path / "runs", append=bare.append, events=bare.read, now=lambda: now[0])
    plain.boot()
    assert "the daemon's PATH (/usr/bin:/bin)" in bare.of(sc.EVENT_NOT_RUN)[0]["reason"]


@pytest.mark.parametrize("record, check, runs", [
    ("same", True, True),            # installed as it is
    ("changed", True, False),        # the command changed since install
    ("none", True, False),           # no install recorded
    ("changed", False, True),        # a rendered declaration: out of the agent's reach, not checked
])
def test_a_host_runs_only_the_schedules_pd_install_recorded(tmp_path, record, check, runs):
    """MIS-0002-R33 on a host: a daemon runs a schedule only as pd install recorded it. One
    whose digest differs, or with no record at all, is said not run once, with how to accept
    it. A daemon over a rendered declaration checks nothing, since no run can change that."""
    log, now = Log(), [at("2026-10-14 12:00")]
    declared = command_schedule(["/usr/bin/true"])
    if record != "none":
        took = command_schedule(["/usr/bin/false"]) if record == "changed" else declared
        log.append(sc.EVENT_INSTALLED, {"agent": CARD, "digests": sc.schedule_digests(
            Declaration(version=1, agent=CARD, timezone="UTC", schedules=[took]))})
    s = make_scheduler(tmp_path, [declared], log, now, check_installed=check)
    now[0] = at("2026-10-14 12:05")
    s.tick()
    finish(s)
    assert bool(log.of(sc.EVENT_STARTED)) == runs
    if not runs:
        assert "pd install" in log.of(sc.EVENT_NOT_RUN)[0]["reason"]


def test_pd_install_records_each_schedules_digest(tmp_path, monkeypatch):
    """pd install records what it took, so the daemon has something to check against, and a
    timezone change counts as a change to every schedule read in it."""
    from macf.pd import cli
    recorded = []
    monkeypatch.setattr("macf.agent_events_log.append_event", lambda e, d: recorded.append((e, d)) or True)
    decl = Declaration(version=1, agent=CARD, timezone="UTC", schedules=[command_schedule(["/usr/bin/true"])])
    cli._record_schedules(CARD, decl, tmp_path)
    assert recorded == [(sc.EVENT_INSTALLED, {"agent": CARD, "digests": sc.schedule_digests(decl)})]
    moved = decl.model_copy(update={"timezone": "America/New_York"})
    assert sc.schedule_digests(moved)["check"] != sc.schedule_digests(decl)["check"]


def test_a_rewritten_prompt_file_counts_as_a_change(tmp_path):
    """Review of #713. A prompt file sits in the agent's home, where a run allowed to write
    there could rewrite its own future instructions, so its bytes are part of the digest."""
    decl = Declaration(version=1, agent=CARD, timezone="UTC", schedules=[_prompt_schedule()], notice_routes=ROUTED)
    (tmp_path / "p.md").write_text("Sweep the open pull requests.\n")
    took = sc.schedule_digests(decl, tmp_path)
    assert sc.schedule_digests(decl, tmp_path) == took
    (tmp_path / "p.md").write_text("Sweep the open pull requests, then push to main.\n")
    assert sc.schedule_digests(decl, tmp_path)["sweep"] != took["sweep"]


def test_pd_install_records_before_the_daemon_can_start(tmp_path, monkeypatch):
    """Review of #713. launchd starts the daemon as the job loads (RunAtLoad), so the install
    record must be in the log before the service manager is asked, or the daemon refuses
    every schedule it reads in that moment."""
    import argparse
    import macf
    from macf.pd import adapter as adapters
    from macf.pd import cli
    order = []
    decl = Declaration(version=1, agent=CARD, timezone="UTC", schedules=[command_schedule(["/usr/bin/true"])])

    class Tier:
        def install(self, card, home, force=False):
            order.append("install")
            return tmp_path / "unit"

        def status(self, card):
            return "running"

    monkeypatch.setattr(cli, "_this_agent", lambda: (tmp_path, CARD))
    monkeypatch.setattr("macf.pd.core.load_declaration", lambda home, card: decl)
    monkeypatch.setattr(adapters, "adapter_for", lambda platform: Tier())
    monkeypatch.setattr(cli, "daemon_macf", lambda python: (Path(macf.__file__).resolve().parent, ""))
    monkeypatch.setattr("macf.agent_events_log.append_event", lambda e, d: order.append(e) or True)
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    assert cli.cmd_pd_install(argparse.Namespace(plan=False, force=False)) == 0
    assert order == [sc.EVENT_INSTALLED, "install"]


def test_a_run_gets_the_prompt_read_at_start(tmp_path):
    """Review of #713. The prompt is read once, at boot, where its digest is checked, and every
    run in that daemon's life gets those bytes. A run that rewrites the file in the home changes
    nothing until the next start, where the check refuses it."""
    log, now = Log(), [at("2026-10-14 12:00")]
    s = make_scheduler(tmp_path, [_prompt_schedule()], log, now, client=_fake_client(tmp_path, []))
    (tmp_path / "p.md").write_text("Sweep the open pull requests, then push to main.\n")   # a run's rewrite
    now[0] = at("2026-10-14 13:00")
    s.tick()
    finish(s)
    assert json.loads((tmp_path / "started.json").read_text())["prompt"] == "Sweep the open pull requests.\n"
