"""The inbound receiver and its tunnel as supervised units: alive means working, and start-up says
which daemon runs each, refusing a configured receiver that nothing runs (MIS-0004 R31, R32)."""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from macf.amail.daemons import tunnel

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"
VENV_PY = "/opt/maceff-venv/bin/python"


# --------------------------------------------------------------------------- tunnel readiness

def _serve(status, body):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"127.0.0.1:{srv.server_address[1]}"


@pytest.mark.parametrize("status,body,expect", [
    (200, {"status": 200, "readyConnections": 4}, True),
    (200, {"status": 200, "readyConnections": 0}, False),
    (503, {"status": 503, "readyConnections": 0}, False),
    (200, {"unexpected": True}, False),
])
def test_ready_means_an_edge_connection(status, body, expect):
    srv, addr = _serve(status, body)
    try:
        ok, why = tunnel.ready(addr)
        assert ok is expect, why
    finally:
        srv.shutdown()


def test_ready_is_false_when_nothing_listens():
    ok, why = tunnel.ready("127.0.0.1:1")
    assert not ok and "unreachable" in why


@pytest.fixture
def proxied(monkeypatch):
    """A proxy in the environment that refuses every connection. urlopen builds its default opener
    once and reads the proxy variables then, so drop any opener cached before they were set."""
    import urllib.request
    for k in ("http_proxy", "HTTP_PROXY"):
        monkeypatch.setenv(k, "http://127.0.0.1:9")
    for k in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(urllib.request, "_opener", None)


def test_ready_asks_loopback_directly_even_with_a_proxy_set(proxied):
    """A unit environment carrying http_proxy must not turn a connected tunnel into an
    unreachable one: urlopen sends http:// through the proxy, loopback included."""
    srv, addr = _serve(200, {"status": 200, "readyConnections": 2})
    try:
        assert tunnel.ready(addr) == (True, "2 edge connection(s)")
    finally:
        srv.shutdown()


def test_the_receiver_probe_asks_loopback_directly_even_with_a_proxy_set(proxied, monkeypatch):
    """Through a proxy every probe would fail, and three failures make the receiver exit: a
    restart loop while the server was fine."""
    from macf.amail.daemons import receiver
    monkeypatch.setattr(receiver, "log_event", lambda e: None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), receiver.IngestHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}{receiver.HEALTH_PATH}"
        assert receiver.probe_health(url) is True
    finally:
        srv.shutdown()


class _Child:
    def __init__(self, exit_after, code):
        self.polls, self.exit_after, self.code = 0, exit_after, code

    def poll(self):
        self.polls += 1
        return self.code if self.polls > self.exit_after else None


def test_supervise_ticks_only_when_connected_and_exits_with_the_child(capsys):
    answers = iter([(False, "no edge connections"), (True, "2 edge connection(s)"),
                    (True, "2 edge connection(s)"), (False, "/ready answered 503")])
    ticks = []
    code = tunnel.supervise(_Child(exit_after=4, code=1), "x", startup_s=60,
                            tick=lambda: ticks.append(1), probe=lambda m: next(answers),
                            sleep=lambda s: None, clock=lambda: 0.0)
    assert code == 1
    assert len(ticks) == 2                      # only the two ready answers
    out, err = capsys.readouterr()
    assert "amail tunnel connected: 2 edge connection(s)" in out
    assert "lost its edge connections" in err and "exited with 1" in err


def test_a_clean_child_exit_is_still_a_failure():
    """A tunnel that stops has stopped carrying mail, whatever its exit code says."""
    assert tunnel.supervise(_Child(0, 0), "x", 60, probe=lambda m: (True, ""),
                            sleep=lambda s: None) == 1


def test_a_cloudflared_killed_by_a_signal_exits_as_a_shell_reports_it(capsys):
    """Popen gives a signal death as a negative code, and exiting -15 would read as 241."""
    assert tunnel.supervise(_Child(0, -15), "x", 60, probe=lambda m: (True, ""),
                            sleep=lambda s: None) == 143
    assert "killed by signal 15" in capsys.readouterr().err


def test_never_connecting_warns_once_after_the_startup_window(capsys):
    t = iter(range(0, 1000, 30))
    tunnel.supervise(_Child(exit_after=5, code=2), "127.0.0.1:20241", startup_s=60,
                     probe=lambda m: (False, "no edge connections"), sleep=lambda s: None,
                     clock=lambda: float(next(t)))
    err = capsys.readouterr().err
    assert err.count("not connected after 60 s") == 1


def test_main_refuses_a_missing_config_with_ex_config(tmp_path):
    assert tunnel.main(["--config", str(tmp_path / "none.yml")]) == 78


