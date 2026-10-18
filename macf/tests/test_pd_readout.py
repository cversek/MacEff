"""Each declared unit's health, derived from events alone (MIS-0002-R15, R16)."""
import json
import os
import pwd
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from macf.notify.session import proc_start
from macf.pd.health import ABSENT, ALIVE, GONE, STALE, UNREADABLE, health
from macf.pd.interface import Declaration, Unit

CARD = "Tester@abc123"


def declaration(*names):
    return Declaration(version=1, agent=CARD, units=[
        Unit(name=n, command=["true"], account="tester", restart="always",
             liveness_interval_s=10.0, memory_limit_mb=64) for n in names])


def alive(unit, *, at, pid=4242, start="t0", interval=10.0, card=CARD, **extra):
    return {"timestamp": at, "event": "pd_unit_alive",
            "data": {"agent": card, "unit": unit, "pid": pid, "proc_start": start,
                     "interval_s": interval, **extra}}


def state(unit, value, *, at, reason="because", card=CARD):
    return {"timestamp": at, "event": "pd_unit_state",
            "data": {"agent": card, "unit": unit, "state": value, "reason": reason}}


def by_unit(results):
    return {h.unit: h for h in results}


def test_liveness_probed():
    """ALIVE needs a recent liveness and the very process it names (R15).

    The probe is asked with the pid and start time the unit wrote; a pid that now
    belongs to another process reads GONE however recent the write. The default
    probe is checked against this test's own process, with its own start time and with
    pid 1's, which a probe that looked at the pid alone would accept.
    """
    now = time.time()
    asked = []

    def probe(pid, start):
        asked.append((pid, start))
        return start == "t0"

    found = by_unit(health(declaration("worker", "imposter"), [
        alive("worker", at=now - 5),
        alive("imposter", at=now - 5, start="t1"),
    ], now, probe))
    assert found["worker"].liveness == ALIVE
    assert found["imposter"].liveness == GONE and "no longer the process" in found["imposter"].detail
    assert sorted(asked) == [(4242, "t0"), (4242, "t1")]

    me = os.getpid()
    real = health(declaration("worker"), [alive("worker", at=now - 5, pid=me, start=proc_start(me))], now)
    assert real[0].liveness == ALIVE
    wrong = proc_start(1)   # pid 1's start: real on Linux and macOS, never this process's
    assert health(declaration("worker"), [alive("worker", at=now - 5, pid=me, start=wrong)], now)[0].liveness == GONE


def test_stopped_never_started_and_unreadable():
    """Stopped, never started and unreadable are three verdicts, none of them ALIVE."""
    now = time.time()
    garbled = {"timestamp": now - 1, "event": "pd_unit_alive", "data": {"agent": CARD, "unit": "garbled"}}
    found = by_unit(health(declaration("stopped", "never", "garbled"), [
        alive("stopped", at=now - 300),
        state("never", "starting", at=now - 2),
        garbled,
    ], now, lambda pid, start: True))
    assert found["stopped"].liveness == STALE and "300 s ago" in found["stopped"].detail
    assert found["never"].liveness == ABSENT
    assert found["garbled"].liveness == UNREADABLE


def test_each_declared_unit_once_and_nothing_else():
    """Declared units in declaration order, once each, however many events name them.
    Another agent's events and an undeclared unit's are ignored, so neither can read
    as a healthy unit of this agent."""
    now = time.time()
    results = health(declaration("worker", "broker"), [
        state("worker", "starting", at=now - 10),
        state("worker", "running", at=now - 9),
        alive("worker", at=now - 1),
        alive("worker", at=now - 1, card="Someone@ffffff", pid=1111),
        alive("stray", at=now - 1),
    ], now, lambda pid, start: True)
    assert [h.unit for h in results] == ["worker", "broker"]
    assert results[0].pid == 4242 and results[1].liveness == ABSENT


