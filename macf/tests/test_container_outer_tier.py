"""The container's outer tier for primal daemons (MIS-0002-R03, R57; first-seat plan step 1).

In a container there is no systemd or launchd to restart an agent's primal daemon, so
start.py does it: for each agent whose home declares a daemon, a thread starts it as that
agent and restarts it when it exits, with the systemd unit's backoff. An agent without a
declaration is started exactly as before.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"


def _start():
    spec = importlib.util.spec_from_file_location("maceff_start_outer_tier", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Runs:
    """A stand-in for Popen: each run exits with the next code, after `lasted` seconds."""

    def __init__(self, codes, lasted, clock):
        self.codes, self.lasted, self.clock, self.argvs, self.envs = list(codes), lasted, clock, [], []

    def __call__(self, argv, env=None):
        self.argvs.append(argv)
        self.envs.append(env)
        code = self.codes.pop(0)
        clock = self.clock
        lasted = self.lasted
        return SimpleNamespace(wait=lambda: (clock.advance(lasted), code)[1])


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def _supervise(start, codes, lasted):
    clock, slept = _Clock(), []
    runs = _Runs(codes, lasted, clock)
    left = [len(codes)]

    def keep_going():
        left[0] -= 1
        return left[0] >= 0
    start.supervise_primal_daemon("pa_x", Path("/home/pa_x"), run=runs, sleep=slept.append,
                                  clock=clock, keep_going=keep_going)
    return runs, slept


def test_a_failing_daemon_is_restarted_with_the_units_backoff():
    start = _start()
    runs, slept = _supervise(start, [1, 1, 1, 1, 1], lasted=2)
    assert slept == [10, 20, 40, 60, 60]
    assert len(runs.argvs) == 5
    argv = runs.argvs[0]
    assert argv[1:4] == ["-u", "pa_x", "--"] and argv[-3:] == ["-m", "macf.pd", "/home/pa_x"]
    # runuser by absolute path: Popen searches the daemon's PATH, which holds no sbin directory
    assert argv[0].startswith("/") and argv[0].endswith("runuser")


def test_a_daemon_that_ran_a_while_starts_the_backoff_over():
    start = _start()
    _, slept = _supervise(start, [1, 1], lasted=start.PD_STABLE_S + 1)
    assert slept == [10, 10]


def test_an_unusable_home_is_not_restarted():
    start = _start()
    runs, slept = _supervise(start, [start.PD_EXIT_UNUSABLE_HOME, 0, 0], lasted=1)
    assert len(runs.argvs) == 1 and slept == []


def test_another_running_daemon_is_checked_again_at_the_slowest_pace():
    start = _start()
    _, slept = _supervise(start, [start.PD_EXIT_ALREADY_RUNS], lasted=0)
    assert slept == [start.PD_BACKOFF_CAP_S]


def test_the_daemon_gets_who_and_where_it_is_and_no_agent_configuration():
    start = _start()
    runs, _ = _supervise(start, [1], lasted=1)
    env = runs.envs[0]
    assert env["HOME"] == "/home/pa_x" and env["USER"] == "pa_x"
    assert set(env) == {"HOME", "USER", "LOGNAME", "PATH", "LANG"}


def _wait_for(supervised):
    import time
    for _ in range(50):
        if supervised:
            break
        time.sleep(0.01)


def test_only_agents_with_a_rendered_declaration_get_a_daemon(tmp_path, monkeypatch):
    """MIS-0002-R33: the outer tier starts a daemon for a declaration the deployment rendered.
    One only in the agent's home starts nothing, because a run could rewrite it."""
    start = _start()
    from macf.pd import names as pd_names
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")
    monkeypatch.setattr(pd_names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    for user in ("pa_a", "pa_b", "pa_c"):
        (tmp_path / "home" / user).mkdir(parents=True)
    rendered = tmp_path / "etc" / "pa_b" / "declaration.json"
    rendered.parent.mkdir(parents=True)
    rendered.write_text(json.dumps({"units": []}))
    home_only = tmp_path / "home" / "pa_c" / start.PD_DECLARATION      # written by the agent
    home_only.parent.mkdir(parents=True)
    home_only.write_text(json.dumps({"units": []}))
    supervised = []
    monkeypatch.setattr(start, "supervise_primal_daemon", lambda user, home: supervised.append(user))
    cfg = SimpleNamespace(services={}, agents={u: SimpleNamespace(username=u, primal_daemon=None) for u in ("pa_a", "pa_b", "pa_c")})
    # pa_c's schedules would have no daemon (MIS-0002-R11): the step fails, naming it, after
    # pa_b's daemon has started
    import pytest
    with pytest.raises(RuntimeError, match="pa_c"):
        start.start_primal_daemons(cfg)
    _wait_for(supervised)
    assert supervised == ["pa_b"]


def _rendering(tmp_path, monkeypatch, primal_daemon):
    start = _start()
    from macf.pd import names as pd_names
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")
    monkeypatch.setattr(pd_names, "agent_card", lambda home: "Resident@1a2b3c")
    (tmp_path / "home" / "pa_a").mkdir(parents=True)
    chowned = []
    cfg = SimpleNamespace(services={}, agents={"a": SimpleNamespace(username="pa_a", primal_daemon=primal_daemon)})
    done = start.render_pd_declarations(cfg, root=tmp_path / "etc",
                                        chown=lambda p, u, g: chowned.append((str(p), u, g)))
    return SimpleNamespace(start=start, done=done, chowned=chowned)


UNIT = {"name": "broker", "command": ["true"], "account": "pa_a", "restart": "always",
        "liveness_interval_s": 30, "memory_limit_mb": 64}


def test_the_declaration_is_rendered_from_agents_yaml_owned_by_root(tmp_path, monkeypatch):
    """R33: the file and its directory go to root, the file 0644, the directories 0755, with the
    agent's card and the version filled in."""
    r = _rendering(tmp_path, monkeypatch, {"units": [UNIT]})
    target = tmp_path / "etc" / "pa_a" / "declaration.json"
    assert r.done == ["pa_a"]
    data = json.loads(target.read_text())
    assert data["agent"] == "Resident@1a2b3c" and data["version"] == 1 and data["units"][0]["name"] == "broker"
    assert oct(target.stat().st_mode)[-3:] == "644" and oct(target.parent.stat().st_mode)[-3:] == "755"
    owned = {Path(p).name: (u, g) for p, u, g in r.chowned}
    assert owned["etc"] == owned["pa_a"] == (0, 0)
    assert any(p.endswith(".declaration.json.tmp") and (u, g) == (0, 0) for p, u, g in r.chowned)


def test_an_agent_that_declares_none_has_its_old_rendering_removed(tmp_path, monkeypatch):
    stale = tmp_path / "etc" / "pa_a" / "declaration.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    assert _rendering(tmp_path, monkeypatch, None).done == [] and not stale.exists()



def test_one_agents_broken_identity_costs_only_that_agents_rendering(tmp_path, monkeypatch):
    """Review of #702: an agent whose calling card can't be read gets no rendering, and its old one
    goes, while every other agent still renders, so the daemons step isn't skipped for all (R58)."""
    start = _start()
    from macf.pd import names as pd_names
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")

    def card(home):
        if Path(home).name == "pa_bad":
            raise pd_names.IdentityError("no identity file")
        return "Good@1a2b3c"
    monkeypatch.setattr(pd_names, "agent_card", card)
    for user in ("pa_good", "pa_bad"):
        (tmp_path / "home" / user).mkdir(parents=True)
    stale = tmp_path / "etc" / "pa_bad" / "declaration.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    cfg = SimpleNamespace(services={}, agents={u: SimpleNamespace(username=u, primal_daemon={"units": [UNIT]})
                                  for u in ("pa_good", "pa_bad")})
    done = start.render_pd_declarations(cfg, root=tmp_path / "etc", chown=lambda p, u, g: None)
    assert done == ["pa_good"]
    assert (tmp_path / "etc" / "pa_good" / "declaration.json").exists() and not stale.exists()


