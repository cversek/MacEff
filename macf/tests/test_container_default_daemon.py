"""Every container agent that isn't vanilla gets a primal daemon by default (persistent_layer 10.1).

Start-up renders, for each such agent, the container default (``pd.default_declaration
.container_body``: the session as a unit) with whatever the agent's ``primal_daemon`` declares laid
over it. An agent opts out only with a reason, which start-up logs at every start, and one that
should have a daemon and can't get one fails the start step by name.
"""
import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from macf.models.agent_spec import AgentsConfig
from macf.pd.interface import Declaration

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"
TELEGRAM = "plugin:telegram@claude-plugins-official"
CLOCK = {"name": "clock", "command": ["/usr/bin/true"], "account": "pa_res", "restart": "always",
         "liveness_interval_s": 30, "memory_limit_mb": 256}


def _agent(**extra):
    spec = {"username": "pa_res", "uid": 21100, "personality": "../agents/resident.md",
            "claude_config": {"channels": [TELEGRAM]}}
    spec.update(extra)
    return spec


def _config(agents, services=None):
    return AgentsConfig.model_validate({"ids": {"base": 21000}, "agents": agents, "subagents": {},
                                        "services": services or {}})


def _body(name="Resident", mail=False, **extra):
    config = _config({name: _agent(**extra)})
    return config.agents[name].effective_primal_daemon(name, mail=mail)


def _session(body):
    return next(u for u in body["units"] if u.get("kind") == "session")


def test_an_agent_that_declares_nothing_gets_the_default_session():
    """No block, no opt-out: the session runs as a unit of the agent's own daemon, on its own
    account, in its home, under its declared tmux name, with its channels and the MacEff channel,
    and the result is a declaration the daemon accepts."""
    body = _body(harness_session="res")
    assert [u["name"] for u in body["units"]] == ["session"]
    session = _session(body)
    assert session["account"] == "pa_res" and session["restart"] == "always"
    command = session["command"]
    assert command[command.index("--project-dir") + 1] == "{agent_home}"
    assert command[command.index("--agent") + 1] == "res" and "--no-proxy" in command
    env = session["environment"]
    assert env["MACEFF_HARNESS_SESSION"] == "res" and env["USER"] == env["LOGNAME"] == "pa_res"
    assert env["MACEFF_CHANNELS"] == f"{TELEGRAM} plugin:maceff-channel@maceff"
    assert {"plugin": "maceff-channel", "marketplace": "maceff"} in body["allowlisted_channels"]
    assert body["operator_channels"] == ["plugin:telegram:telegram"]
    Declaration(version=1, agent="Resident@1a2b3c", **body)
    # The tmux name falls back to the agent's key, as provisioning's does.
    assert _session(_body())["environment"]["MACEFF_HARNESS_SESSION"] == "Resident"


def test_the_session_starts_where_the_login_shell_always_did():
    """A seat moved onto its daemon continues the same conversation only if its session starts in
    the same directory: the active_project link with assigned projects, else the home, and an
    explicit project_dir over both. The memory limit is declarable the same way."""
    def project(**extra):
        return _session(_body(**extra))["environment"]["MACEFF_PROJECT_DIR"]
    assert project() == "{agent_home}"
    assert project(assigned_projects=["NeuroVEP"]) == "/home/pa_res/active_project"
    assert project(assigned_projects=["NeuroVEP"], project_dir="/home/pa_res/workspace/NeuroVEP") \
        == "/home/pa_res/workspace/NeuroVEP"
    assert _session(_body(session_memory_mb=28672))["memory_limit_mb"] == 28672


def test_the_session_keeps_the_deployments_time_zone(monkeypatch):
    """A unit inherits nothing, so the login shell's TZ doesn't reach it. Without this the seat's
    clock moves to UTC when it moves onto its daemon, while its login shells stay on local time."""
    monkeypatch.setenv("MACEFF_TZ", "America/New_York")
    assert _session(_body())["environment"]["TZ"] == "America/New_York"
    Declaration(version=1, agent="Resident@1a2b3c", **_body())
    for unset in (lambda: monkeypatch.delenv("MACEFF_TZ"), lambda: monkeypatch.setenv("MACEFF_TZ", "")):
        unset()
        assert "TZ" not in _session(_body())["environment"]


def test_a_declared_block_is_laid_over_the_default():
    """A deployment states only what differs: its session replaces the default's, a unit of its
    own is added after it, and any other key it sets replaces the default's value."""
    own_session = {"name": "session", "kind": "session", "command": ["/usr/bin/true"], "account": "pa_res",
                   "restart": "always", "liveness_interval_s": 120, "memory_limit_mb": 1024}
    body = _body(calling_card="Resident", primal_daemon={"units": [CLOCK], "operator_channels": []})
    assert [u["name"] for u in body["units"]] == ["session", "clock"]
    assert body["units"][1] == CLOCK and body["operator_channels"] == []
    assert body["allowlisted_channels"]                     # kept from the default
    replaced = _body(calling_card="Resident", primal_daemon={"units": [own_session, CLOCK]})
    assert replaced["units"] == [own_session, CLOCK]


def test_vanilla_and_opted_out_agents_get_none():
    """A vanilla account gets no MacEff footprint and so no daemon; an agent that opts out with a
    reason gets none either."""
    vanilla = _config({"plain": {"username": "pa_plain", "uid": 21101, "flavor": "vanilla"}}).agents["plain"]
    assert not vanilla.has_daemon() and vanilla.effective_primal_daemon("plain", mail=True) is None
    assert _body(primal_daemon_opt_out="mid-experiment; moves after the freeze") is None