def test_state_is_the_last_recorded():
    """The state reported is the daemon's latest for the unit, with its reason and time."""
    now = time.time()
    found = health(declaration("worker"), [
        state("worker", "starting", at=now - 30),
        state("worker", "running", at=now - 29),
        state("worker", "failed", at=now - 3, reason="exited 1"),
    ], now, lambda pid, start: True)[0]
    assert (found.state, found.reason, found.since) == ("failed", "exited 1", now - 3)


def test_work_in_flight_and_a_wait_are_carried():
    """What the unit last reported (R21, R49) reaches the reader with the verdict."""
    now = time.time()
    found = health(declaration("session"), [
        alive("session", at=now - 2, in_flight=2, waiting_on="a permission prompt"),
    ], now, lambda pid, start: True)[0]
    assert (found.liveness, found.in_flight, found.waiting_on) == (ALIVE, 2, "a permission prompt")


def test_the_watch_and_the_readout_agree():
    """The outside watch gives the readout's verdict on the same event (R15, R16): both
    apply ``read_liveness``, so neither can drift to its own bound or probe. The stale
    case sits between three and four intervals, where a second bound would part them."""
    from macf.pd import watch

    now = time.time()
    decl = declaration("worker")
    cases = {
        "absent": None,
        "unreadable": {"timestamp": now - 5, "event": "pd_unit_alive",
                       "data": {"agent": CARD, "unit": "worker"}},
        "stale": alive("worker", at=now - 35),
        "gone": alive("worker", at=now - 5, start="t1"),
        "alive": alive("worker", at=now - 5),
    }
    for name, event in cases.items():
        readout = health(decl, [event] if event else [], now, lambda pid, start: start == "t0")[0]
        watched = watch.check_unit(CARD, decl.units[0], event, now, lambda pid, start: start == "t0")
        assert readout.liveness == watched.verdict == name.upper(), (name, readout, watched)


@pytest.mark.parametrize("bad_unit", [["worker"], {"name": "worker"}])
def test_a_row_whose_unit_is_not_a_name_costs_only_itself(bad_unit):
    """A row whose unit is a list or a dict is skipped like any other malformed row; it must
    not stop the readout and take every unit's verdict with it."""
    now = time.time()
    bad = alive("worker", at=now - 1)
    bad["data"]["unit"] = bad_unit
    rows = [alive("worker", at=now - 5), bad]
    found = by_unit(health(declaration("worker"), rows, now, lambda pid, start: True))
    assert found["worker"].liveness == ALIVE


def test_a_malformed_row_costs_only_itself():
    """A row that isn't an event, or whose data isn't one, is skipped. One bad line in the
    log takes away no other unit's verdict."""
    now = time.time()
    rows = ["not an event", {"event": "pd_unit_alive", "data": "not data"}, alive("worker", at=now - 5)]
    found = by_unit(health(declaration("worker"), rows, now, lambda pid, start: True))
    assert found["worker"].liveness == ALIVE


def test_tray_unavailable_said(tmp_path, monkeypatch, capsys):
    """Where this host can't show the tray, the readout says so and why (R73): in the report
    whatever its source, in the JSON, and on the printed readout."""
    from macf.cli import main
    from macf.pd import client
    from macf.pd.interface import declaration_path
    from macf.platform.tray_host import TrayHost

    home = tmp_path / "home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text("abc123def4567890\n")
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"moniker": "Tester"}}))
    nobody = TrayHost(False, "nobody is logged in to the GUI")
    said = "tray: unavailable (nobody is logged in to the GUI)"
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(home))

    assert client.status(home, CARD, host=lambda: nobody).tray == said
    declaration_path(home).parent.mkdir(parents=True)
    me = pwd.getpwuid(os.getuid()).pw_name
    declared = Declaration(version=1, agent=CARD, units=[
        Unit(name="worker", command=["true"], account=me, restart="never",
             liveness_interval_s=60, memory_limit_mb=64)])
    declaration_path(home).write_text(declared.model_dump_json())
    base = tempfile.mkdtemp(prefix="pd-", dir="/tmp")
    try:
        report = client.status(home, CARD, base=Path(base), host=lambda: nobody)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    assert (report.source, report.tray) == ("event log", said)

    monkeypatch.setattr(client, "tray_host", lambda: nobody)
    for argv in (["pd", "status"], ["pd", "status", "--json"]):
        with pytest.raises(SystemExit) as exited:
            main(argv)
        assert exited.value.code == 0
        out = capsys.readouterr().out.strip().splitlines()
        if "--json" in argv:
            assert json.loads(out[-1])["tray"] == said
        else:
            assert out[-1] == said