def test_one_agents_failed_write_costs_only_that_agents_rendering(tmp_path, monkeypatch):
    """Review of #702: a write that fails for one agent (here the chown of its temporary file)
    leaves no stale or partial rendering for it, and the agents after it still render."""
    start = _start()
    from macf.pd import names as pd_names
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")
    monkeypatch.setattr(pd_names, "agent_card", lambda home: "Good@1a2b3c")
    for user in ("pa_bad", "pa_good"):
        (tmp_path / "home" / user).mkdir(parents=True)
    stale = tmp_path / "etc" / "pa_bad" / "declaration.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")

    def chown(path, uid, gid):
        if Path(path).parent.name == "pa_bad" and Path(path).name.endswith(".tmp"):
            raise PermissionError("chown refused")
    cfg = SimpleNamespace(services={}, agents={u: SimpleNamespace(username=u, primal_daemon={"units": [UNIT]})
                                  for u in ("pa_bad", "pa_good")})
    done = start.render_pd_declarations(cfg, root=tmp_path / "etc", chown=chown)
    assert done == ["pa_good"]
    assert (tmp_path / "etc" / "pa_good" / "declaration.json").exists()
    assert not stale.exists() and not (stale.parent / ".declaration.json.tmp").exists()


def test_an_agent_removed_from_agents_yaml_leaves_no_rendering(tmp_path, monkeypatch):
    gone = tmp_path / "etc" / "pa_gone" / "declaration.json"
    gone.parent.mkdir(parents=True)
    gone.write_text("{}")
    _rendering(tmp_path, monkeypatch, {"units": [UNIT]})
    assert not gone.parent.exists()
    assert (tmp_path / "etc" / "pa_a" / "declaration.json").exists()

