"""A unit's own liveness (MIS-0002-R14): the helper a unit uses to write ``pd_unit_alive``."""
import json
import os
import time

from macf.pd import liveness as lv
from macf.pd.interface import EVENT_LIVENESS, Liveness


def _home(tmp_path, name="Resident", uuid="1a2b3c4d-0000"):
    (tmp_path / ".maceff").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": name}}))
    (tmp_path / ".maceff_primary_agent.id").write_text(uuid + "\n")
    return tmp_path


def recorder():
    events = []
    return events, lambda name, data: events.append((name, data)) or True


def test_an_event_names_this_process_by_pid_and_start_time():
    events, append = recorder()
    assert lv.emit("Resident@1a2b3c", "amail-broker", 60.0, append=append)
    name, data = events[0]
    assert name == EVENT_LIVENESS
    live = Liveness.model_validate(data)
    assert (live.agent, live.unit, live.pid, live.interval_s) == ("Resident@1a2b3c", "amail-broker", os.getpid(), 60.0)
    assert live.proc_start and live.proc_start != "unknown"


def _ticking(hb, period=0.01):
    """A work loop that ticks *hb* every *period* until the returned event is set."""
    import threading
    halt = threading.Event()

    def loop():
        while not halt.wait(period):
            hb.tick()
    threading.Thread(target=loop, daemon=True).start()
    return halt


def test_the_heartbeat_reports_at_once_and_then_at_its_interval():
    events, append = recorder()
    hb = lv.Heartbeat("Resident@1a2b3c", "u", 0.05, append=append).start()
    halt = _ticking(hb)
    time.sleep(0.18)
    hb.stop()
    halt.set()
    n = len(events)
    assert n >= 3, f"{n} events in 0.18 s at a 0.05 s interval"
    time.sleep(0.12)
    assert len(events) <= n + 1, "the heartbeat kept writing after stop"


def test_a_loop_that_stops_passing_stops_the_events_within_one_interval(capsys):
    """The beat means the work is running: a wedged loop must go quiet, so its daemon sees
    the unit overdue, even though the heartbeat's own thread is still alive."""
    events, append = recorder()
    hb = lv.Heartbeat("Resident@1a2b3c", "u", 0.05, append=append).start()
    halt = _ticking(hb)
    time.sleep(0.15)
    assert events, "a ticking loop wrote nothing"
    halt.set()                      # the loop wedges; the heartbeat thread runs on
    time.sleep(0.06)                # at most one beat already due may still land
    n = len(events)
    time.sleep(0.25)
    try:
        assert len(events) == n, f"{len(events) - n} beats from a loop that stopped passing"
        assert "has not passed" in capsys.readouterr().err
    finally:
        hb.stop()


def test_nothing_is_written_before_the_loop_first_passes():
    events, append = recorder()
    hb = lv.Heartbeat("Resident@1a2b3c", "u", 0.05, append=append).start()
    time.sleep(0.12)
    assert events == []
    hb.tick()
    time.sleep(0.03)
    hb.stop()
    assert len(events) == 1, "the first tick should beat at once"


def test_in_flight_is_reported_when_the_unit_gives_it():
    events, append = recorder()
    hb = lv.Heartbeat("C@1a2b3c", "u", 10.0, in_flight=lambda: 3, append=append).start()
    hb.tick()
    time.sleep(0.05)
    hb.stop()
    assert events[0][1]["in_flight"] == 3


def test_outside_a_daemon_nothing_is_written(tmp_path):
    assert lv.heartbeat_from_env(environ={"MACEFF_AGENT_HOME_DIR": str(_home(tmp_path))}) is None


def test_a_unit_named_with_its_interval_starts_a_heartbeat_with_the_home_card(tmp_path):
    events, append = recorder()
    hb = lv.heartbeat_from_env(environ={"MACF_PD_UNIT": "amail-broker", "MACF_PD_LIVENESS_S": "30",
                                        "MACEFF_AGENT_HOME_DIR": str(_home(tmp_path))}, append=append)
    try:
        assert hb is not None and hb.unit == "amail-broker" and hb.interval_s == 30.0
        assert hb.card.startswith("Resident@")
        hb.tick()
        time.sleep(0.05)
        assert events and events[0][1]["agent"] == hb.card
    finally:
        hb.stop()


