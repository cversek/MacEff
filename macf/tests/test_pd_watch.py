"""The outside watch (MIS-0002-R74 (pd_MUST_have_outside_watch), R75).

Each test is one of the demonstrations ``service_supervision`` section 6 asks for: stop
the subject and see one alert, bring it back and see one recovery; corrupt, remove and
backdate a heartbeat for three verdicts, none ALIVE; each external state its own code.
"""
import json
import sys
import time

import pytest

from macf.pd import interface as pdi
from macf.pd import watch

NOW = 1_800_000_000.0
CARD = "Resident@1a2b3c"


def _home(root, name="Resident", uuid="1a2b3c4d-0000", units=(("broker", 15.0),)):
    home = root / name
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": name}}))
    (home / ".maceff_primary_agent.id").write_text(uuid)
    declaration = {"version": 1, "agent": name, "units": [
        {"name": unit, "command": ["true"], "account": "resident", "restart": "always",
         "liveness_interval_s": interval, "memory_limit_mb": 64} for unit, interval in units]}
    pdi.declaration_path(home).write_text(json.dumps(declaration))
    return home


def _stamp(home, unit, age_s, interval_s=15.0, pid=4242, start="777"):
    log = home / ".maceff" / "agent_events_log.jsonl"
    data = {"agent": CARD, "unit": unit, "pid": pid, "proc_start": start, "interval_s": interval_s}
    with log.open("a") as fh:
        fh.write(json.dumps({"timestamp": NOW - age_s, "event": pdi.EVENT_LIVENESS, "data": data}) + "\n")


def _record(base, pid=5151, start="888"):
    base.mkdir(exist_ok=True)
    pdi.record_path(CARD, base).write_text(pdi.DaemonRecord(pid=pid, proc_start=start).model_dump_json())


def _probe(starts):
    return lambda pid: starts.get(pid)


ALL_RUNNING = _probe({5151: "888", 4242: "777"})


def _config(tmp_path, homes, sink):
    command = [sys.executable, "-c", f"import sys; open({str(sink)!r}, 'a').write(sys.stdin.read())"]
    return watch.render_config(homes, command, tmp_path / "state")


def test_a_stopped_daemon_alerts_once_then_recovers_once(tmp_path):
    home, base, sink = _home(tmp_path), tmp_path / "run", tmp_path / "sink.txt"
    _stamp(home, "broker", age_s=5, interval_s=600.0)  # the unit stays fresh; only the daemon varies
    config = _config(tmp_path, [home], sink)

    # Stopped: no record. One alert, through the configured command and nothing else.
    assert watch.run_pass(config, now=NOW, base=base, probe=ALL_RUNNING) == watch.EXIT_UNHEALTHY
    assert sink.read_text().count("ALERT") == 1
    assert "Resident@1a2b3c daemon: ABSENT" in sink.read_text()
    # Still stopped on the next pass: the stretch is open, nothing more is sent.
    watch.run_pass(config, now=NOW + 120, base=base, probe=ALL_RUNNING)
    assert sink.read_text().count("ALERT") == 1
    # Started again: one recovery line naming the stretch's length.
    _record(base)
    assert watch.run_pass(config, now=NOW + 240, base=base, probe=ALL_RUNNING) == watch.EXIT_HEALTHY
    assert "recovered: Resident@1a2b3c daemon: ALIVE" in sink.read_text()
    assert "(after 4 min)" in sink.read_text()


def test_a_declared_daemon_without_a_watch_is_named(tmp_path):
    declared, other = _home(tmp_path), _home(tmp_path, name="Second", uuid="9f8e7d6c-0000")
    bare = tmp_path / "NoDeclaration"
    bare.mkdir()
    config = watch.render_config([declared, other, bare], ["true"], tmp_path / "state")
    assert [h.path for h in config.homes] == [str(declared), str(other)]
    assert watch.unwatched(config, [declared, other, bare]) == []
    config.homes.pop()  # a hand edit, or a home added after rendering
    assert watch.unwatched(config, [declared, other, bare]) == [str(other)]


def test_corrupt_removed_and_backdated_heartbeats_are_three_verdicts_none_alive(tmp_path):
    home = _home(tmp_path, units=(("fresh", 15.0), ("old", 15.0), ("never", 15.0), ("broken", 15.0)))
    _stamp(home, "fresh", age_s=10)
    _stamp(home, "old", age_s=600)
    log = home / ".maceff" / "agent_events_log.jsonl"
    with log.open("a") as fh:
        fh.write(json.dumps({"timestamp": NOW - 1, "event": pdi.EVENT_LIVENESS,
                             "data": {"unit": "broken", "pid": "not a pid"}}) + "\n")
    _record(tmp_path / "run")
    verdicts = {f.subject: f.verdict for f in watch.check_home(home, NOW, tmp_path / "run", ALL_RUNNING)}
    assert verdicts == {"daemon": "ALIVE", "fresh": "ALIVE", "old": "STALE",
                        "never": "ABSENT", "broken": "UNREADABLE"}


