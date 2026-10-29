"""A rendered declaration is read in preference to the home copy, and refused unless only root
can change it (MIS-0002-R33 (run_MUST-NOT_change_schedules)). A test isn't root, so the owner the
check wants is set to the test's own uid; the refusals are what a run as the agent could do."""
import json
import os
import pwd

import pytest

from macf.pd import core
from macf.pd import names

CARD = "Resident@1a2b3c"
UNIT = {"name": "broker", "command": ["true"], "account": pwd.getpwuid(os.getuid()).pw_name, "restart": "always",
        "liveness_interval_s": 30, "memory_limit_mb": 64}


@pytest.fixture
def layout(tmp_path, monkeypatch):
    monkeypatch.setattr(names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    monkeypatch.setattr(names, "SEAL_UID", os.getuid())
    home = tmp_path / "home" / "resident"
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff" / "pd" / "declaration.json").write_text(
        json.dumps({"version": 1, "agent": CARD, "units": []}))          # the agent's own copy
    rendered = tmp_path / "etc" / "resident" / "declaration.json"
    rendered.parent.mkdir(parents=True)
    rendered.write_text(json.dumps({"version": 1, "agent": CARD, "units": [UNIT]}))
    for p in (tmp_path / "etc", rendered.parent):
        p.chmod(0o755)
    rendered.chmod(0o644)
    return home, rendered


def test_the_rendered_declaration_is_read_and_the_home_copy_is_not(layout):
    home, rendered = layout
    assert names.declaration_path(home) == rendered
    assert [u.name for u in core.load_declaration(home, CARD).units] == ["broker"]


def test_without_a_rendering_the_home_copy_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    home = tmp_path / "home" / "resident"
    assert names.declaration_path(home) == home / ".maceff" / "pd" / "declaration.json"


@pytest.mark.parametrize("loosen", ["file group-writable", "directory world-writable", "file a symlink"])
def test_a_rendering_the_agent_could_change_is_refused(layout, loosen):
    home, rendered = layout
    if loosen == "file group-writable":
        rendered.chmod(0o664)
    elif loosen == "directory world-writable":
        rendered.parent.chmod(0o777)
    else:
        real = rendered.with_name("real.json")
        rendered.rename(real)
        rendered.symlink_to(real)
    with pytest.raises(core.DeclarationRefused, match="R33"):
        core.load_declaration(home, CARD)


def test_a_rendering_owned_by_someone_else_is_refused(layout, monkeypatch):
    home, _ = layout
    monkeypatch.setattr(names, "SEAL_UID", os.getuid() + 1)     # the files are not the sealer's
    with pytest.raises(core.DeclarationRefused, match="owned by uid"):
        core.load_declaration(home, CARD)


def test_a_writable_parent_of_the_rendered_root_is_refused(layout, tmp_path):
    """Whoever can write the rendered root's parent can move the root aside and put another there."""
    home, _ = layout
    tmp_path.chmod(0o777)
    try:
        with pytest.raises(core.DeclarationRefused, match="group or others"):
            core.load_declaration(home, CARD)
    finally:
        tmp_path.chmod(0o700)


def test_a_body_the_daemon_would_refuse_is_refused_when_agents_yaml_loads():
    """Review of #702: the load-time check had no test; replacing it with a no-op passed everything."""
    from macf.models.agent_spec import AgentSpec
    bad_schedule = {"timezone": "UTC", "schedules": [{"name": "s", "cron": "0 3 * * *", "target": "isolated",
                    "run": {"command": ["true"], "wake_when": "exit_code"}, "timeout_s": 60}]}  # no missed_run
    with pytest.raises(ValueError, match="missed_run"):
        AgentSpec(username="pa_x", uid=21100, personality="p.md", primal_daemon=bad_schedule)
    with pytest.raises(ValueError, match="must not set agent or version"):
        AgentSpec(username="pa_x", uid=21100, personality="p.md",
                  primal_daemon={"agent": "Other@000000", "units": []})



def test_an_agent_daemon_needs_a_calling_card_when_agents_yaml_loads():
    """persistent_layer 10.1: a container agent's daemon runs under the card agents.yaml declares,
    so primal_daemon without calling_card is refused at load, naming the agent and the field,
    rather than found at start as a daemon whose card can't be read. A card alone is fine, a card
    takes a service card's form, and a vanilla account can't carry one."""
    from macf.models.agent_spec import AgentsConfig, AgentSpec

    def agents_yaml(**fields):
        return AgentsConfig.model_validate({"ids": {"base": 21000}, "subagents": {}, "agents": {
            "manny1": {"username": "pa_manny", "uid": 21100, "personality": "p.md", **fields}}})
    with pytest.raises(ValueError, match=r"'pa_manny' declares primal_daemon without calling_card"):
        agents_yaml(primal_daemon={"units": []})
    assert agents_yaml(calling_card="Manny1").agents["manny1"].calling_card == "Manny1"
    assert agents_yaml(calling_card="Manny1", primal_daemon={"units": []}).agents["manny1"].primal_daemon
    for bad in ("1Manny", "Manny@1", "Manny One", "M" * 49):
        with pytest.raises(ValueError, match="calling_card"):
            agents_yaml(calling_card=bad)
    with pytest.raises(ValueError, match="vanilla and declares calling_card"):
        AgentSpec(username="pa_v", uid=21101, flavor="vanilla", calling_card="Vanilla")
