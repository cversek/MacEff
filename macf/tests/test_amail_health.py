"""The mail broker's health is its last sweep, and stuck mail reaches a person (MIS-0004 R31, R32).

The sweep is the scheduled run of the inbound ``sweep`` verb, which ages the spool and the
pickup boxes against their declared bounds and exits non-zero on anything stuck
(``test_amail_inbound``'s orphan-sweep tests). The scheduler records how each run ended, so
the broker is judged from those records, and the outside watch alerts on that judgement.
"""
import json
import sys

import pytest
from pydantic import ValidationError

from macf.pd import interface as pdi
from macf.pd import watch
from macf.pd.health import START_GRACE_S, broker_health, schedule_health
from macf.pd.interface import CommandRun, Declaration, MissedRunPolicy, Schedule

CARD = "Broker@1a2b3c"
SWEEP = "mail-sweep"
H10 = 1792231200.0   # 2026-10-17T10:00:00Z, a firing of the hourly cron
ISO = "2026-10-17T10:00:00+00:00"


def _schedule(name=SWEEP):
    return Schedule(name=name, cron="0 * * * *", missed_run=MissedRunPolicy(kind="skip"),
                    target="isolated", run=CommandRun(command=["true"], wake_when="exit_code"),
                    timeout_s=60)


def _declaration(**extra):
    fields = {"version": 1, "agent": CARD, "timezone": "UTC", "schedules": [_schedule()],
              "mail_sweep_schedule": SWEEP}
    fields.update(extra)
    return Declaration.model_validate(fields)


def _run(kind, stamp, card=CARD, schedule=SWEEP, **data):
    return {"timestamp": stamp, "event": kind, "data": {"agent": card, "schedule": schedule, **data}}


SEEN = [_run("pd_schedule_seen", H10 - 1800, at="2026-10-17T09:30:00+00:00")]
STARTED = SEEN + [_run("pd_run_started", H10 + 1, scheduled_for=ISO)]


def _ended(outcome):
    return STARTED + [_run("pd_run_done", H10 + 3, scheduled_for=ISO, outcome=outcome)]


def _health(events, now):
    return broker_health(schedule_health(_declaration(), events, now)[0])


def test_health_is_last_sweep():
    """R31: a clean empty sweep is healthy; a failed or missing sweep is not.

    Healthy only when the last sweep that ended ended ok. A sweep in flight, or due and not yet
    late, leaves that verdict standing, so a broker between sweeps doesn't flap; an overdue
    sweep is unhealthy however the last one ended, and a sweep that never ended is no verdict.
    """
    # Missing: nothing declared, nothing ever run, or only a run that has not ended.
    assert not broker_health(None).healthy
    assert not _health([], H10).healthy
    assert not _health(SEEN, H10 - 60).healthy
    running = _health(STARTED, H10 + 30)
    assert not running.healthy and "no sweep has ended" in running.detail

    # A clean sweep that found nothing is healthy: an idle broker is not a failing one.
    clean = _health(_ended("ok: nothing to say"), H10 + 600)
    assert clean.healthy and clean.schedule == SWEEP

    # Every way a sweep ends other than ok is unhealthy.
    for outcome in ("failed: exit 1", "killed: past its 60 s limit", "stopped: the daemon stopped",
                    "abandoned: the daemon restarted while it ran", "not started: no such file"):
        assert not _health(_ended(outcome), H10 + 600).healthy, outcome

    # The next run in flight keeps the last ended run's verdict, either way.
    next_iso = "2026-10-17T11:00:00+00:00"
    in_flight = [_run("pd_run_started", H10 + 3601, scheduled_for=next_iso)]
    assert _health(_ended("ok: nothing to say") + in_flight, H10 + 3630).healthy
    assert not _health(_ended("failed: exit 1") + in_flight, H10 + 3630).healthy

    # Overdue: the 11:00 sweep never started, so the 10:00 one's ok no longer speaks.
    late = _health(_ended("ok: nothing to say"), H10 + 3600 + START_GRACE_S + 1)
    assert not late.healthy and "OVERDUE" in late.detail

    # Another agent's clean sweep is not this broker's.
    other = [_run(k["event"], k["timestamp"], card="Other@000000", **{
        f: v for f, v in k["data"].items() if f not in ("agent", "schedule")}) for k in _ended("ok: x")]
    assert not _health(other, H10 + 600).healthy


def test_a_sweep_that_is_not_declared_is_refused():
    """Naming a sweep that no schedule declares would read unhealthy forever, so it is refused."""
    with pytest.raises(ValidationError, match="mail_sweep_schedule names 'nightly'"):
        _declaration(mail_sweep_schedule="nightly")
    assert _declaration(mail_sweep_schedule=None).mail_sweep_schedule is None


# ---- through the outside watch ---------------------------------------------

def _home(root, *, sweep=True, unread=False):
    home = root / "Broker"
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Broker"}}))
    (home / ".maceff_primary_agent.id").write_text("1a2b3c4d-0000")
    # A rendered declaration names its agent by calling card, as the events do.
    declaration = {"version": 1, "agent": CARD, "timezone": "UTC",
                   "schedules": [json.loads(_schedule().model_dump_json())]}
    if sweep:
        declaration["mail_sweep_schedule"] = SWEEP
    if unread:
        declaration.update(unread_mail_threshold_s=600, notice_routes={pdi.UNREAD_MAIL_SOURCE: "operator"})
    pdi.declaration_path(home).write_text(json.dumps(declaration))
    return home