@pytest.mark.parametrize("metrics, loopback", [
    ("127.0.0.1:20241", True), ("[::1]:20241", True),
    ("0.0.0.0:20241", False), ("192.168.1.5:20241", False), ("localhost:20241", False),
])
def test_a_metrics_address_off_loopback_is_refused(tmp_path, capsys, metrics, loopback):
    """The metrics server answers anyone who can reach it, so it stays on loopback by
    construction. A loopback address gets past this check to the missing config's refusal."""
    assert tunnel.main(["--config", str(tmp_path / "none.yml"), "--metrics", metrics]) == 78
    assert ("not a loopback IP address" in capsys.readouterr().err) is (not loopback)


# --------------------------------------------------------------------------- receiver

def test_the_env_file_fills_gaps_and_never_overrides(tmp_path):
    from macf.amail.daemons.receiver import load_env_file
    f = tmp_path / "receiver.env"
    f.write_text("# comment\nINGEST_AUD=from-file\nINGEST_TEAM_DOMAIN=team.example\n\nBROKEN\n")
    env = {"INGEST_AUD": "from-declaration"}
    assert load_env_file(f, env) == 1
    assert env == {"INGEST_AUD": "from-declaration", "INGEST_TEAM_DOMAIN": "team.example"}
    assert load_env_file(tmp_path / "absent.env", env) == 0


def test_health_is_answered_and_not_logged_while_other_gets_are_refused(monkeypatch):
    from macf.amail.daemons import receiver
    logged = []
    monkeypatch.setattr(receiver, "log_event", logged.append)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), receiver.IngestHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert receiver.probe_health(base + receiver.HEALTH_PATH) is True
        assert logged == []
        assert receiver.probe_health(base + "/") is False      # 405, refused and logged
        assert [e["code"] for e in logged] == [405]
    finally:
        srv.shutdown()


# --------------------------------------------------------------------------- start-up check