def _scheduled(policy="skip"):
    from macf.pd.interface import CommandRun, MissedRunPolicy, Schedule
    return Declaration(version=1, agent=CARD, timezone="UTC", schedules=[
        Schedule(name="hourly", cron="0 * * * *", missed_run=MissedRunPolicy(kind=policy),
                 target="isolated", run=CommandRun(command=["true"], wake_when="exit_code"),
                 timeout_s=60)])


def _run(kind, stamp, card=CARD, **data):
    return {"timestamp": stamp, "event": kind, "data": {"agent": card, "schedule": "hourly", **data}}


H10 = 1792231200.0   # 2026-10-17T10:00:00Z, a firing of the hourly cron


def test_health_is_runs():
    """R17: a schedule's health is derived from runs owed and runs done, when it is read.

    The same events read at a later moment give a later verdict: a run owed and not yet
    started is DUE, then OVERDUE once its grace has passed, with nothing written between.
    A start holds it RUNNING, its end says OK or FAILED, and a firing the declared policy
    marked missed is accounted for, not overdue. Another agent's runs count for nothing."""
    from macf.pd.health import START_GRACE_S, schedule_health

    def verdict(events, now):
        return schedule_health(_scheduled(), events, now)[0].verdict

    iso = "2026-10-17T10:00:00+00:00"
    seen = [_run("pd_schedule_seen", H10 - 1800, at="2026-10-17T09:30:00+00:00")]
    assert verdict([], H10) == "NONE_OWED"
    assert verdict(seen, H10 - 60) == "NONE_OWED"
    assert verdict(seen, H10 + 5) == "DUE"
    assert verdict(seen, H10 + START_GRACE_S + 1) == "OVERDUE"
    # Two firings owed: the 10:00 run is the late one, however fresh the 11:00 firing is.
    two = schedule_health(_scheduled(), seen, H10 + 3600 + 30)[0]
    assert two.verdict == "OVERDUE" and two.owed == iso and "1 more owed" in two.detail
    assert verdict(seen + [_run("pd_run_started", H10 + 1, scheduled_for=iso, card="Other@000000")],
                   H10 + 120) == "OVERDUE"
    started = seen + [_run("pd_run_started", H10 + 1, scheduled_for=iso)]
    assert verdict(started, H10 + 30) == "RUNNING"
    assert verdict(started, H10 + 60 + 5 + START_GRACE_S + 2) == "OVERDUE"   # past its limit, no end
    ok = started + [_run("pd_run_done", H10 + 3, scheduled_for=iso, outcome="ok: nothing to say")]
    assert verdict(ok, H10 + 600) == "OK"
    failed = started + [_run("pd_run_done", H10 + 3, scheduled_for=iso, outcome="failed: exit 2")]
    assert verdict(failed, H10 + 600) == "FAILED"
    assert verdict(ok, H10 + 3600 + START_GRACE_S + 1) == "OVERDUE"       # the next hour's run
    skipped = ok + [_run("pd_run_missed", H10 + 7300, count=1, policy="skip",
                         first="2026-10-17T11:00:00+00:00", last="2026-10-17T11:00:00+00:00")]
    assert verdict(skipped, H10 + 3600 + START_GRACE_S + 1) == "OK"


