"""The search service as a primal daemon unit: run in the foreground, beat liveness from
before the model loads, end on SIGTERM; and the start sites stand aside when a unit
declares it. No real model is loaded: a fake retriever stands in."""
import importlib.util
import json
import os
import signal
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from macf.search_service import daemon as sd
from macf.search_service.retrievers.base import AbstractRetriever, SearchResult

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"


class FakeHeartbeat:
    def __init__(self):
        self.ticks = 0
        self.stopped = False

    def tick(self):
        self.ticks += 1

    def stop(self):
        self.stopped = True


class FakeRetriever(AbstractRetriever):
    namespace = "policy"

    def __init__(self, on_warmup=None):
        self.on_warmup = on_warmup or (lambda: None)
        self.warmed = False

    def warmup(self):
        self.on_warmup()
        self.warmed = True

    def search(self, query, limit=5):
        return SearchResult(formatted=f"found:{query}")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _query(port, text, deadline_s=10.0):
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2) as c:
                c.sendall((json.dumps({"namespace": "policy", "query": text}) + "\n").encode())
                return json.loads(c.makefile().readline())
        except OSError:
            time.sleep(0.05)
    raise AssertionError("the service never answered")


def _bounded(get_service, after_s=8.0):
    """Clear a service's running flag after *after_s*, and keep clearing it, so a defect that
    leaves the serve loop running ends the test as a failure instead of hanging the suite."""
    done = threading.Event()

    def run():
        if done.wait(after_s):
            return
        while not done.wait(0.2):
            service = get_service()
            if service is not None:
                service.running = False
    threading.Thread(target=run, daemon=True).start()
    return done


@pytest.fixture
def unit_env(tmp_path, monkeypatch):
    """No fork may happen; the pid file goes to tmp; signal handlers are restored after."""
    def no_fork():
        raise AssertionError("a unit must never fork")
    monkeypatch.setattr(os, "fork", no_fork)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    yield tmp_path
    for s, h in saved.items():
        signal.signal(s, h)


def test_unit_beats_before_the_load_and_during_it(unit_env):
    beat = FakeHeartbeat()
    seen = {}

    def warmup():
        seen["at_load_start"] = beat.ticks
        time.sleep(1.4)           # a slow cold start: the load ticker must vouch for it
        seen["at_load_end"] = beat.ticks
        os.kill(os.getpid(), signal.SIGTERM)   # stop as soon as it would serve

    service = sd.SearchService(port=_free_port()).register(FakeRetriever(warmup))
    guard = _bounded(lambda: service)
    started = time.monotonic()
    assert service.run_as_unit(beat) == 0
    guard.set()
    assert time.monotonic() - started < 6, "SIGTERM did not end the unit"
    assert seen["at_load_start"] >= 1, "no beat before the model load"
    assert seen["at_load_end"] > seen["at_load_start"], "no beat while the model loads"


def test_unit_serves_on_its_port_beats_per_pass_and_sigterm_ends_it(unit_env):
    beat = FakeHeartbeat()
    port = _free_port()
    service = sd.SearchService(port=port).register(FakeRetriever())
    answers = {}

    def client():
        answers["reply"] = _query(port, "hello")
        answers["ticks"] = beat.ticks
        time.sleep(1.2)                     # at least one idle pass of the serve loop
        answers["ticks_later"] = beat.ticks
        os.kill(os.getpid(), signal.SIGTERM)
    t = threading.Thread(target=client, daemon=True)
    t.start()
    started = time.monotonic()
    code = service.run_as_unit(beat)
    t.join(5)
    assert code == 0 and time.monotonic() - started < 15
    assert answers["reply"]["formatted"] == "found:hello"
    assert answers["ticks_later"] > answers["ticks"], "the serve loop does not tick per pass"
    assert beat.stopped
    assert not (unit_env / sd.PID_FILE_NAME).exists()      # cleaned up on SIGTERM


def test_sigterm_during_the_load_exits_cleanly_without_serving(unit_env):
    def warmup():
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(5)
        raise AssertionError("the load went on after SIGTERM")
    service = sd.SearchService(port=_free_port()).register(FakeRetriever(warmup))
    guard = _bounded(lambda: service)
    started = time.monotonic()
    try:
        assert service.run_as_unit(FakeHeartbeat()) == 0
    finally:
        guard.set()
    assert time.monotonic() - started < 3


def test_a_taken_port_fails_fast_before_the_load_and_says_how_to_free_it(unit_env, capsys):
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    try:
        retriever = FakeRetriever()
        service = sd.SearchService(port=holder.getsockname()[1]).register(retriever)
        assert service.run_as_unit(FakeHeartbeat()) == 1
    finally:
        holder.close()
    assert not retriever.warmed, "the model loaded before the port was known to be free"
    assert "macf_tools search-service stop" in capsys.readouterr().err


def test_the_load_ticker_gives_up_on_a_load_that_hangs():
    ticks = []
    ticker = sd._LoadTicker(lambda: ticks.append(1), period_s=0.01, limit_s=0.1).start()
    time.sleep(0.4)
    count = len(ticks)
    time.sleep(0.2)
    ticker.stop()
    assert 0 < count == len(ticks), "a hung load must stop the beats"


