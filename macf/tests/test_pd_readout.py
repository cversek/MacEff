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

CARD = "Tester_abc123"


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
        alive("worker", at=now - 1, card="Someone_ffffff", pid=1111),
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
    assert verdict(seen + [_run("pd_run_started", H10 + 1, scheduled_for=iso, card="Other_000000")],
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


def test_a_command_schedule_the_daemon_refused_reads_not_run(monkeypatch):
    """A command schedule the daemon refused at its start, as a host refuses one changed since
    the last pd install (R33), reads NOT_RUN, and the daemon stays healthy: it declined the run
    on purpose, so the run isn't overdue (#735). A refusal at an earlier daemon's start counts
    for nothing once a later start took the schedule."""
    from macf.pd import client
    from macf.pd.health import START_GRACE_S
    from macf.pd.interface import EVENT_DAEMON_START

    def daemon_start(stamp):
        return {"timestamp": stamp, "event": EVENT_DAEMON_START,
                "data": {"agent": CARD, "pid": 4242, "proc_start": "t0"}}

    events = [_run("pd_schedule_seen", H10 - 1800, at="2026-10-17T09:30:00+00:00"), daemon_start(H10 - 600),
              _run("pd_schedule_not_run", H10 - 599, reason="it changed since the last pd install")]
    monkeypatch.setattr(client, "load_declaration", lambda home, card: _scheduled())
    monkeypatch.setattr(client, "read_events", lambda **k: iter(sorted(events, key=lambda e: -e["timestamp"])))
    monkeypatch.setattr(client, "_units", lambda home, card, base=None, now=None:
                        client.StatusReport(card=card, source="daemon", why="test"))

    def report():
        return client.status(Path("/nonexistent"), CARD, now=H10 + START_GRACE_S + 1,
                             host=lambda: client.TrayHost(True, ""))

    refused = report()
    assert (refused.schedules[0]["verdict"], refused.runs) == ("NOT_RUN", "healthy")
    events.append(daemon_start(H10 - 300))                          # a later daemon took it
    taken = report()
    assert (taken.schedules[0]["verdict"], taken.runs) == ("OVERDUE", "unhealthy: hourly OVERDUE")


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


def test_auth_failure_waits_on_login(tmp_path):
    """MIS-0002-R19 (auth_failure_MUST_read_waiting_on_person): the session's harness adapter reads a
    failed login from the transcript, in the shapes Claude Code writes it, and says so in the
    session's beat until a request goes through again. The daemon, hearing that beat, sets the
    session's state to waiting on a person with the login named as data, keeps the same process
    running so a person can attach and log in, tells the wake it waits on its login, and returns
    it to running once the beat says it can authenticate again."""
    from macf.pd.interface import LOGIN_WAIT
    from macf.pd.liveness import liveness_event
    from macf.transcript_monitor.daemon import AuthWatch
    import test_primal_daemon as tpd

    def said(text, error="authentication_failed"):
        return {"type": "assistant", "isApiErrorMessage": True, "error": error, "timestamp": "t",
                "message": {"role": "assistant", "model": "<synthetic>",       # as the client writes it
                            "content": [{"type": "text", "text": text}]}}

    reply = {"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-5",
                                              "content": [{"type": "text", "text": "ok"}]}}
    synthetic = {"type": "assistant", "message": {"role": "assistant", "model": "<synthetic>",
                                                  "content": [{"type": "text", "text": "No response requested."}]}}
    expired = "Login expired \u00b7 Please run /login"
    token = ('API Error: 401 {"type":"error","error":{"type":"authentication_error",'
             '"message":"OAuth token has expired."}}')

    # The adapter: the transcript's shapes, one record per failure, recovery by a real reply.
    watch = AuthWatch()
    assert watch(reply) is None and watch.state() is None
    assert watch(said(expired)).event_name == "auth_failure_detected"
    assert watch.state() == expired
    assert watch(said(token)) is None and watch.state() == expired
    assert watch({"type": "user", "message": {"content": "hello"}}) is None
    assert watch(said("Overloaded", error="overloaded")) is None and watch.state() == expired
    assert watch(synthetic) is None and watch.state() == expired         # the client wrote it: no request
    assert watch(reply).event_name == "auth_recovered" and watch.state() is None
    watch(said(token))
    beat = liveness_event(CARD, "session", 10.0, pid=os.getpid(), auth_failed=watch.state())
    assert beat.auth_failed.startswith("API Error: 401")

    # The daemon: a session whose beat carries the failure waits on its login, still running.
    script = tmp_path / "fake_unit.py"
    script.write_text(tpd.FAKE_UNIT)
    unit = tpd.make_unit("session", script, {"auth_failed": expired, "auth_failed_for": 2.0}, restart="always"
                         ).model_copy(update={"kind": "session"})
    declaration = Declaration(version=1, agent=tpd.CARD, units=[unit])
    core = tpd.Core(declaration, tpd.CARD, backoff_base_s=0.05, backoff_cap_s=0.2)
    try:
        core.boot()
        assert tpd.drive(core, lambda: core.state("session") == "waiting_on_a_person")
        pid = core.statuses()[0].pid
        rows = [json.loads(line) for line in tpd.get_log_path().read_text().splitlines()]
        record = [r["data"] for r in rows if r.get("event") == "pd_unit_state"
                  and r["data"].get("unit") == "session"][-1]
        assert record["state"] == "waiting_on_a_person" and record["waiting_on"] == LOGIN_WAIT
        assert record["reason"] == f"authentication failed: {expired}"
        found = health(declaration, rows, time.time(), lambda pid, start: True)[0]
        assert found.state == "waiting_on_a_person"
        status = core.statuses()[0]
        assert status.waiting_on == LOGIN_WAIT and status.auth_failed == expired and status.pid == pid
        assert core.session_waiting_on() == "its login"     # the wake holds: nothing typed into /login
        # Logged in again: the beat clears, and the same process is running again.
        assert tpd.drive(core, lambda: core.state("session") == "running")
        status = core.statuses()[0]
        assert status.pid == pid and status.waiting_on is None and core.session_waiting_on() is None
    finally:
        core.shutdown("the test is over")


