"""The session unit: an agent's session as a unit its primal daemon parents.

MIS-0002-R12 (pd_MUST_start_units_itself): the wrapper keeps the tmux server, and the
session in it, as its own children, so the daemon that started the wrapper sees the
unit end when the session does. MIS-0002-R14 (unit_MUST_emit_liveness_events): the
session's transcript monitor reports the unit's liveness, naming the wrapper's pid.
MIS-0002-R100 (attach_MUST_resolve_from_pd): attach finds the session unit's pane on its
own server.
"""
import json
import os
import shutil
import signal
import stat
import time
from pathlib import Path

import pytest

from macf.pd import liveness as lv
from macf.pd import session_unit as su
from macf.pd.interface import EVENT_LIVENESS, Liveness
from macf.utils.attach import TMUX, plan_attach

needs_tmux = pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")


def _home(tmp_path, name="Resident", uuid="1a2b3c4d-0000"):
    (tmp_path / ".maceff").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": name}}))
    (tmp_path / ".maceff_primary_agent.id").write_text(uuid + "\n")
    return tmp_path


def _unit_env(home, **over):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home),
           lv.ENV_HOME: str(home), lv.ENV_UNIT: "session", lv.ENV_INTERVAL: "30"}
    env.update(over)
    return env


@pytest.fixture
def short_base():
    """A runtime directory short enough for a socket path: pytest's own is not."""
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="su-", dir="/tmp"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def restore_signals():
    saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    yield
    for s, h in saved.items():
        signal.signal(s, h)


# --- the session's environment -----------------------------------------------------

def test_the_session_gets_the_units_identity_under_its_own_names(tmp_path):
    env = su.session_environment(_unit_env(tmp_path, TMUX="/tmp/x,1,0"), 4321, tmp_path / "t.tmux")
    assert env[lv.ENV_SESSION_UNIT] == "session"
    assert env[lv.ENV_SESSION_INTERVAL] == "30"
    assert env[lv.ENV_SESSION_PID] == "4321"
    assert env["TMUX_TMPDIR"] == str(tmp_path / "t.tmux")
    # the unit's own names are gone, so no process the session starts reports as the unit,
    # and an outer tmux the wrapper was started from does not leak in
    assert lv.ENV_UNIT not in env and lv.ENV_INTERVAL not in env and "TMUX" not in env


def test_without_a_declared_unit_there_is_no_session_liveness_to_hand_on(tmp_path):
    env = su.session_environment({"HOME": str(tmp_path)}, 4321, tmp_path / "t.tmux")
    assert lv.ENV_SESSION_PID not in env and lv.ENV_SESSION_UNIT not in env


def test_the_proxy_attaches_only_when_it_answers():
    assert su.proxy_environment(8019, probe=lambda url: False) == {}
    on = su.proxy_environment(8019, probe=lambda url: True)
    # one assignment: a base URL without the first-party flag silently costs the long window
    assert on == {"ANTHROPIC_BASE_URL": "http://localhost:8019",
                  "_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL": "1"}


def test_a_tmux_directory_open_to_others_is_refused(tmp_path):
    d = tmp_path / "open.tmux"
    d.mkdir(mode=0o755)
    d.chmod(0o755)
    with pytest.raises(PermissionError):
        su._private_dir(d)
    assert stat.S_IMODE(su._private_dir(tmp_path / "new.tmux").stat().st_mode) == 0o700


# --- liveness from the transcript monitor ------------------------------------------

def test_the_monitor_reads_the_session_unit_and_its_pid(tmp_path):
    home = _home(tmp_path)
    found = lv.session_unit_from_env({lv.ENV_HOME: str(home), lv.ENV_SESSION_UNIT: "session",
                                      lv.ENV_SESSION_INTERVAL: "30", lv.ENV_SESSION_PID: "4321"})
    assert (found.card, found.unit, found.interval_s, found.pid) == ("Resident@1a2b3c", "session", 30.0, 4321)
    assert lv.session_unit_from_env({lv.ENV_HOME: str(home)}) is None


