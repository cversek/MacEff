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


def test_the_heartbeat_reports_at_once_and_then_at_its_interval():
    events, append = recorder()
    hb = lv.Heartbeat("Resident@1a2b3c", "u", 0.05, append=append).start()
    time.sleep(0.18)
    hb.stop()
    n = len(events)
    assert n >= 3, f"{n} events in 0.18 s at a 0.05 s interval"
    time.sleep(0.12)
    assert len(events) <= n + 1, "the heartbeat kept writing after stop"


def test_in_flight_is_reported_when_the_unit_gives_it():
    events, append = recorder()
    lv.Heartbeat("C@1a2b3c", "u", 10.0, in_flight=lambda: 3, append=append).start()
    time.sleep(0.05)
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