def test_overdue_is_unhealthy(monkeypatch):
    """R18: while the daemon answers, which is how it is known alive, a run it owes that is
    overdue makes the readout report it unhealthy, naming the schedule. When it is not
    overdue the daemon reads healthy, and when no daemon answers the runs are still listed
    but no daemon is called healthy or not."""
    from macf.pd import client
    from macf.pd.health import START_GRACE_S

    events = [_run("pd_schedule_seen", H10 - 1800, at="2026-10-17T09:30:00+00:00")]
    monkeypatch.setattr(client, "load_declaration", lambda home, card: _scheduled())
    monkeypatch.setattr(client, "read_events", lambda **k: iter(sorted(events, key=lambda e: -e["timestamp"])))
    source = ["daemon"]
    monkeypatch.setattr(client, "_units", lambda home, card, base=None, now=None:
                        client.StatusReport(card=card, source=source[0], why="test"))

    def host():
        return client.TrayHost(True, "")

    report = client.status(Path("/nonexistent"), CARD, now=H10 + START_GRACE_S + 1, host=host)
    assert report.runs == "unhealthy: hourly OVERDUE"
    failed = events + [_run("pd_run_started", H10 + 1, scheduled_for="2026-10-17T10:00:00+00:00"),
                       _run("pd_run_done", H10 + 2, scheduled_for="2026-10-17T10:00:00+00:00", outcome="failed: exit 2")]
    events[:] = failed
    outcome = client.status(Path("/nonexistent"), CARD, now=H10 + 600, host=host)
    assert (outcome.schedules[0]["verdict"], outcome.runs) == ("FAILED", "healthy")   # an outcome, not overdue
    events[:] = failed[:1]
    assert report.schedules[0]["owed"] == "2026-10-17T10:00:00+00:00"
    assert client.status(Path("/nonexistent"), CARD, now=H10 + 5, host=host).runs == "healthy"
    source[0] = "event log"
    report = client.status(Path("/nonexistent"), CARD, now=H10 + START_GRACE_S + 1, host=host)
    assert (report.runs, report.schedules[0]["verdict"]) == ("", "OVERDUE")


def test_a_run_waiting_as_declared_or_never_started_is_not_overdue():
    """Review of #711. A missed run its policy defers to a window reads DUE until the window
    opens, then OVERDUE if it still hasn't started. A run that never started, for a missing
    placeholder say, ends with a done record for its firing: it reads FAILED, an outcome, not
    a firing still owed."""
    from macf.pd.health import START_GRACE_S, schedule_health
    from macf.pd.interface import CommandRun, MissedRunPolicy, Schedule, Window
    daily = Declaration(version=1, agent=CARD, timezone="UTC", schedules=[
        Schedule(name="hourly", cron="0 9 * * *", target="isolated", timeout_s=60,
                 missed_run=MissedRunPolicy(kind="run_once_in_window", window=Window(start="22:00", end="23:00")),
                 run=CommandRun(command=["true"], wake_when="exit_code"))])
    nine, ten30, twenty2 = H10 - 3600, H10 + 1800, H10 + 12 * 3600
    rows = [_run("pd_schedule_seen", nine - 86400, at="2026-10-16T09:00:00+00:00"),
            _run("pd_run_started", nine - 86400, scheduled_for="2026-10-16T09:00:00+00:00"),
            _run("pd_run_done", nine - 86390, scheduled_for="2026-10-16T09:00:00+00:00", outcome="ok: nothing to say"),
            _run("pd_run_deferred", ten30, scheduled_for="2026-10-17T09:00:00+00:00",
                 run_at="2026-10-17T22:00:00+00:00", policy="run_once_in_window")]
    waiting = schedule_health(daily, rows, ten30 + 60)[0]
    assert waiting.verdict == "DUE" and "waits for its window" in waiting.detail
    assert schedule_health(daily, rows, twenty2 + START_GRACE_S + 1)[0].verdict == "OVERDUE"

    iso = "2026-10-17T10:00:00+00:00"
    never = [_run("pd_schedule_seen", H10 - 1800, at="2026-10-17T09:30:00+00:00"),
             _run("pd_run_done", H10 + 1, scheduled_for=iso, outcome="not started: no value for the placeholder {x}")]
    assert schedule_health(_scheduled(), never, H10 + 600)[0].verdict == "FAILED"
