"""The primal daemon's interface (MIS-0002 step 1, proposed): names, declaration, events, sockets.

Each test names the requirement it holds the interface to. The daemon itself is not
here; these pin the contracts the daemon and every later step build against.
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from macf.pd import interface as pdi

CARD = "TheHarborMaster@ee5cd8"
EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "developer" / "examples" / "pd_declaration.json"


def _unit(**over):
    unit = {"name": "broker", "command": ["python3", "-m", "x"], "account": "a",
            "restart": "always", "liveness_interval_s": 60, "memory_limit_mb": 256}
    unit.update(over)
    return unit


def _declaration(**over):
    decl = {"version": 1, "agent": CARD, "units": [_unit()]}
    decl.update(over)
    return decl


# ---- names and paths --------------------------------------------------------

def test_every_name_carries_the_identifier_and_the_agent(tmp_path):
    """R06: maceff_pd in every name; the agent too, since agents can share a login."""
    names = [pdi.systemd_unit(CARD), pdi.launchd_label(CARD),
             pdi.control_socket(CARD, tmp_path).name, pdi.channel_socket(CARD, tmp_path).name,
             pdi.record_path(CARD, tmp_path).name]
    assert all("TheHarborMaster_ee5cd8" in n for n in names), names
    assert pdi.PD_IDENTIFIER in pdi.systemd_unit(CARD) and pdi.PD_IDENTIFIER in pdi.launchd_label(CARD)


def test_no_name_uses_a_character_systemd_or_tmux_reinterprets():
    """'@' reads as a systemd template instance; tmux silently rewrites '.' and ':'."""
    unit = pdi.systemd_unit(CARD)
    assert "@" not in unit and ":" not in unit
    assert unit == "maceff_pd-TheHarborMaster_ee5cd8.service"


def test_a_socket_path_too_long_for_the_kernel_is_refused_with_the_reason(tmp_path):
    """R129: refused before bind, naming the limit, not a bare kernel error."""
    with pytest.raises(OSError, match="longer than"):
        pdi.check_socket_path(tmp_path / ("d" * 200) / "x.control.sock")
    pdi.check_socket_path(Path("/run/user/1000/maceff_pd") / "TheHarborMaster_ee5cd8.control.sock")


def test_the_declaration_lives_in_the_agent_home_not_the_outer_tier(tmp_path):
    """R04: the outer tier holds no agent's declaration."""
    assert pdi.declaration_path(tmp_path) == tmp_path / ".maceff" / "pd" / "declaration.json"


# ---- the declaration --------------------------------------------------------

def test_the_documented_example_is_a_valid_declaration():
    """The developer doc's example is checked, so the doc cannot drift from the format."""
    decl = pdi.Declaration.model_validate(json.loads(EXAMPLE.read_text()))
    assert [u.name for u in decl.units][:2] == ["session", "transcript-monitor"]


@pytest.mark.parametrize("field", ["command", "account", "restart", "liveness_interval_s", "memory_limit_mb"])
def test_a_unit_missing_a_required_field_is_refused(field):
    """R09 (command, account, restart policy, liveness interval) and R59 (memory limit)."""
    unit = _unit()
    del unit[field]
    with pytest.raises(ValidationError):
        pdi.Declaration.model_validate(_declaration(units=[unit]))


def test_an_unknown_key_is_refused_not_ignored():
    """A key the daemon ignores is a setting the author believes is in force."""
    with pytest.raises(ValidationError):
        pdi.Declaration.model_validate(_declaration(units=[_unit(restart_delay=5)]))


def test_a_name_declared_twice_is_refused():
    with pytest.raises(ValidationError, match="more than once"):
        pdi.Declaration.model_validate(_declaration(units=[_unit(), _unit()]))


def test_a_schedule_without_a_missed_run_policy_is_refused():
    """R109: no default missed-run policy."""
    schedule = {"name": "s", "cron": "0 7 * * *", "target": "isolated",
                "run": {"prompt_file": "p.md"}, "timeout_s": 60}
    with pytest.raises(ValidationError):
        pdi.Declaration.model_validate(_declaration(schedules=[schedule]))