def test_a_partial_session_setting_gives_no_liveness(tmp_path, capsys):
    home = _home(tmp_path)
    for broken in ({lv.ENV_SESSION_UNIT: "session", lv.ENV_SESSION_INTERVAL: "30"},
                   {lv.ENV_SESSION_UNIT: "session", lv.ENV_SESSION_INTERVAL: "30", lv.ENV_SESSION_PID: "1"},
                   {lv.ENV_SESSION_UNIT: "session", lv.ENV_SESSION_INTERVAL: "x", lv.ENV_SESSION_PID: "4321"}):
        assert lv.session_unit_from_env({lv.ENV_HOME: str(home), **broken}) is None, broken
    assert "no session liveness" in capsys.readouterr().err


def test_a_session_beat_names_the_units_pid_not_the_monitors(tmp_path):
    events = []
    hb = lv.Heartbeat("Resident@1a2b3c", "session", 0.05,
                      append=lambda n, d: events.append((n, d)) or True, pid=os.getppid()).start()
    hb.tick()
    deadline = time.monotonic() + 2
    while not events and time.monotonic() < deadline:
        time.sleep(0.01)
    hb.stop()
    name, data = events[0]
    live = Liveness.model_validate(data)
    assert name == EVENT_LIVENESS and live.unit == "session"
    assert live.pid == os.getppid() != os.getpid()


def test_the_monitor_beats_once_per_pass_for_the_session_unit(tmp_path, monkeypatch, restore_signals):
    from macf.transcript_monitor import daemon

    home = _home(tmp_path)
    for k, v in {lv.ENV_HOME: str(home), lv.ENV_SESSION_UNIT: "session",
                 lv.ENV_SESSION_INTERVAL: "0.05", lv.ENV_SESSION_PID: str(os.getppid())}.items():
        monkeypatch.setenv(k, v)
    beats = []
    monkeypatch.setattr(lv, "append_event", lambda n, d: beats.append(d) or True)
    monkeypatch.setattr(daemon, "append_event", lambda *a, **k: True)
    monkeypatch.setattr(daemon, "find_monitors", lambda: [])
    passes = []

    def fake_run(self, start_from_end=True):
        # three passes of the loop, then the session ends
        for _ in range(3):
            self.on_pass()
            passes.append(1)
            time.sleep(0.08)

    monkeypatch.setattr(daemon.TranscriptMonitor, "run", fake_run)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("")
    daemon.run_monitor(transcript, 0.01, owner=0)
    assert len(passes) == 3
    assert beats and all(b["pid"] == os.getppid() and b["unit"] == "session" for b in beats)
    # once the loop has ended, no further beat
    n = len(beats)
    time.sleep(0.2)
    assert len(beats) == n


def test_the_loop_calls_on_pass_each_pass(tmp_path):
    from macf.transcript_monitor.daemon import TranscriptMonitor

    transcript = tmp_path / "t.jsonl"
    transcript.write_text("")
    import threading
    calls = []
    mon = TranscriptMonitor(transcript, poll_interval=0.01, detectors=[],
                            on_pass=lambda: calls.append(1) if len(calls) < 4 else mon.stop("enough"))
    # a bound, so a loop that never calls on_pass fails here instead of hanging the suite
    threading.Timer(3.0, mon.stop, args=("timed out",)).start()
    mon.run()
    assert mon.stop_reason == "enough" and len(calls) == 4


# --- the wrapper itself, with a real tmux ------------------------------------------

def _child(tmp_path, body):
    script = tmp_path / "child.sh"
    script.write_text("#!/bin/bash\n" + body)
    script.chmod(0o755)
    return script


