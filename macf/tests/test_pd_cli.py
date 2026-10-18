"""``macf_tools pd status``: the daemon's answer when a daemon can be believed, the event
log's when not, and always which of the two it is."""
import json
import os
import pwd
import shutil
import socket
import tempfile
import threading
from pathlib import Path

import pytest

from macf.agent_events_log import append_event
from macf.cli import main
from macf.notify.session import proc_start
from macf.pd.client import status
from macf.pd.interface import (
    EVENT_LIVENESS,
    EVENT_STATE,
    DaemonRecord,
    Declaration,
    Unit,
    control_socket,
    declaration_path,
    record_path,
)

CARD = "Tester@abc123"
ME = pwd.getpwuid(os.getuid()).pw_name


def make_home(tmp_path, declared=True):
    """An agent home whose own files name it Tester@abc123, declaring one unit."""
    home = tmp_path / "home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text("abc123def4567890\n")
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"moniker": "Tester"}}))
    if declared:
        unit = Unit(name="worker", command=["true"], account=ME, restart="never",
                    liveness_interval_s=60, memory_limit_mb=64)
        path = declaration_path(home)
        path.parent.mkdir(parents=True)
        path.write_text(Declaration(version=1, agent=CARD, units=[unit]).model_dump_json())
    return home


@pytest.fixture
def base():
    """A runtime directory short enough for a socket path on every platform."""
    path = Path(tempfile.mkdtemp(prefix="pd-", dir="/tmp"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def answer_once(path, reply):
    """A stand-in daemon in this process: it answers one request on ``path`` with ``reply``."""
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)

    def run():
        with listener:
            conn, _ = listener.accept()
            with conn:
                if conn.recv(4096):  # a client that hangs up without asking gets nothing
                    conn.sendall(json.dumps(reply).encode() + b"\n")
    threading.Thread(target=run, daemon=True).start()


def record(base, pid, start):
    record_path(CARD, base).write_text(DaemonRecord(pid=pid, proc_start=start).model_dump_json())


RUNNING = {"ok": True, "units": [{"unit": "worker", "state": "running", "pid": 4321, "since": 1.0}]}


def test_status_from_a_daemon_that_checks_out(tmp_path, base):
    """A daemon whose record names this very process, answering on its socket, is believed."""
    record(base, os.getpid(), proc_start(os.getpid()))
    answer_once(control_socket(CARD, base), RUNNING)
    report = status(make_home(tmp_path), CARD, base=base)
    assert report.source == "daemon"
    assert [(u["unit"], u["state"]) for u in report.units] == [("worker", "running")]


def test_a_stale_record_is_not_believed(tmp_path, base):
    """A record whose pid is no longer the process it names sends the readout to the log."""
    record(base, os.getpid(), "not this process's start")
    report = status(make_home(tmp_path), CARD, base=base)
    assert report.source == "event log"
    assert "no longer" in report.why


def test_a_socket_answered_by_another_process_is_not_believed(tmp_path, base):
    """A live record is not enough: the process answering the socket must be the one it names."""
    parent = os.getppid()
    record(base, parent, proc_start(parent))
    answer_once(control_socket(CARD, base), RUNNING)  # answered by this process, not the parent
    report = status(make_home(tmp_path), CARD, base=base)
    assert report.source == "event log"
    assert f"answered by pid {os.getpid()}" in report.why


def test_status_from_the_log_when_no_daemon_answers(tmp_path, base):
    """With no daemon, each unit's last recorded state and its liveness verdict come from the log."""
    me = os.getpid()
    append_event(EVENT_STATE, {"agent": CARD, "unit": "worker", "state": "running", "pid": me,
                               "proc_start": proc_start(me), "reason": "its first liveness"})
    append_event(EVENT_LIVENESS, {"agent": CARD, "unit": "worker", "pid": me,
                                  "proc_start": proc_start(me), "interval_s": 60})
    # Another agent's unit of the same name, written later, is not this agent's.
    append_event(EVENT_STATE, {"agent": "Someone@fff000", "unit": "worker", "state": "failed",
                               "pid": me, "proc_start": proc_start(me), "reason": "not ours"})
    report = status(make_home(tmp_path), CARD, base=base)
    assert report.source == "event log"
    assert [(u["unit"], u["state"], u["liveness"]) for u in report.units] == [("worker", "running", "ALIVE")]


def test_no_declaration_means_no_daemon(tmp_path, base):
    """An agent with no declaration has no daemon to ask, and the readout says so without scanning."""
    report = status(make_home(tmp_path, declared=False), CARD, base=base)
    assert (report.source, report.units) == ("none", [])
    assert "no declaration" in report.why


def test_the_command_reports_its_source(tmp_path, monkeypatch, capsys):
    """``macf_tools pd status --json`` names the agent and where its answer came from."""
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(make_home(tmp_path)))
    with pytest.raises(SystemExit) as exited:
        main(["pd", "status", "--json"])
    assert exited.value.code == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (report["card"], report["source"]) == (CARD, "event log")