def test_the_declarations_render_before_the_daemons_start():
    src = START_PY.read_text()
    assert src.index('("primal daemon declarations",') < src.index('("primal daemons",')
    assert '"primal daemon declarations")),' in src     # the daemons step needs the rendering


def test_primal_daemons_start_after_access_and_before_optional_units():
    """R57: the access path first; the daemons before the optional units (policy index,
    search service), in run_after_access's order."""
    src = START_PY.read_text()
    at = {name: src.index(f'("{name}",') for name in
          ("MACF tools", "agent initialization", "amail", "primal daemons", "policy index", "search service")}
    assert at["agent initialization"] < at["primal daemons"] < at["policy index"] < at["search service"]


def test_main_starts_the_access_path_before_the_daemons_and_both_before_any_optional_unit(
        tmp_path, monkeypatch):
    """R57, at the place it names: main() itself, run in-process with every step stubbed to
    record when it runs. sshd (the access path) must start before the primal daemons, and
    both before the optional units (policy index, search service)."""
    import subprocess
    start = _start()
    order = []
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text("{}\n")
    monkeypatch.setattr(start, "AGENTS_CONFIG", agents_yaml)
    monkeypatch.setattr(start, "PROJECTS_CONFIG", tmp_path / "absent.yaml")
    cfg = SimpleNamespace(agents={}, subagents={}, defaults=None, ids=SimpleNamespace(slot=lambda name: 0))
    monkeypatch.setattr(start, "AgentsConfig", lambda **kw: cfg)
    for quiet in ("run_command", "check_image_ids", "check_service_paths", "ensure_group",
                  "setup_shared_workspace_permissions", "apply_egress_policy",
                  "propagate_container_env", "install_ssh_key", "install_macf_tools",
                  "initialize_agents", "setup_policies", "setup_policy_editors", "place_secrets",
                  "start_amail_services", "render_pd_declarations"):
        monkeypatch.setattr(start, quiet, lambda *a, **kw: None)
    for name, recorded in (("start_primal_daemons", "primal daemons"),
                           ("start_policy_index", "policy index"),
                           ("start_search_service_daemon", "search service")):
        monkeypatch.setattr(start, name, lambda *a, _r=recorded, **kw: order.append(_r))

    def popen(argv, *a, **kw):
        order.append("sshd" if argv[0].endswith("sshd") else argv[0])
        return SimpleNamespace(pid=1, wait=lambda: 0)
    monkeypatch.setattr(subprocess, "Popen", popen)

    start.main()
    assert {"sshd", "primal daemons", "policy index", "search service"} <= set(order), order
    optional = min(order.index("policy index"), order.index("search service"))
    assert order.index("sshd") < order.index("primal daemons") < optional, order


# ---- an agent's calling card, declared in agents.yaml and written to its home (persistent_layer 10.1) ----