def test_a_window_is_given_exactly_for_a_windowed_policy():
    """R25: run once inside a declared window needs the window, and only it does."""
    with pytest.raises(ValidationError):
        pdi.MissedRunPolicy.model_validate({"kind": "run_once_in_window"})
    with pytest.raises(ValidationError):
        pdi.MissedRunPolicy.model_validate({"kind": "skip", "window": {"start": "06:00", "end": "07:00"}})


# ---- the events -------------------------------------------------------------

def test_a_liveness_event_names_the_process_by_pid_and_start_time():
    """R14, R15: the readout confirms the writer by pid and start time before calling it alive."""
    with pytest.raises(ValidationError):
        pdi.Liveness.model_validate({"agent": CARD, "unit": "broker", "pid": 4242, "interval_s": 60})
    pdi.Liveness.model_validate({"agent": CARD, "unit": "broker", "pid": 4242,
                                 "proc_start": "123456", "interval_s": 60})


def test_unit_states_are_exactly_the_listed_six():
    """R20."""
    assert pdi.UNIT_STATES == ("declared", "starting", "running", "waiting_on_a_person", "failed", "stopped")
    with pytest.raises(ValidationError):
        pdi.UnitState.model_validate({"agent": CARD, "unit": "broker", "state": "hung"})


def test_a_control_event_names_who_asked_and_why():
    """R52."""
    with pytest.raises(ValidationError):
        pdi.Control.model_validate({"agent": CARD, "act": "restart", "unit": "broker",
                                    "asked_by": {"kind": "operator"}, "reason": ""})


# ---- the sockets ------------------------------------------------------------

def test_a_status_request_parses():
    assert isinstance(pdi.parse_request('{"op": "status"}'), pdi.StatusRequest)


def test_an_unknown_operation_or_field_is_refused_whole():
    for line in ('{"op": "delete_all"}', '{"op": "status", "verbose": true}'):
        with pytest.raises(ValidationError):
            pdi.parse_request(line)


def test_a_compaction_may_be_asked_only_by_the_operator_or_the_wind_down():
    """R108."""
    for kind in ("operator", "wind_down"):
        pdi.parse_request(json.dumps({"op": "compact", "asked_by": {"kind": kind}, "reason": "cl 9"}))
    with pytest.raises(ValidationError, match="wind-down"):
        pdi.parse_request(json.dumps({"op": "compact", "asked_by": {"kind": "policy"}, "reason": "cl 9"}))


# ---- the revision: identity, runtime directory, placeholders, grants ------------

def _home(tmp_path, name="Resident", uuid="1a2b3c4d-0000"):
    (tmp_path / ".maceff").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": name}}))
    (tmp_path / ".maceff_primary_agent.id").write_text(uuid + "\n")
    return tmp_path


def test_the_card_comes_from_the_named_home_and_never_the_environment(tmp_path, monkeypatch):
    """R02: a daemon started by the outer tier has no MACEFF_AGENT_NAME; a session may.
    Both must name the same sockets, so the environment is never read."""
    monkeypatch.setenv("MACEFF_AGENT_NAME", "SomeoneElse")
    assert pdi.agent_card(_home(tmp_path)) == "Resident@1a2b3c"


def test_a_home_that_names_no_agent_is_refused(tmp_path):
    with pytest.raises(pdi.IdentityError):
        pdi.agent_card(tmp_path)


def test_the_runtime_directory_is_made_private(tmp_path):
    made = pdi.ensure_runtime_dir(tmp_path / "maceff_pd")
    assert made.stat().st_mode & 0o777 == 0o700


def test_a_runtime_directory_open_to_others_is_refused(tmp_path):
    """Without XDG_RUNTIME_DIR it is in /tmp, where anyone could have made it first."""
    d = tmp_path / "maceff_pd"
    d.mkdir(mode=0o755)
    d.chmod(0o755)
    with pytest.raises(OSError, match="open to its group or others"):
        pdi.ensure_runtime_dir(d)


def test_an_unknown_placeholder_is_refused_and_a_known_one_rendered():
    """R13: the daemon fills in a closed set; a path that differs by host is never declared."""
    with pytest.raises(ValidationError, match="unknown placeholder"):
        pdi.Unit.model_validate(_unit(environment={"HOME_DIR": "{home}"}))
    unit = pdi.Unit.model_validate(_unit(command=["tool", "--home", "{agent_home}"]))
    assert pdi.render(unit.command[2], {"agent_home": "/h/a"}) == "/h/a"