def test_the_bound_is_the_units_own_published_interval(tmp_path):
    home = _home(tmp_path, units=(("fast", 15.0), ("slow", 15.0)))
    _stamp(home, "fast", age_s=100, interval_s=10.0)
    _stamp(home, "slow", age_s=100, interval_s=600.0)  # not the declaration's 15
    _record(tmp_path / "run")
    verdicts = {f.subject: f.verdict for f in watch.check_home(home, NOW, tmp_path / "run", ALL_RUNNING)}
    assert (verdicts["fast"], verdicts["slow"]) == ("STALE", "ALIVE")


def test_a_fresh_stamp_from_a_process_that_is_gone_is_not_alive(tmp_path):
    home = _home(tmp_path)
    _stamp(home, "broker", age_s=5)
    _record(tmp_path / "run")
    restarted = _probe({5151: "888", 4242: "999"})  # the pid now names another process
    unit = watch.check_home(home, NOW, tmp_path / "run", restarted)[1]
    assert (unit.verdict, unit.subject) == ("GONE", "broker")
    daemon = watch.check_home(home, NOW, tmp_path / "run", _probe({}))[0]
    assert daemon.verdict == "GONE"


def test_each_external_state_has_its_own_exit_code(tmp_path):
    missing = tmp_path / "gone"
    assert watch.exit_code(watch.check_home(missing, NOW)) == watch.EXIT_UNREACHABLE
    broken = _home(tmp_path)
    pdi.declaration_path(broken).write_text('{"version": 1, "agent": "x", "surprise": true}')
    findings = watch.check_home(broken, NOW)
    assert [f.verdict for f in findings] == ["CHECK-FAILED"]
    assert watch.exit_code(findings) == watch.EXIT_CHECK_FAILED
    assert len({watch.EXIT_HEALTHY, watch.EXIT_UNHEALTHY, watch.EXIT_UNREACHABLE, watch.EXIT_CHECK_FAILED}) == 4


def test_a_failed_push_is_recorded_and_loud_and_echoes_nothing_from_the_command(tmp_path, capsys):
    durable = tmp_path / "state" / "alerts.jsonl"
    secret_url = "https://api.example/bot123:SECRET/send"
    command = [sys.executable, "-c", f"import sys; print({secret_url!r}); sys.exit(4)"]
    assert watch.send(command, "ALERT: x daemon: ABSENT\n", durable) is False
    record = json.loads(durable.read_text())
    assert (record["outcome"], record["text"]) == ("alert command exited 4", "ALERT: x daemon: ABSENT\n")
    err = capsys.readouterr().err
    assert "ALERT: x daemon: ABSENT" in err
    assert "SECRET" not in err and "SECRET" not in durable.read_text()


def test_an_unprobed_home_gets_no_guessed_daemon_verdict(tmp_path):
    home = _home(tmp_path)
    _stamp(home, "broker", age_s=5)
    findings = watch.check_home(home, NOW, tmp_path / "run", probe=None)
    assert [(f.subject, f.verdict) for f in findings] == [("broker", "ALIVE")]


def test_a_subject_no_longer_checked_closes_its_stretch(tmp_path):
    lines, after = watch.transitions([], {"Resident@1a2b3c/broker": {"since": NOW - 300, "verdict": "STALE"}}, NOW)
    assert lines == ["closed: Resident@1a2b3c/broker is no longer checked (was STALE for 5 min)"]
    assert after == {}


def test_a_stamp_older_than_the_lookback_reads_absent_and_says_so(tmp_path):
    home = _home(tmp_path)
    _stamp(home, "broker", age_s=watch.LOOKBACK_S + 60)
    _record(tmp_path / "run")
    unit = watch.check_home(home, NOW, tmp_path / "run", ALL_RUNNING)[1]
    assert unit.verdict == "ABSENT"
    assert "within 168 h" in unit.detail


def test_the_rendered_units_run_the_watch_on_its_own_timer(tmp_path):
    units = watch.render_systemd(tmp_path / "watch.json", every_s=90, python="/usr/bin/python3")
    service, timer = units["maceff_pd_watch.service"], units["maceff_pd_watch.timer"]
    assert f"ExecStart=/usr/bin/python3 -m macf.pd.watch --config {tmp_path / 'watch.json'}" in service
    assert "SuccessExitStatus=1 2" in service
    assert "OnUnitActiveSec=90" in timer


def test_the_watch_breaking_is_itself_an_alert(tmp_path, monkeypatch):
    sink = tmp_path / "sink.txt"
    home = _home(tmp_path)
    config = _config(tmp_path, [home], sink)
    path = tmp_path / "watch.json"
    path.write_text(config.model_dump_json())

    def broken(*a, **k):
        raise RuntimeError("instrument fault")
    monkeypatch.setattr(watch, "run_pass", broken)
    assert watch.main(["--config", str(path)]) == watch.EXIT_CHECK_FAILED
    assert "the watch itself: CHECK-FAILED, RuntimeError: instrument fault" in sink.read_text()