def test_an_opt_out_needs_a_reason_and_stands_alone():
    """An opt-out without a reason, one beside a declaration, and one on a vanilla account are each
    refused when agents.yaml loads, naming the agent."""
    for bad in ("", "   "):
        with pytest.raises(ValidationError):
            _body(primal_daemon_opt_out=bad)
    with pytest.raises(ValidationError, match="declares primal_daemon and opts out"):
        _body(calling_card="Resident", primal_daemon={"units": [CLOCK]}, primal_daemon_opt_out="why")
    with pytest.raises(ValidationError, match="vanilla and opts out"):
        _config({"plain": {"username": "pa_plain", "uid": 21101, "flavor": "vanilla",
                           "primal_daemon_opt_out": "why"}})


def test_mail_notices_are_routed_only_where_a_broker_runs():
    config = _config({"Resident": _agent()})
    assert not config.runs_mail()
    assert _body(mail=False)["notice_routes"] == {}
    assert _body(mail=True)["notice_routes"] == {"amail": "agent"}


def test_the_card_is_the_declared_one_else_the_key_when_it_can_be_one():
    config = _config({"Resident": _agent(), "res_two": _agent(username="pa_two", uid=21101),
                      "Named": _agent(username="pa_named", uid=21102, calling_card="Other")})
    assert config.agents["Resident"].effective_calling_card("Resident") == "Resident"
    assert config.agents["res_two"].effective_calling_card("res_two") is None
    assert config.agents["Named"].effective_calling_card("Named") == "Other"


# ---- start-up ---------------------------------------------------------------

def _start():
    spec = importlib.util.spec_from_file_location("maceff_start_default_daemon", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _home(root, user, uuid):
    home = root / "home" / user
    home.mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text(uuid)
    return home


def test_start_renders_the_default_and_names_an_agent_left_without_one(tmp_path, monkeypatch):
    """Start-up renders the default for an agent that declares nothing, under the card it writes
    from the agent's key, logs an opt-out with its reason, and fails the daemons step naming an
    agent that should have a daemon and couldn't get one (here: no usable card), after starting
    the others."""
    import os
    start = _start()
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")
    monkeypatch.setattr(start, "account_ids", lambda name: (os.getuid(), os.getgid()))
    _home(tmp_path, "pa_res", "1a2b3c4d-0000")
    _home(tmp_path, "pa_two", "9f8e7d6c-0000")
    _home(tmp_path, "pa_off", "5a5a5a5a-0000")
    said = []
    monkeypatch.setattr(start, "log", said.append)
    config = _config({"Resident": _agent(),
                      "res_two": _agent(username="pa_two", uid=21101),
                      "Off": _agent(username="pa_off", uid=21102, primal_daemon_opt_out="moves Thursday")})
    from macf.pd import names as pd_names
    monkeypatch.setattr(pd_names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    rendered = start.render_pd_declarations(config, root=tmp_path / "etc", chown=lambda p, u, g: None)
    assert rendered == ["pa_res"], said
    declaration = json.loads((tmp_path / "etc" / "pa_res" / "declaration.json").read_text())
    assert declaration["agent"] == "Resident@1a2b3c"
    assert [u["name"] for u in declaration["units"]] == ["session"]
    assert any("pa_off" in line and "moves Thursday" in line for line in said)
    assert not (tmp_path / "etc" / "pa_off").exists()

    supervised = []
    monkeypatch.setattr(start, "supervise_primal_daemon", lambda user, home: supervised.append(user))
    monkeypatch.setattr(pd_names, "rendered_declaration_path",
                        lambda home: tmp_path / "etc" / Path(home).name / "declaration.json")
    with pytest.raises(RuntimeError, match="pa_two") as failed:
        start.start_primal_daemons(config)
    assert "pa_off" not in str(failed.value)
    import time
    for _ in range(100):
        if supervised:
            break
        time.sleep(0.01)
    assert supervised == ["pa_res"]


def test_a_home_keeps_the_name_it_holds_and_only_a_nameless_home_takes_the_key(tmp_path, monkeypatch):
    """The second maintainer's case: a seat keyed ``resident`` whose home holds moniker
    ``Resident`` keeps that name and renders under it, never refused for the key's case. A home
    that names no agent takes the key. A declared card is still written as declared."""
    import os
    start = _start()
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")
    monkeypatch.setattr(start, "account_ids", lambda name: (os.getuid(), os.getgid()))
    named = _home(tmp_path, "pa_res", "1a2b3c4d-0000")
    (named / ".maceff").mkdir()
    held = json.dumps({"agent_identity": {"moniker": "Resident"}, "other": 1})
    (named / ".maceff" / "config.json").write_text(held)
    bare = _home(tmp_path, "pa_bare", "9f8e7d6c-0000")
    config = _config({"resident": _agent(), "Bare": _agent(username="pa_bare", uid=21101)})
    from macf.pd import names as pd_names
    monkeypatch.setattr(pd_names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    rendered = start.render_pd_declarations(config, root=tmp_path / "etc", chown=lambda p, u, g: None)
    assert sorted(rendered) == ["pa_bare", "pa_res"]
    assert (named / ".maceff" / "config.json").read_text() == held          # untouched
    assert json.loads((tmp_path / "etc" / "pa_res" / "declaration.json").read_text())["agent"] \
        == "Resident@1a2b3c"
    assert json.loads((bare / ".maceff" / "config.json").read_text())["agent_identity"]["calling_card"] == "Bare"
    assert start.home_agent_name(bare) == "Bare" and start.home_agent_name(tmp_path / "none") is None