def test_a_misspelled_privacy_grant_is_refused():
    """R63: a misspelling fails when the declaration is read, not as a missing grant later."""
    with pytest.raises(ValidationError, match="unknown privacy grant"):
        pdi.Unit.model_validate(_unit(privacy_grants=["full_disk"]))
    pdi.Unit.model_validate(_unit(privacy_grants=["keychain", "automation:com.apple.Terminal"]))


def test_at_most_one_unit_is_the_session():
    with pytest.raises(ValidationError, match="at most one"):
        pdi.Declaration.model_validate(_declaration(units=[_unit(name="a", kind="session"),
                                                           _unit(name="b", kind="session")]))


def test_a_requested_act_records_its_peer_and_only_such_an_act_does():
    """R52: the claimed asker beside what the kernel proved; the policy has no peer."""
    peer = {"uid": 1000, "pid": 4242, "proc_start": "123"}
    base = {"agent": CARD, "act": "stop", "unit": "broker", "reason": "asked"}
    with pytest.raises(ValidationError):
        pdi.Control.model_validate({**base, "asked_by": {"kind": "operator"}})
    with pytest.raises(ValidationError):
        pdi.Control.model_validate({**base, "asked_by": {"kind": "policy"}, "peer": peer})
    pdi.Control.model_validate({**base, "asked_by": {"kind": "operator"}, "peer": peer})


def test_liveness_can_report_work_in_flight_and_a_wait_on_a_person():
    """R49 and R21: the unit says what the daemon must not cut short or restart for."""
    live = {"agent": CARD, "unit": "session", "pid": 4242, "proc_start": "1", "interval_s": 60}
    pdi.Liveness.model_validate({**live, "in_flight": 2, "waiting_on": "a permission prompt"})
    with pytest.raises(ValidationError):
        pdi.Liveness.model_validate({**live, "in_flight": -1})


def test_a_schedule_needs_a_wall_clock_limit():
    """R36."""
    schedule = {"name": "s", "cron": "0 7 * * *", "missed_run": {"kind": "skip"},
                "target": "isolated", "run": {"command": ["true"], "wake_when": "stdout"}}
    with pytest.raises(ValidationError):
        pdi.Declaration.model_validate(_declaration(schedules=[schedule]))


def _schedule(**over):
    schedule = {"name": "s", "cron": "0 7 * * *", "missed_run": {"kind": "skip"},
                "target": "isolated", "run": {"command": ["true"], "wake_when": "stdout"},
                "timeout_s": 60}
    schedule.update(over)
    return schedule


def test_a_declaration_with_schedules_names_its_timezone():
    """A bare cron reads in local time on a host and usually in UTC in a container, so a
    declaration with schedules names the timezone they are all read in, and a name that
    is not one is refused rather than read as some other zone."""
    with pytest.raises(ValidationError, match="timezone"):
        pdi.Declaration.model_validate(_declaration(schedules=[_schedule()]))
    with pytest.raises(ValidationError, match="unknown timezone"):
        pdi.Declaration.model_validate(_declaration(schedules=[_schedule()], timezone="Mars/Olympus"))
    assert pdi.Declaration.model_validate(_declaration(schedules=[_schedule()], timezone="UTC")).timezone == "UTC"
    assert pdi.Declaration.model_validate(_declaration()).timezone is None


def test_a_schedule_whose_act_restarts_a_unit_says_so():
    """R27: a run that restarts a unit is never replayed after a downtime, so the schedule
    marks it; nothing restarts unless the declaration says it does."""
    decl = _declaration(schedules=[_schedule(), _schedule(name="t", restarts_unit=True)], timezone="UTC")
    marked = {s.name: s.restarts_unit for s in pdi.Declaration.model_validate(decl).schedules}
    assert marked == {"s": False, "t": True}


def test_a_daemon_start_carries_its_record_and_nothing_else():
    """pd_daemon_start: the fields of the daemon's record and the agent, closed like every event."""
    start = pdi.DaemonStart(agent=CARD, pid=4242, proc_start="1")
    assert (pdi.EVENT_DAEMON_START, start.version) == ("pd_daemon_start", 1)
    assert set(start.model_dump()) == set(pdi.DaemonRecord.model_fields) | {"agent"}
    with pytest.raises(ValidationError):
        pdi.DaemonStart(agent=CARD, pid=4242, proc_start="1", units=["session"])
