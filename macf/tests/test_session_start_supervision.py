"""A session that isn't its primal daemon's session unit says so at its start
(persistent_layer 6.2). It is also the check for moving sessions onto their daemons:
after the move, no session says it."""
import json
from types import SimpleNamespace

import pytest

from macf.hooks import handle_session_start as hss
from macf.pd.interface import Declaration, declaration_path
from macf.pd.liveness import ENV_SESSION_PID, ENV_SESSION_UNIT


def _write_identity(home, name="Resident"):
    (home / ".maceff").mkdir(parents=True, exist_ok=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": name}}))
    (home / ".maceff_primary_agent.id").write_text("1a2b3c4d-0000-0000-0000-000000000000\n")


@pytest.fixture
def home(tmp_path, monkeypatch):
    _write_identity(tmp_path)
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

    (home / ".maceff_primary_agent.id").unlink()  # the home names no agent: agent_card raises
    assert hss._supervision_block(environ={"MACEFF_AGENT_HOME_DIR": str(home)}) == ""


def test_the_daemon_is_named_by_the_homes_card_not_the_environment(home, monkeypatch):
    """A seat whose MACEFF_AGENT_NAME spells its name differently from its card ("seat2"
    against "Seat2") named a socket its daemon never made (MIS-0002-R02)."""
    _write_identity(home, name="Seat2")
    _declare(home)
    asked = []
    monkeypatch.setattr("macf.utils.supervision.primal_daemon_unit",
                        lambda card, environ=None, ask=None: asked.append(card) or None)
    monkeypatch.setenv("MACEFF_AGENT_NAME", "seat2")
    hss._supervision_block(environ={"MACEFF_AGENT_HOME_DIR": str(home), "MACEFF_AGENT_NAME": "seat2"})
    assert asked == ["Seat2@1a2b3c"]
