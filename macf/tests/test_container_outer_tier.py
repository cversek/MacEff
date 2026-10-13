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


def test_only_agents_with_a_declaration_get_a_daemon(tmp_path, monkeypatch):
    start = _start()
    monkeypatch.setattr(start, "HOME_ROOT", tmp_path)
    for user in ("pa_a", "pa_b"):
        (tmp_path / user).mkdir()
    decl = tmp_path / "pa_b" / start.PD_DECLARATION
    decl.parent.mkdir(parents=True)
    decl.write_text(json.dumps({"units": []}))
    supervised = []
    monkeypatch.setattr(start, "supervise_primal_daemon", lambda user, home: supervised.append(user))
    cfg = SimpleNamespace(agents={"a": SimpleNamespace(username="pa_a"), "b": SimpleNamespace(username="pa_b")})
    assert start.start_primal_daemons(cfg) == ["pa_b"]
    import time
    for _ in range(50):
        if supervised:
            break
        time.sleep(0.01)
    assert supervised == ["pa_b"]


def test_primal_daemons_start_after_access_and_before_optional_units():
    """R57: the access path first; the daemons before the optional units (policy index,
    search service), in run_after_access's order."""
    src = START_PY.read_text()
    at = {name: src.index(f'("{name}",') for name in
          ("MACF tools", "agent initialization", "amail", "primal daemons", "policy index", "search service")}
    assert at["agent initialization"] < at["primal daemons"] < at["policy index"] < at["search service"]
