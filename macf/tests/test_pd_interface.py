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
    schedule = {"name": "s", "cron": "0 7 * * *", "target": "isolated", "prompt_file": "p.md"}
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
