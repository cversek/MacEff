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
    cfg = SimpleNamespace(agents={u: SimpleNamespace(username=u) for u in ("pa_a", "pa_b", "pa_c")})
    assert start.start_primal_daemons(cfg) == ["pa_b"]
    _wait_for(supervised)
    assert supervised == ["pa_b"]


def _rendering(tmp_path, monkeypatch, primal_daemon):
    start = _start()
    from macf.pd import names as pd_names
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path / "home")
    monkeypatch.setattr(pd_names, "agent_card", lambda home: "Resident@1a2b3c")
    (tmp_path / "home" / "pa_a").mkdir(parents=True)
    chowned = []
    cfg = SimpleNamespace(agents={"a": SimpleNamespace(username="pa_a", primal_daemon=primal_daemon)})
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
