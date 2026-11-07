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


def test_never_connecting_warns_once_after_the_startup_window(capsys):
    t = iter(range(0, 1000, 30))
    tunnel.supervise(_Child(exit_after=5, code=2), "127.0.0.1:20241", startup_s=60,
                     probe=lambda m: (False, "no edge connections"), sleep=lambda s: None,
                     clock=lambda: float(next(t)))
    err = capsys.readouterr().err
    assert err.count("not connected after 60 s") == 1


def test_main_refuses_a_missing_config_with_ex_config(tmp_path):
    assert tunnel.main(["--config", str(tmp_path / "none.yml")]) == 78


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