def test_one_login_returns_every_session_waiting_on_it():
    """Where sessions share one stored credential, a /login in one renews it for all. The others,
    quiet, write no reply that would show it, so their monitors read the credential's expiry dates
    instead and clear once they change (Ira on #1161, point 3). Two sessions wait; a person logs in
    once; both are back. The dates alone are read, never a token."""
    from macf.transcript_monitor.daemon import AuthWatch, CREDENTIAL_RECHECK_S
    from macf.pd.login import credential_fingerprint
    expired = {"type": "assistant", "isApiErrorMessage": True, "error": "authentication_failed",
               "timestamp": "t", "message": {"role": "assistant", "model": "<synthetic>",
                                             "content": [{"type": "text", "text": "Login expired"}]}}
    stored = {"claudeAiOauth": {"accessToken": "secret-a", "refreshToken": "secret-r",
                                "expiresAt": 1_000_000, "refreshTokenExpiresAt": 2_000_000}}
    reads = []

    def credential():
        reads.append(1)
        return credential_fingerprint(reader=lambda: json.dumps(stored))

    clock = [0.0]
    first, second = (AuthWatch(credential=credential, clock=lambda: clock[0]) for _ in range(2))
    first(expired)
    second(expired)
    assert first.state() == second.state() == "Login expired"
    clock[0] += CREDENTIAL_RECHECK_S
    assert first.state() == second.state() == "Login expired", "nothing changed yet"
    # A person runs /login in the first session only: the stored credential gets new dates.
    stored["claudeAiOauth"].update(expiresAt=9_000_000, refreshTokenExpiresAt=8_000_000_000)
    clock[0] += 1
    assert first.state() == "Login expired", "read at most once a minute"
    clock[0] += CREDENTIAL_RECHECK_S
    assert first.state() is None and second.state() is None
    assert "secret" not in repr(credential_fingerprint(reader=lambda: json.dumps(stored)))


def test_a_credential_unread_at_the_failure_takes_its_next_reading_as_the_baseline():
    """No reading at the failure, then one: that one is the baseline, not a change, so an unreadable
    keychain at the moment of failure never clears the wait by itself."""
    from macf.transcript_monitor.daemon import AuthWatch, CREDENTIAL_RECHECK_S
    expired = {"type": "assistant", "isApiErrorMessage": True, "error": "authentication_failed",
               "timestamp": "t", "message": {"role": "assistant", "model": "<synthetic>",
                                             "content": [{"type": "text", "text": "Login expired"}]}}
    answers = iter([None, (1.0, 2.0), (1.0, 2.0), (3.0, 4.0)])
    clock = [0.0]
    watch = AuthWatch(credential=lambda: next(answers), clock=lambda: clock[0])
    watch(expired)                                   # the failure: unreadable (None)
    for _ in range(2):
        clock[0] += CREDENTIAL_RECHECK_S
        assert watch.state() == "Login expired"      # the baseline, then the same again
    clock[0] += CREDENTIAL_RECHECK_S
    assert watch.state() is None                     # changed: logged in again


def test_a_credential_that_wont_read_leaves_the_wait_and_says_so(capsys):
    """A stored credential that isn't the client's JSON raises in the reader. The wait stands, since
    nothing shows a login, and the monitor says why on its error stream rather than dropping it."""
    from macf.transcript_monitor.daemon import AuthWatch, CREDENTIAL_RECHECK_S
    from macf.pd.login import credential_fingerprint
    expired = {"type": "assistant", "isApiErrorMessage": True, "error": "authentication_failed",
               "timestamp": "t", "message": {"role": "assistant", "model": "<synthetic>",
                                             "content": [{"type": "text", "text": "Login expired"}]}}
    clock = [0.0]
    watch = AuthWatch(credential=lambda: credential_fingerprint(reader=lambda: "not json"),
                      clock=lambda: clock[0])
    watch(expired)
    clock[0] += CREDENTIAL_RECHECK_S
    assert watch.state() == "Login expired"
    assert "couldn't be read" in capsys.readouterr().err


@pytest.mark.parametrize("said,kind", [
    ("Login expired \u00b7 Please run /login", "login"),
    ('API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"OAuth token has expired."}}', "login"),
    ("Invalid API key \u00b7 Fix external API key", "credential"),
    ("authentication failed", "login"),
    (None, "login"),
])
def test_what_the_adapter_read_names_the_wait(said, kind):
    """MIS-0002-R19 names what the session waits on from what the client said: a rejected API key
    waits on its credential, where no /login helps; every other failure waits on its login."""
    from macf.pd.interface import auth_wait
    assert auth_wait(said) == kind


def test_a_seat_with_its_own_config_dir_reads_no_credential(monkeypatch):
    """A seat with CLAUDE_CONFIG_DIR keeps its own credential, and the reader takes the default one, so
    another seat's /login would end this seat's login wait. Until the reader follows the config dir, such
    a seat reads no credential and its wait ends only by a reply (CTB's review of #1163)."""
    import macf.budget as budget
    from macf.pd.login import credential_fingerprint
    stored = json.dumps({"claudeAiOauth": {"expiresAt": 1_000_000, "refreshTokenExpiresAt": 2_000_000}})
    monkeypatch.setattr(budget, "read_credential", lambda: stored)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert credential_fingerprint() == (2000.0, 1000.0)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/home/seat/.claude-seat")
    assert credential_fingerprint() is None