def test_the_command_shows_a_held_restart(tmp_path, monkeypatch, capsys):
    """A session's restart that a quiet window holds is shown with the window's end, so the
    operator reads that it waits, not that it happened (R50)."""
    from macf.pd import client
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(make_home(tmp_path)))
    unit = {"unit": "session", "state": "stopped", "since": 1.0, "restart_held_until": "07:00"}
    monkeypatch.setattr(client, "status", lambda home, card: client.StatusReport(
        card=card, source="daemon", why="its record and its socket agree", units=[unit]))
    with pytest.raises(SystemExit) as exited:
        main(["pd", "status"])
    assert exited.value.code == 0
    line = next(ln for ln in capsys.readouterr().out.splitlines() if "session:" in ln)
    assert line.startswith("  session: stopped")
    assert line.endswith("; restart held until 07:00 (quiet window)")


def test_a_wake_window_is_read_as_seconds_or_with_a_unit():
    from macf.pd.cli import _seconds
    assert [_seconds(t) for t in ("300", "90s", "5m", "1.5h")] == [300, 90, 300, 5400]
    for bad in ("0", "-5", "five", "5d", ""):
        with pytest.raises(ValueError):
            _seconds(bad)


def test_pd_wake_shows_or_paces_and_a_pace_needs_its_reason(monkeypatch, capsys):
    """pd wake alone asks for the status and says the window and where it came from; with a window
    it sends a pace asked by the agent, with its card; a pace needs a reason, and one window."""
    import argparse

    import macf.pd.client as client
    import macf.pd.daemon as daemon
    import macf.utils.paths as paths
    from macf.pd.cli import cmd_pd_wake
    from macf.pd.interface import Response
    sent = []
    monkeypatch.setattr(paths, "find_agent_home", lambda: Path("/nowhere"))
    monkeypatch.setattr(daemon, "card_for_home", lambda home: "Tester@abc123")
    monkeypatch.setattr(client, "ask", lambda card, request: sent.append(request) or Response(
        ok=True, wake_refractory_s=request.get("refractory_s") or 600.0, wake_window_from="the declaration"))

    def run(**kw):
        args = argparse.Namespace(**{"refractory": None, "declared": False, "reason": None,
                                     "asked_by": "agent", **kw})
        return cmd_pd_wake(args)

    assert run() == 0 and sent[-1] == {"op": "status"}
    assert "600 s" in capsys.readouterr().out
    assert run(refractory="5m") == 1 and len(sent) == 1, "a pace without a reason was sent"
    assert run(refractory="5m", declared=True, reason="r") == 1 and len(sent) == 1
    assert run(refractory="5m", reason="a busy hour") == 0
    assert sent[-1] == {"op": "pace", "refractory_s": 300.0, "reason": "a busy hour",
                        "asked_by": {"kind": "agent", "card": "Tester@abc123"}}
    assert run(declared=True, reason="done", asked_by="operator") == 0
    assert sent[-1]["refractory_s"] is None and sent[-1]["asked_by"] == {"kind": "operator"}