def test_main_unit_flag_runs_in_the_foreground_with_the_env_heartbeat(unit_env, monkeypatch):
    import macf.pd.liveness as liveness
    import macf.search_service.retrievers.policy_retriever as pr
    beat = FakeHeartbeat()
    monkeypatch.setattr(liveness, "heartbeat_from_env", lambda: beat)
    monkeypatch.setattr(pr, "PolicyRetriever",
                        lambda: FakeRetriever(lambda: os.kill(os.getpid(), signal.SIGTERM)))
    monkeypatch.setattr(sd.SearchService, "_daemonize",
                        lambda self: (_ for _ in ()).throw(AssertionError("daemonized")))
    made = []
    real_init = sd.SearchService.__init__
    monkeypatch.setattr(sd.SearchService, "__init__",
                        lambda self, *a, **kw: (made.append(self), real_init(self, *a, **kw))[1])
    guard = _bounded(lambda: made[0] if made else None)
    started = time.monotonic()
    assert sd.main(["--unit", "--port", str(_free_port())]) == 0
    guard.set()
    assert time.monotonic() - started < 6, "SIGTERM did not end the unit"
    assert beat.ticks >= 1 and beat.stopped


# ---- start sites ----

def _start():
    spec = importlib.util.spec_from_file_location("maceff_start_search_unit", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEARCH_UNIT = {"name": "search", "command": ["/opt/maceff-venv/bin/python", "-m",
                                             "macf.search_service.daemon", "--unit"],
               "account": "pa_a", "restart": "always", "liveness_interval_s": 60,
               "memory_limit_mb": 2048}


@pytest.mark.parametrize("where", ["agent", "service"])
def test_start_py_starts_none_when_a_unit_declares_the_search_service(where, monkeypatch):
    start = _start()
    ran, logged = [], []
    monkeypatch.setattr(start.subprocess, "run", lambda *a, **kw: ran.append(a))
    monkeypatch.setattr(start, "log", logged.append)
    monkeypatch.setattr(start, "service_home", lambda name: Path("/var/lib") / name)
    body = {"units": [SEARCH_UNIT]}
    cfg = SimpleNamespace(
        agents={"a": SimpleNamespace(username="pa_a", primal_daemon=body if where == "agent" else None)},
        services={"searcher": SimpleNamespace(primal_daemon=body, calling_card="S")} if where == "service" else {})
    start.start_search_service_daemon(cfg)
    assert ran == []
    assert any("unit 'search'" in line and "starts none" in line for line in logged), logged


def test_start_py_starts_the_daemon_as_before_when_none_is_declared(monkeypatch):
    start = _start()
    ran = []
    monkeypatch.setattr(start.subprocess, "run",
                        lambda argv, **kw: ran.append(argv) or SimpleNamespace(returncode=0, stderr=""))
    monkeypatch.setattr(start, "log", lambda *a: None)
    other = {"units": [{**SEARCH_UNIT, "name": "broker", "command": ["python", "-m", "macf.amail.daemons.broker"]}]}
    cfg = SimpleNamespace(agents={"a": SimpleNamespace(username="pa_a", primal_daemon=other)}, services={})
    start.start_search_service_daemon(cfg)
    assert len(ran) == 1 and ran[0][:2] == ["su", "-"] and "macf.search_service.daemon --daemon" in ran[0][-1]


# ---- the CLI ----

def _declare(root: Path, account: str, units):
    d = root / account
    d.mkdir(parents=True)
    (d / "declaration.json").write_text(json.dumps({"agent": "SomeAgent", "units": units}))


def test_cli_start_refuses_when_a_unit_declares_it_and_names_pd_status(tmp_path, monkeypatch, capsys):
    import macf.pd.names as names
    from macf import cli
    monkeypatch.setattr(names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path / "home"))
    _declare(tmp_path / "etc", "pa_b", [SEARCH_UNIT])
    import macf.search_service as ss
    monkeypatch.setattr(ss, "SearchService",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("started anyway")))
    assert cli.cmd_search_service_start(SimpleNamespace(port=_free_port(), daemon=True)) == 1
    err = capsys.readouterr().err
    assert "macf_tools pd status" in err and "'search'" in err


def test_cli_start_goes_on_as_before_when_nothing_declares_it(tmp_path, monkeypatch, capsys):
    import macf.pd.names as names
    from macf import cli
    import macf.search_service as ss
    monkeypatch.setattr(names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path / "home"))
    _declare(tmp_path / "etc", "pa_b", [{**SEARCH_UNIT, "command": ["python", "-m", "macf.amail.daemons.broker"]}])
    monkeypatch.setattr(ss, "is_service_running", lambda: True)   # stops it at the next check
    assert cli.cmd_search_service_start(SimpleNamespace(port=_free_port(), daemon=True)) == 1
    out = capsys.readouterr()
    assert "already running" in out.out and "pd status" not in out.err


def test_status_reports_a_service_that_answers_on_the_port_without_a_pid_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(sd, "port_answers", lambda *a, **kw: True)
    status = sd.get_service_status()
    assert status["running"] is True and status["pid"] is None and "pd status" in status["note"]