def _carded(tmp_path, monkeypatch, cards, configs=None):
    """Homes for agents declaring *cards* (username -> card or None), each with an identity file
    and, from *configs*, an existing config.json (username -> (dict, mode)). Uses the real
    ``agent_card``, so a rendering names exactly what the home now holds."""
    import os
    start = _start()
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")
    monkeypatch.setattr(start, "account_ids", lambda name: (os.getuid(), os.getgid()))
    for i, user in enumerate(cards):
        home = tmp_path / "home" / user
        (home / ".maceff").mkdir(parents=True)
        (home / ".maceff_primary_agent.id").write_text(f"{i}a2b3c\n")
        if user in (configs or {}):
            data, mode = configs[user]
            (home / ".maceff" / "config.json").write_text(json.dumps(data))
            (home / ".maceff" / "config.json").chmod(mode)
    chowned = []
    cfg = SimpleNamespace(services={}, agents={
        u: SimpleNamespace(username=u, calling_card=card,
                           primal_daemon={"units": [{**UNIT, "account": u}]}) for u, card in cards.items()})
    done = start.render_pd_declarations(cfg, root=tmp_path / "etc",
                                        chown=lambda p, u, g: chowned.append((Path(p).name, u, g)))
    return SimpleNamespace(start=start, done=done, chowned=chowned,
                           config=lambda user: tmp_path / "home" / user / ".maceff" / "config.json",
                           rendered=lambda user: tmp_path / "etc" / user / "declaration.json")


def test_a_declared_card_is_written_into_a_home_without_one_and_the_daemon_renders_under_it(
        tmp_path, monkeypatch):
    """Guards the gap that kept every container agent's daemon from rendering: a home with no
    config.json gets one holding just the declared card, the agent's own, mode 0600, and the
    declaration names the card the daemon will read from that home."""
    import os
    r = _carded(tmp_path, monkeypatch, {"pa_manny": "Manny1"})
    config = r.config("pa_manny")
    assert json.loads(config.read_text()) == {"agent_identity": {"calling_card": "Manny1"}}
    assert oct(config.stat().st_mode)[-3:] == "600"
    assert ("config.json.tmp", os.getuid(), os.getgid()) in r.chowned
    assert r.done == ["pa_manny"]
    assert json.loads(r.rendered("pa_manny").read_text())["agent"] == "Manny1@0a2b3c"


def test_writing_the_card_keeps_every_other_key_and_the_files_owner_and_mode(tmp_path, monkeypatch):
    """The home's config.json carries the task store and the rest of the agent's identity, which
    nobody can reconstruct: the card is added beside them, and the file keeps its owner and mode
    (a mode other than 0600 here, so keeping it can't be mistaken for the default)."""
    import os
    existing = {"task_store": {"mode": "home", "path": "agent/public/tasks"},
                "agent_identity": {"display_name": "Manny MacEff"}}
    r = _carded(tmp_path, monkeypatch, {"pa_manny": "Manny1"}, {"pa_manny": (existing, 0o640)})
    config = r.config("pa_manny")
    assert json.loads(config.read_text()) == {
        "task_store": {"mode": "home", "path": "agent/public/tasks"},
        "agent_identity": {"display_name": "Manny MacEff", "calling_card": "Manny1"}}
    assert oct(config.stat().st_mode)[-3:] == "640"
    st = config.stat()
    assert ("config.json.tmp", st.st_uid, st.st_gid) in r.chowned
    assert r.done == ["pa_manny"]


def test_a_home_already_holding_the_card_is_left_untouched(tmp_path, monkeypatch):
    """At every start after the first the card is already there: the file isn't rewritten, so
    its inode and contents stay exactly as they were, and the daemon still renders."""
    existing = {"agent_identity": {"calling_card": "Manny1"}, "z": 1}
    home_config = tmp_path / "home" / "pa_manny" / ".maceff" / "config.json"
    start = _start()
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")
    home_config.parent.mkdir(parents=True)
    home_config.write_text(json.dumps(existing))
    before = (home_config.stat().st_ino, home_config.read_text())
    assert start.write_agent_card("pa_manny", "Manny1", tmp_path / "home" / "pa_manny",
                                  chown=lambda *a: None) is False
    assert (home_config.stat().st_ino, home_config.read_text()) == before
    home_config.unlink()
    r = _carded(tmp_path / "again", monkeypatch, {"pa_manny": "Manny1"}, {"pa_manny": (existing, 0o600)})
    assert not any(name == "config.json.tmp" for name, *_ in r.chowned) and r.done == ["pa_manny"]


