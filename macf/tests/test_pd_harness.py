"""The Claude Code harness adapter and the client's own supervisor.

MIS-0002-R66 (pd_MUST_adopt_harness_supervisor): a session the client's background
daemon already hosts is adopted, never supervised a second time, and acted on through
the client's own verbs.
"""
from dataclasses import dataclass

import pytest

from macf.utils.client_daemon import ADOPT, REFUSE, START, client_command, decide, unit_state


@dataclass
class _Unit:
    name: str
    kind: str


@dataclass
class _Hosted:
    pid: int
    session_id: str
    cwd: str
    status: str = "idle"


def test_adopts_harness_supervisor(tmp_path):
    """One hosted session in the agent home is adopted, and its control acts are client verbs."""
    home = tmp_path / "home"
    home.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    hosted = [_Hosted(101, "8d48008b-aaaa", str(other)), _Hosted(202, "3d52b89a-bbbb", str(home))]

    d = decide(_Unit("session", "session"), hosted, home)

    assert (d.action, d.session_id, d.pid) == (ADOPT, "3d52b89a-bbbb", 202)
    assert client_command("restart", d.session_id) == ["claude", "respawn", "3d52b89a-bbbb"]
    assert client_command("stop", d.session_id) == ["claude", "stop", "3d52b89a-bbbb"]


def test_two_hosted_sessions_in_the_home_are_refused_not_guessed(tmp_path):
    hosted = [_Hosted(1, "aaaaaaaa-1", str(tmp_path)), _Hosted(2, "bbbbbbbb-2", str(tmp_path))]
    d = decide(_Unit("session", "session"), hosted, tmp_path)
    assert d.action == REFUSE and d.session_id is None
    assert "aaaaaaaa" in d.reason and "bbbbbbbb" in d.reason


def test_no_hosted_session_and_service_units_are_started(tmp_path):
    hosted = [_Hosted(1, "aaaaaaaa-1", str(tmp_path))]
    assert decide(_Unit("session", "session"), [], tmp_path).action == START
    assert decide(_Unit("broker", "service"), hosted, tmp_path).action == START


def test_a_control_act_is_never_a_signal():
    with pytest.raises(ValueError):
        client_command("kill", "aaaaaaaa-1")
    with pytest.raises(ValueError):
        client_command("stop", "")


def test_turn_state_never_claims_a_person_is_awaited():
    state, reason = unit_state("busy")
    assert state == "running" and "busy" in reason