@needs_tmux
def test_the_session_runs_under_the_wrapper_and_ends_it(tmp_path, short_base, restore_signals):
    """The server is the wrapper's child, the session the server's, and the wrapper
    returns when the session ends: the daemon sees the unit end with the session."""
    out = tmp_path / "chain.txt"
    child = _child(tmp_path, f"""
p=$$; chain=""
while [ "$p" -gt 1 ]; do chain="$chain $p"; p=$(ps -o ppid= -p $p | tr -d ' '); done
echo "$chain" > {out}
env | grep -E '^(MACF_PD_|TMUX_TMPDIR=)' | sort >> {out}
exit 0
""")
    base = short_base
    rc = su.run("Resident_1a2b3c", child, environ=_unit_env(tmp_path), base=base, ready_timeout=10)
    assert rc == 0
    text = out.read_text()
    chain = text.splitlines()[0].split()
    assert str(os.getpid()) in chain, "the session does not descend from the wrapper"
    assert f"{lv.ENV_SESSION_PID}={os.getpid()}" in text
    assert f"{lv.ENV_SESSION_UNIT}=session" in text
    assert f"{lv.ENV_UNIT}=" not in text
    assert f"TMUX_TMPDIR={base / 'Resident_1a2b3c.tmux'}" in text
    # the server is gone with the session (asked through the unit's own environment, which
    # drops an outer TMUX: tmux follows TMUX over TMUX_TMPDIR, so a test run inside a tmux
    # session would otherwise ask that session's server)
    import subprocess
    env = su.client_environment("Resident_1a2b3c", base)
    assert env is None or subprocess.run(["tmux", "has-session"], env=env,
                                         capture_output=True).returncode != 0


@needs_tmux
def test_a_server_already_serving_the_agent_is_not_doubled(tmp_path, short_base, restore_signals):
    import subprocess
    base = short_base
    d = su._private_dir(su.tmux_dir("Resident_1a2b3c", base))
    env = {**os.environ, "TMUX_TMPDIR": str(d)}
    env.pop("TMUX", None)
    subprocess.run(["tmux", "-f", "/dev/null", "new-session", "-d", "-s", "other", "sleep 30"], env=env, check=True)
    try:
        rc = su.run("Resident_1a2b3c", _child(tmp_path, "exit 0\n"), environ=_unit_env(tmp_path), base=base)
        assert rc == su.EXIT_NOT_STARTED
    finally:
        subprocess.run(["tmux", "kill-server"], env=env)


def test_a_missing_project_directory_starts_nothing(tmp_path, capsys):
    base = tmp_path / "rt"
    rc = su.run("Resident_1a2b3c", tmp_path / "child.sh", project_dir=tmp_path / "gone",
                environ=_unit_env(tmp_path), base=base)
    assert rc == su.EXIT_NOT_STARTED
    assert not su.tmux_dir("Resident_1a2b3c", base).exists()
    assert "different conversation" in capsys.readouterr().err


def test_a_socket_path_too_long_for_the_kernel_starts_nothing(tmp_path, capsys):
    base = tmp_path / ("x" * 120)
    rc = su.run("Resident_1a2b3c", tmp_path / "child.sh", environ=_unit_env(tmp_path), base=base)
    assert rc == su.EXIT_NOT_STARTED
    assert "longer than" in capsys.readouterr().err
    assert not base.exists()


# --- attach -------------------------------------------------------------------------

def test_attach_finds_the_session_units_pane_on_its_own_server():
    resp = {"ok": True, "units": [{"unit": "session", "state": "running", "pid": 500,
                                   "proc_start": "x", "since": 0.0}]}
    chains = {500: [500, 400, 1], 700: [700, 600, 500, 400]}    # pane 700 descends from the unit

    def panes(env=None):
        return {700: "Resident_1a2b3c"} if env and env.get("TMUX_TMPDIR") == "/rt/R.tmux" else {}

    plan = plan_attach(resp, "session", read_info=lambda pid: None, verify=lambda pid, s: True,
                       ancestors=lambda pid: chains.get(pid, [pid]), tmux_panes=panes,
                       tmux_tmpdir="/rt/R.tmux")
    assert plan.kind == TMUX
    assert plan.argv == ["env", "TMUX_TMPDIR=/rt/R.tmux", "tmux", "attach", "-t", "=Resident_1a2b3c", "-d"]
    # without the unit's directory, nothing to attach to: no fallback to a name
    plain = plan_attach(resp, "session", read_info=lambda pid: None, verify=lambda pid, s: True,
                        ancestors=lambda pid: chains.get(pid, [pid]), tmux_panes=panes)
    assert plain.kind != TMUX