def test_a_different_card_in_the_home_is_refused_and_costs_only_that_agent(tmp_path, monkeypatch, capsys):
    """An agent's card keys its daemon's sockets and unit names, so a card in the home that differs
    from agents.yaml is never overwritten. The conflict is logged by name with both values, and
    that agent alone gets no rendering (its old one goes), while the next agent still renders.
    A differing moniker counts the same, since the daemon reads it when no card is set."""
    for user in ("pa_clash", "pa_moniker"):
        stale = tmp_path / user / "etc" / user / "declaration.json"
        stale.parent.mkdir(parents=True)
        stale.write_text("{}")
    held = {"pa_clash": {"agent_identity": {"calling_card": "OldName"}},
            "pa_moniker": {"agent_identity": {"moniker": "OldName"}}}
    for user, data in held.items():
        r = _carded(tmp_path / user, monkeypatch, {user: "NewName", "pa_fine": "Fine"}, {user: (data, 0o600)})
        assert r.done == ["pa_fine"]
        assert json.loads(r.config(user).read_text()) == data
        assert not r.rendered(user).exists() and r.rendered("pa_fine").exists()
        err = capsys.readouterr().err
        assert user in err and "'OldName'" in err and "'NewName'" in err


def test_a_home_whose_moniker_is_the_declared_name_takes_the_card_and_renders(tmp_path, monkeypatch):
    """A moniker is the card's name without the id fragment, the shape agent init leaves (review
    of #805). agents.yaml declares the same bare name, so a home holding that moniker agrees with
    it: the card is written beside it, every other key stays, and the agent renders."""
    user = "pa_tester"
    data = {"agent_identity": {"moniker": "Tester", "type": "primary_agent"}}
    r = _carded(tmp_path / user, monkeypatch, {user: "Tester"}, {user: (data, 0o600)})
    assert r.done == [user]
    assert json.loads(r.config(user).read_text()) == {
        "agent_identity": {"moniker": "Tester", "type": "primary_agent", "calling_card": "Tester"}}
    assert r.rendered(user).exists()


def test_an_agent_without_a_calling_card_gets_nothing_written(tmp_path, monkeypatch):
    """A card is written only where agents.yaml declares one: an agent without it keeps its home
    as it was, with no config.json created and an existing one unchanged."""
    start = _start()
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")
    monkeypatch.setattr(start, "write_agent_card", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
    bare, kept = tmp_path / "home" / "pa_bare", tmp_path / "home" / "pa_kept"
    (bare / ".maceff").mkdir(parents=True)
    (kept / ".maceff").mkdir(parents=True)
    (kept / ".maceff" / "config.json").write_text('{"agent_identity": {"calling_card": "Kept"}}')
    cfg = SimpleNamespace(services={}, agents={
        "bare": SimpleNamespace(username="pa_bare", calling_card=None, primal_daemon=None),
        "kept": SimpleNamespace(username="pa_kept", primal_daemon=None)})
    assert start.write_agent_cards(cfg) == {}
    assert not (bare / ".maceff" / "config.json").exists()
    assert (kept / ".maceff" / "config.json").read_text() == '{"agent_identity": {"calling_card": "Kept"}}'


OWN_SCHEDULE = {"name": "sweep", "cron": "47 9 * * *", "missed_run": {"kind": "run_once"},
                "target": "{card}", "timeout_s": 900,
                "run": {"command": ["/usr/bin/true"], "wake_when": "exit_code"}}


def test_a_schedule_targeting_its_own_card_is_rendered_with_the_agents_card(tmp_path, monkeypatch):
    """R29: a seat's schedule wakes its own session. agents.yaml can't know the card's id, so it
    writes {card}, and the rendering puts the card there, as it does for ``agent``."""
    r = _rendering(tmp_path, monkeypatch, {"units": [UNIT], "timezone": "UTC",
                                            "schedules": [OWN_SCHEDULE]})
    data = json.loads((tmp_path / "etc" / "pa_a" / "declaration.json").read_text())
    assert r.done == ["pa_a"]
    assert data["schedules"][0]["target"] == "Resident@1a2b3c"
