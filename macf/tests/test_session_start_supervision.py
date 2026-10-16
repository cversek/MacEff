"""A session that isn't its primal daemon's session unit says so at its start
(persistent_layer 6.2). It is also the check for moving sessions onto their daemons:
after the move, no session says it."""
from types import SimpleNamespace

import pytest

from macf.hooks import handle_session_start as hss
from macf.pd.interface import Declaration, declaration_path
from macf.pd.liveness import ENV_SESSION_PID, ENV_SESSION_UNIT


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(hss, "get_agent_identity", lambda: "Resident@1a2b3c")
    return tmp_path


def _declare(home):
    path = declaration_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Declaration(version=1, agent="Resident@1a2b3c").model_dump_json())


def _daemon_says(unit="session", pid="4242", state="running"):
    return lambda: SimpleNamespace(source="daemon", why="", units=[{"unit": unit, "pid": pid, "state": state}])


def test_an_agent_with_no_daemon_hears_nothing(home):
    assert hss._supervision_block(environ={"MACEFF_AGENT_HOME_DIR": str(home)}) == ""


def test_a_session_outside_its_daemon_says_so(home):
    _declare(home)
    text = hss._supervision_block(environ={"MACEFF_AGENT_HOME_DIR": str(home)})
    assert "isn't running as its session unit" in text and "won't restart it" in text


def test_a_session_the_daemon_confirms_is_silent(home):
    _declare(home)
    env = {"MACEFF_AGENT_HOME_DIR": str(home), ENV_SESSION_UNIT: "session", ENV_SESSION_PID: "4242"}
    assert hss._supervision_block(environ=env, ask=_daemon_says()) == ""


def test_a_claim_the_daemon_does_not_confirm_is_named(home):
    _declare(home)
    env = {"MACEFF_AGENT_HOME_DIR": str(home), ENV_SESSION_UNIT: "session", ENV_SESSION_PID: "4242"}
    text = hss._supervision_block(environ=env, ask=_daemon_says(pid="9999"))
    assert "unit session (pid 4242), but the daemon doesn't confirm it" in text
    assert "the daemon's session is pid 9999, not this session's 4242" in text


def test_without_the_variable_the_home_is_found_as_the_other_hooks_find_it(home, monkeypatch):
    """Several agents can share one login, with homes below ~; the bare login home would be
    the wrong place to look (host-side maintainer, on review)."""
    from macf.utils import paths
    _declare(home)
    monkeypatch.setattr(paths, "find_agent_home", lambda: home)
    assert "isn't running as its session unit" in hss._supervision_block(environ={})


def test_a_failure_never_breaks_session_start(home, monkeypatch):
    _declare(home)

    def broken():
        raise OSError("identity file unreadable")
    monkeypatch.setattr(hss, "get_agent_identity", broken)
    assert hss._supervision_block(environ={"MACEFF_AGENT_HOME_DIR": str(home)}) == ""