def _log(home, rows):
    with (home / ".maceff" / "agent_events_log.jsonl").open("a") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _pass(tmp_path, home, sink, now):
    command = [sys.executable, "-c", f"import sys; open({str(sink)!r}, 'a').write(sys.stdin.read())"]
    config = watch.render_config([home], command, tmp_path / "state")
    return watch.run_pass(config, now=now, base=tmp_path / "run", probe=None)


def _mail_findings(home, now):
    return [f for f in watch.check_home(home, now, probe=None) if f.subject in ("mail-broker", "mail")]


def test_stuck_mail_alerts(tmp_path):
    """R32: an unhealthy broker reaches a person through the outside watch, once per stretch.

    Mail stuck in a pickup box past its declared age fails the sweep (the sweep verb exits
    non-zero on any alert), so it reaches the watch as a failed sweep; so does a sweep that
    stopped running. An agent's mail unread past its declared age reaches the same watch by
    the daemon's own record of the spell. A clean sweep closes the stretch with one line.
    """
    home, sink = _home(tmp_path), tmp_path / "sink.txt"
    _log(home, _ended("failed: exit 1"))   # the sweep found mail past its pickup bound
    assert _pass(tmp_path, home, sink, H10 + 600) == watch.EXIT_UNHEALTHY
    text = sink.read_text()
    assert text.count("ALERT") == 1 and "Broker@1a2b3c mail-broker: SWEEP-FAILED" in text
    assert "failed: exit 1" in text
    _pass(tmp_path, home, sink, H10 + 720)                      # still failing: no second alert
    assert sink.read_text().count("ALERT") == 1

    next_iso = "2026-10-17T11:00:00+00:00"
    _log(home, [_run("pd_run_started", H10 + 3601, scheduled_for=next_iso),
                _run("pd_run_done", H10 + 3603, scheduled_for=next_iso, outcome="ok: nothing to say")])
    assert _pass(tmp_path, home, sink, H10 + 3700) == watch.EXIT_HEALTHY
    assert "recovered: Broker@1a2b3c mail-broker: ALIVE" in sink.read_text()

    # A broker that stops sweeping alerts as well, once its next sweep is overdue.
    stopped = _mail_findings(home, H10 + 2 * 3600 + START_GRACE_S + 1)
    assert [f.verdict for f in stopped] == ["SWEEP-FAILED"] and "OVERDUE" in stopped[0].detail

    # Mail unread past the agent's threshold is the same watch's other alert.
    reader = _home(tmp_path / "reader", sweep=False, unread=True)
    _log(reader, [{"timestamp": H10, "event": pdi.EVENT_UNREAD_MAIL,
                   "data": {"agent": CARD, "reason": "2 messages unread for 15 min"}}])
    assert [f.verdict for f in _mail_findings(reader, H10 + 60)] == ["UNREAD"]


def test_a_home_with_no_sweep_declared_gets_no_broker_finding(tmp_path):
    """Only a home that declares a sweep runs a broker the watch can judge; the rest say nothing."""
    home = _home(tmp_path, sweep=False)
    assert all(f.subject != "mail-broker" for f in watch.check_home(home, H10, probe=None))


def test_a_missing_or_unreadable_log_is_never_a_healthy_broker(tmp_path, monkeypatch):
    """No log is a missing sweep, and a log the watch cannot read is CHECK-FAILED, not ALIVE."""
    home = _home(tmp_path)
    assert [f.verdict for f in _mail_findings(home, H10)] == ["SWEEP-FAILED"]
    _log(home, _ended("ok: nothing to say"))

    def unreadable(*_args, **_kw):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(watch, "mail_sweep_events", unreadable)
    found = _mail_findings(home, H10 + 600)
    assert [f.verdict for f in found] == ["CHECK-FAILED"] and "cannot be read" in found[0].detail


def test_a_sweep_older_than_the_lookback_is_missing(tmp_path):
    """The watch reads back a bounded window; a last sweep older than that is no verdict."""
    home = _home(tmp_path)
    _log(home, _ended("ok: nothing to say"))
    now = H10 + watch.LOOKBACK_S + 3600
    events = watch.mail_sweep_events(home / ".maceff" / "agent_events_log.jsonl", CARD, SWEEP, now)
    assert events == []
    assert [f.verdict for f in _mail_findings(home, now)] == ["SWEEP-FAILED"]


def test_malformed_sweep_rows_cost_a_verdict_never_the_watch(tmp_path):
    """The check runs inside the watch's pass over every home, so a damaged row in one log
    must not raise: it is skipped, and the broker is judged by the rows that remain."""
    home = _home(tmp_path)
    garbage = [{"timestamp": "yesterday", "event": "pd_run_done", "data": {"agent": CARD, "schedule": SWEEP,
                                                                            "scheduled_for": 5, "outcome": 7}},
               {"timestamp": H10, "event": "pd_run_started", "data": "not a mapping"},
               {"timestamp": H10, "event": "pd_run_done", "data": {"agent": CARD, "schedule": ["x"]}},
               ["not", "an", "event"]]
    _log(home, garbage)
    with (home / ".maceff" / "agent_events_log.jsonl").open("a") as fh:
        fh.write("not json at all\n")
    assert [f.verdict for f in _mail_findings(home, H10 + 600)] == ["SWEEP-FAILED"]
    _log(home, _ended("ok: nothing to say"))
    assert [f.verdict for f in _mail_findings(home, H10 + 600)] == ["ALIVE"]