def _start():
    spec = importlib.util.spec_from_file_location("maceff_start_ingest_units", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unit(name, module, account):
    return {"name": name, "command": [VENV_PY, "-m", module], "account": account,
            "restart": "always", "liveness_interval_s": 60, "memory_limit_mb": 256}


def _cfg(services):
    from macf.models.agent_spec import AgentsConfig
    return AgentsConfig.model_validate({"ids": {"base": 21000}, "agents": {}, "subagents": {},
                                        "services": services})


@pytest.fixture
def start(tmp_path, monkeypatch):
    s = _start()
    logs = []
    monkeypatch.setattr(s, "log", logs.append)
    monkeypatch.setattr(s, "RECEIVER_ENV", tmp_path / "receiver.env")
    monkeypatch.setattr(s, "TUNNEL_CONFIG", tmp_path / "config.yml")
    s.logs = logs
    return s


def test_declared_units_are_named_and_started_by_nothing_here(start):
    (start.RECEIVER_ENV).write_text("INGEST_AUD=x\n")
    (start.TUNNEL_CONFIG).write_text("tunnel: x\n")
    start._check_inbound_units(_cfg({
        "amail_ingest": {"calling_card": "AmailIngest", "primal_daemon": {
            "units": [_unit("receiver", "macf.amail.daemons.receiver", "amail_ingest")]}},
        "amail_tunnel": {"calling_card": "AmailTunnel", "primal_daemon": {
            "units": [_unit("tunnel", "macf.amail.daemons.tunnel", "amail_tunnel")]}}}))
    joined = "\n".join(start.logs)
    assert "declared unit amail_ingest/receiver" in joined
    assert "declared unit amail_tunnel/tunnel" in joined
    assert "⚠️" not in joined


def test_a_placed_receiver_env_with_no_unit_refuses_the_start(start):
    start.RECEIVER_ENV.write_text("INGEST_AUD=x\n")
    with pytest.raises(RuntimeError, match="macf.amail.daemons.receiver"):
        start._check_inbound_units(_cfg({}))


def test_a_receiver_declared_on_another_account_refuses_the_start(start):
    """The receiver owns the ingest spool and log. On any other account it would fail later, at
    their permissions, so the start-up check refuses it by name."""
    with pytest.raises(RuntimeError, match="ingest account amail_ingest"):
        start._check_inbound_units(_cfg({
            "amail_tunnel": {"calling_card": "AmailTunnel", "primal_daemon": {
                "units": [_unit("receiver", "macf.amail.daemons.receiver", "amail_tunnel")]}}}))


def test_a_tunnel_config_with_no_unit_is_announced_not_silent(start):
    start.TUNNEL_CONFIG.write_text("tunnel: x\n")
    start._check_inbound_units(_cfg({}))
    joined = "\n".join(start.logs)
    assert "none configured (no receiver.env)" in joined
    assert "⚠️" in joined and "macf.amail.daemons.tunnel" in joined


def test_nothing_configured_says_so_for_each(start):
    start._check_inbound_units(_cfg({}))
    assert any("receiver: none configured" in l for l in start.logs)
    assert any("tunnel: none configured (deployment choice)" in l for l in start.logs)


# --------------------------------------------------------------------------- review round 1

def test_a_requested_stop_is_a_clean_exit(capsys):
    """SIGTERM from the daemon is a stop, not a failure, in the exit code and in the log."""
    code = tunnel.supervise(_Child(exit_after=1, code=143), "x", 60, probe=lambda m: (True, ""),
                            sleep=lambda s: None, stopping=lambda: True)
    assert code == 0
    assert "stopped on request" in capsys.readouterr().out


def test_receiver_exits_when_its_server_thread_dies():
    from macf.amail.daemons.receiver import watch_health
    alive = iter([True, True, False])
    ticks = []
    assert watch_health(lambda: next(alive), lambda: True, lambda: ticks.append(1),
                        lambda s: None, 0) == 1
    assert len(ticks) == 2


def test_receiver_exits_after_consecutive_failed_probes_and_a_success_resets_the_count():
    from macf.amail.daemons.receiver import watch_health
    answers = [False, False, True, False, False, False]
    asked = []

    def probe():
        asked.append(1)
        return answers[len(asked) - 1]
    ticks = []
    assert watch_health(lambda: True, probe, lambda: ticks.append(1),
                        lambda s: None, 0, failures_to_exit=3) == 1
    assert len(ticks) == 1
    # The success reset the count: the exit comes on the sixth probe, three failures after it,
    # not on the fourth, which a count carried across the success would give.
    assert len(asked) == 6


def test_importing_the_receiver_reads_no_env_file(tmp_path, monkeypatch):
    import importlib
    import os
    f = tmp_path / "receiver.env"
    f.write_text("INGEST_AUD=from-file\n")
    monkeypatch.setenv("AMAIL_INGEST_ENV_FILE", str(f))
    monkeypatch.delenv("INGEST_AUD", raising=False)
    from macf.amail.daemons import receiver
    importlib.reload(receiver)
    assert "INGEST_AUD" not in os.environ and receiver.AUD == ""


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="PR_SET_PDEATHSIG")
def test_a_killed_wrapper_takes_cloudflared_with_it(tmp_path):
    """The child is started with die_with_parent, so SIGKILL on the wrapper ends it too."""
    import os
    import signal
    import subprocess
    import sys
    import time
    pidfile = tmp_path / "child.pid"
    wrapper = subprocess.Popen([sys.executable, "-c", (
        "import os, subprocess, sys, time\n"
        "from macf.amail.daemons.tunnel import die_with_parent\n"
        "w = os.getpid()\n"
        "c = subprocess.Popen(['sleep', '60'], preexec_fn=lambda: die_with_parent(w))\n"
        f"open({str(pidfile)!r}, 'w').write(str(c.pid))\n"
        "time.sleep(60)\n")], env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    for _ in range(100):
        if pidfile.exists() and pidfile.read_text():
            break
        time.sleep(0.05)
    child = int(pidfile.read_text())
    wrapper.send_signal(signal.SIGKILL)
    wrapper.wait()
    for _ in range(100):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        # A dead child the init process has not reaped yet still answers; read its state.
        try:
            if open(f"/proc/{child}/stat").read().split(")")[-1].split()[0] == "Z":
                break
        except OSError:
            break
        time.sleep(0.05)
    else:
        os.kill(child, signal.SIGKILL)
        pytest.fail("the child outlived its killed parent")


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="PR_SET_PDEATHSIG")
@pytest.mark.parametrize("parent_is_wrapper, status", [(True, 0), (False, 1)])
def test_a_child_whose_wrapper_already_died_does_not_start(monkeypatch, parent_is_wrapper, status):
    """The death signal only covers a wrapper that dies after it is set. A child whose parent is
    no longer the wrapper that started it must exit before exec, not run as an orphan."""
    import os
    wrapper = os.getpid() if parent_is_wrapper else 1
    pid = os.fork()
    if pid == 0:
        try:
            tunnel.die_with_parent(wrapper)
        finally:
            os._exit(0)
    _, raw = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(raw) == status


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="PR_SET_PDEATHSIG")
def test_a_process_that_forks_after_import_still_starts_its_tunnel():
    """The wrapper's pid is read when cloudflared starts, not when the module is imported: a
    process that imported it and forked before starting would otherwise see the parent check
    stop every child before exec."""
    import os
    import shutil
    pid = os.fork()
    if pid == 0:
        code = 99
        try:
            code = tunnel.start(shutil.which("true"), "unused.yml", "127.0.0.1:1").wait()
        finally:
            os._exit(code)
    _, raw = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(raw) == 0
