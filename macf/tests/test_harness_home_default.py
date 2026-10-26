"""The harness's parameters default their home to the agent home, found as ``macf_tools env``
finds it, not the login's ~."""

from pathlib import Path

from macf.utils.harness import default_params
from macf.utils.paths import find_agent_home


def test_default_params_finds_the_project_root_agent_home(tmp_path, monkeypatch):
    agent_home, login = tmp_path / "agent_home", tmp_path / "login"
    (agent_home / ".maceff").mkdir(parents=True)
    (agent_home / ".maceff" / "agent_events_log.jsonl").write_text("")
    (agent_home / "sub").mkdir()
    login.mkdir()
    monkeypatch.delenv("MACEFF_AGENT_HOME_DIR", raising=False)
    monkeypatch.setenv("HOME", str(login))
    monkeypatch.chdir(agent_home / "sub")
    find_agent_home.cache_clear()
    try:
        p = default_params(agent="Agent_abc123")
        assert p.home == agent_home.resolve()
        assert p.child_path == agent_home.resolve() / ".local" / "bin" / "maceff_cc_child_Agent_abc123"
    finally:
        find_agent_home.cache_clear()


def test_default_params_named_home_wins(tmp_path):
    assert default_params(agent="Agent_abc123", home=tmp_path).home == Path(tmp_path)
