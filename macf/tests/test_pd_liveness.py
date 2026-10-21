"""A unit's own liveness (MIS-0002-R14): the helper a unit uses to write ``pd_unit_alive``."""
import json
import os
import sys
import time

from macf.pd import liveness as lv
from macf.pd.interface import EVENT_LIVENESS, Liveness
from test_primal_daemon import (CARD, MACF_SRC, ME, base, make_home, run_daemon,  # noqa: F401 - fixtures
                                unit_pid, unit_state, wait_for)


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
    deadline = time.monotonic() + 1.0   # generous under a loaded suite; returns at the third beat
    while len(events) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    hb.stop()
    halt.set()
    n = len(events)
    assert n >= 3, f"{n} events within 1 s at a 0.05 s interval"
    time.sleep(0.12)
    assert len(events) <= n + 1, "the heartbeat kept writing after stop"


#: A unit as the mail broker and inbound watcher are wired: its work loop ticks the heartbeat
#: it gets from its environment, and nothing in it names the unit, the interval or the log.
MANAGED_UNIT = r'''
import time
from macf.pd.liveness import heartbeat_from_env

beat = heartbeat_from_env()
while True:
    if beat is not None:
        beat.tick()
    time.sleep(0.02)
'''


def test_a_managed_unit_writes_its_liveness_to_its_agents_log_at_its_declared_interval(
        tmp_path, base, run_daemon):
    """R14 where it lives: a unit the daemon starts, declared with no liveness settings of its
    own, writes ``pd_unit_alive`` into its agent's event log, the one in the agent home, naming
    the process the daemon started, at the interval its declaration gives. The daemon credits
    it, so the unit reads running."""
    from macf.agent_events_log import set_log_path
    from macf.pd.interface import Unit
    script = tmp_path / "managed_unit.py"
    script.write_text(MANAGED_UNIT)
    interval = 0.25
    unit = Unit(name="worker", command=[sys.executable, str(script)], account=ME, restart="on-failure",
                liveness_interval_s=interval, memory_limit_mb=256, environment={"PYTHONPATH": MACF_SRC},
                stop_grace_s=1.0)
    home = make_home(tmp_path, [unit])
    agent_log = home / ".maceff" / "agent_events_log.jsonl"
    set_log_path(agent_log)       # the daemon reads the agent's log, as it does outside a test

    def beats():
        rows = [json.loads(line) for line in agent_log.read_text().splitlines()] if agent_log.exists() else []
        return [r for r in rows if r.get("event") == EVENT_LIVENESS and r["data"].get("unit") == "worker"]

    daemon = run_daemon(home, base)
    assert wait_for(lambda: len(beats()) >= 5, timeout=15), f"{len(beats())} beats in the agent's log"
    found = beats()
    pid = unit_pid(daemon, "worker")
    assert unit_state(daemon, "worker") == "running"
    for row in found:
        live = Liveness.model_validate(row["data"])
        assert (live.agent, live.unit, live.pid, live.interval_s) == (CARD, "worker", pid, interval)
    gaps = sorted(b["timestamp"] - a["timestamp"] for a, b in zip(found, found[1:]))
    assert gaps[0] >= 0.8 * interval, f"beats closer than the declared {interval} s: {gaps}"
    assert gaps[len(gaps) // 2] <= 2 * interval, f"beats further apart than the declared {interval} s: {gaps}"


def test_a_loop_that_stops_passing_stops_the_events_within_one_interval(capsys):
    """The beat means the work is running: a wedged loop must go quiet, so its daemon sees
    the unit overdue, even though the heartbeat's own thread is still alive."""
    events, append = recorder()
    hb = lv.Heartbeat("Resident@1a2b3c", "u", 0.05, append=append).start()
    halt = _ticking(hb)
    deadline = time.monotonic() + 1.0   # generous under a loaded suite; returns at the first beat
    while not events and time.monotonic() < deadline:
        time.sleep(0.01)
    assert events, "a ticking loop wrote nothing"
    halt.set()                      # the loop wedges; the heartbeat thread runs on
    time.sleep(0.15)                # at most one beat already due may still land, even if late
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
    deadline = time.monotonic() + 1.0   # generous under a loaded suite; returns at the beat
    while not events and time.monotonic() < deadline:
        time.sleep(0.005)
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

def test_the_broker_server_calls_its_pass_hook_while_idle():
    """socketserver passes service_actions on every turn of the accept loop, idle or not, so
    the broker's heartbeat ticks while the loop runs and stops when it stops."""
    import shutil
    import tempfile
    import threading
    from macf.amail.broker import _Handler, _Server
    # A short directory: pytest's tmp_path on macOS passes the 103-byte AF_UNIX limit.
    sockdir = tempfile.mkdtemp(prefix="pd-", dir="/tmp")
    try:
        server = _Server(os.path.join(sockdir, "s.sock"), _Handler)
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
    finally:
        shutil.rmtree(sockdir, ignore_errors=True)


def test_the_beat_carries_a_failed_login_while_it_lasts():
    """MIS-0002-R19 (auth_failure_MUST_read_failed): each beat asks whether the harness can
    authenticate, so the daemon hears a failed login on the next beat and its end the same way."""
    events, append = recorder()
    said = ["Login expired"]
    hb = lv.Heartbeat("Resident@1a2b3c", "session", 0.05, append=append,
                      auth_failed=lambda: said[0]).start()
    halt = _ticking(hb)
    deadline = time.monotonic() + 1.0
    while len(events) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    said[0] = None
    n = len(events)
    while len(events) < n + 2 and time.monotonic() < deadline + 1.0:
        time.sleep(0.01)
    hb.stop()
    halt.set()
    data = [d for _, d in events]
    assert data[0]["auth_failed"] == "Login expired"
    assert data[-1].get("auth_failed") is None                       # left out once it ends


def test_a_beat_leaves_out_what_is_unset():
    """A beat with nothing to say about a wait or a login carries neither key, so a daemon that
    predates either field, and refuses unknown keys, still credits it."""
    events, append = recorder()
    lv.emit("Resident@1a2b3c", "session", 10.0, append=append, pid=os.getpid())
    (_, data), = events
    assert "auth_failed" not in data and "waiting_on" not in data and "in_flight" not in data
    assert lv.Liveness.model_validate(data).auth_failed is None


def test_a_change_in_what_the_unit_waits_on_beats_at_once(monkeypatch):
    """MIS-0002-R21 between beats: a dialog that opens, and one that closes, reach the daemon
    within seconds, not a whole interval later. A 60 s interval stood two minutes late in both
    directions on a host before this (#728)."""
    monkeypatch.setattr(lv, "CHANGE_CHECK_S", 0.02)
    events, append = recorder()
    asked = {"now": None}
    hb = lv.Heartbeat("Resident@1a2b3c", "session", 60.0, append=append,
                      waiting_on=lambda: asked["now"]).start()
    halt = _ticking(hb)

    def beats_saying(value, n, within=1.0):
        deadline = time.monotonic() + within
        while time.monotonic() < deadline:
            said = [d.get("waiting_on") for _, d in events]
            if len(said) >= n and said[n - 1] == value:
                return True
            time.sleep(0.01)
        return False
    try:
        assert beats_saying(None, 1)                    # the first beat, at once
        asked["now"] = "a permission dialog for Bash, open since 21:08"
        assert beats_saying(asked["now"], 2)            # opened: beat now, not in 60 s
        asked["now"] = None
        assert beats_saying(None, 3)                    # answered: beat now too
        time.sleep(0.1)
        assert len(events) == 3                         # and nothing more while nothing changes
    finally:
        hb.stop()
        halt.set()


def test_a_wedged_loop_never_beats_early_on_a_change(monkeypatch):
    """Only a loop that has passed since the last beat may beat early (R14, R18): a session
    whose loop has wedged and which then shows a dialog, or loses its login, must stay
    silent, so its daemon fails it for silence rather than reading it alive."""
    monkeypatch.setattr(lv, "CHANGE_CHECK_S", 0.02)
    events, append = recorder()
    asked = {"now": None}
    hb = lv.Heartbeat("Resident@1a2b3c", "session", 60.0, append=append,
                      waiting_on=lambda: asked["now"]).start()
    try:
        hb.tick()                                       # the loop passes once, then wedges
        deadline = time.monotonic() + 1.0
        while not events and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(events) == 1
        asked["now"] = "a permission dialog for Bash, open since 21:34"
        time.sleep(0.2)                                 # ten change checks, and no pass
        assert len(events) == 1
    finally:
        hb.stop()