def test_a_partial_or_malformed_setting_starts_nothing_and_says_why(tmp_path, capsys):
    home = str(_home(tmp_path))
    for env in ({"MACF_PD_UNIT": "u", "MACEFF_AGENT_HOME_DIR": home},
                {"MACF_PD_LIVENESS_S": "30", "MACEFF_AGENT_HOME_DIR": home},
                {"MACF_PD_UNIT": "u", "MACF_PD_LIVENESS_S": "soon", "MACEFF_AGENT_HOME_DIR": home},
                {"MACF_PD_UNIT": "u", "MACF_PD_LIVENESS_S": "-1", "MACEFF_AGENT_HOME_DIR": home},
                {"MACF_PD_UNIT": "u", "MACF_PD_LIVENESS_S": "30"}):
        assert lv.heartbeat_from_env(environ=env) is None
    assert capsys.readouterr().err.count("no liveness from this unit") == 5


def test_a_home_that_names_no_agent_starts_nothing(tmp_path, capsys):
    assert lv.heartbeat_from_env(environ={"MACF_PD_UNIT": "u", "MACF_PD_LIVENESS_S": "30",
                                          "MACEFF_AGENT_HOME_DIR": str(tmp_path)}) is None
    assert "no liveness from this unit" in capsys.readouterr().err


# --- `macf_tools pd alive`, for units that are not Python (a shell loop calls it each pass) -------

def _alive(monkeypatch, env, in_flight=None):
    from argparse import Namespace
    from macf.pd import cli
    for k in ("MACF_PD_UNIT", "MACF_PD_LIVENESS_S", "MACEFF_AGENT_HOME_DIR"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    events, append = recorder()
    monkeypatch.setattr(lv, "append_event", append)
    return cli.cmd_pd_alive(Namespace(in_flight=in_flight, pid=None)), events


def test_pd_alive_outside_a_daemon_does_nothing_and_succeeds(monkeypatch, tmp_path):
    rc, events = _alive(monkeypatch, {"MACEFF_AGENT_HOME_DIR": str(_home(tmp_path))})
    assert (rc, events) == (0, [])


def test_pd_alive_as_a_declared_unit_writes_one_event(monkeypatch, tmp_path):
    rc, events = _alive(monkeypatch, {"MACF_PD_UNIT": "mail-clock", "MACF_PD_LIVENESS_S": "60",
                                      "MACEFF_AGENT_HOME_DIR": str(_home(tmp_path))}, in_flight=2)
    assert rc == 0 and len(events) == 1
    data = events[0][1]
    assert (data["unit"], data["interval_s"], data["in_flight"]) == ("mail-clock", 60.0, 2)
    # the unit is the loop that runs the command, so the event names the parent, not the CLI
    assert data["pid"] == os.getppid()


def test_pd_alive_with_a_malformed_setting_fails(monkeypatch, tmp_path):
    rc, events = _alive(monkeypatch, {"MACF_PD_UNIT": "mail-clock", "MACF_PD_LIVENESS_S": "often",
                                      "MACEFF_AGENT_HOME_DIR": str(_home(tmp_path))})
    assert (rc, events) == (1, [])


# --- the mail broker ticks from its accept loop -------------------------------------------------

def test_the_broker_server_calls_its_pass_hook_while_idle(tmp_path):
    """socketserver passes service_actions on every turn of the accept loop, idle or not, so
    the broker's heartbeat ticks while the loop runs and stops when it stops."""
    import threading
    from macf.amail.broker import _Handler, _Server
    server = _Server(str(tmp_path / "s.sock"), _Handler)
    passes = []
    server.on_pass = lambda: passes.append(1)
    t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    try:
        time.sleep(0.2)
        assert len(passes) >= 3, f"{len(passes)} passes in 0.2 s at a 0.02 s poll"
        assert server.in_flight() == 0
    finally:
        server.shutdown()
        server.server_close()
    n = len(passes)
    time.sleep(0.1)
    assert len(passes) == n, "the hook ran after the loop stopped"
