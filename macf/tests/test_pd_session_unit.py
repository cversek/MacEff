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


# --- inject from inside a session unit ------------------------------------------------

def test_inside_a_session_unit_inject_targets_its_own_pane(monkeypatch):
    from macf import supervisor as sv
    monkeypatch.setenv(lv.ENV_SESSION_PID, "4321")
    monkeypatch.setenv("TMUX", "/run/x/R.tmux/tmux-1000/default,99,0")
    monkeypatch.setenv("TMUX_PANE", "%3")
    assert sv._own_session_unit_pane() == "pane:%3"
    monkeypatch.delenv(lv.ENV_SESSION_PID)
    assert sv._own_session_unit_pane() is None, "a legacy pane is the supervisor's to resolve"


def test_inject_without_a_supervisor_types_into_the_session_units_pane(monkeypatch):
    from macf import supervisor as sv
    monkeypatch.setenv(lv.ENV_SESSION_PID, "4321")
    monkeypatch.setenv("TMUX", "/run/x/R.tmux/tmux-1000/default,99,0")
    monkeypatch.setenv("TMUX_PANE", "%3")
    monkeypatch.setattr(sv, "_find_own_supervisor", lambda: None)
    monkeypatch.setattr(sv, "_tmux_available", lambda: True)
    monkeypatch.setattr(sv, "_record_keys_sent", lambda *a: None)
    followed = []
    monkeypatch.setattr(sv, "_start_compact_followup", lambda target, text: followed.append(target))
    import macf.stop_bypass
    monkeypatch.setattr(macf.stop_bypass, "arm", lambda c: None)
    import macf.agent_events_log
    monkeypatch.setattr(macf.agent_events_log, "append_event", lambda *a, **k: True)
    calls = []

    class _Done:
        returncode = 0

    monkeypatch.setattr(sv.subprocess, "run", lambda argv, **k: calls.append(argv) or _Done())
    assert sv.send_slash_to_self("compact", then="resume") == 0
    assert calls[0] == ["tmux", "send-keys", "-t", "%3", "-l", "--", "/compact"]
    assert calls[1] == ["tmux", "send-keys", "-t", "%3", "Enter"]
    # the follow-up types into the same pane
    assert followed == ["pane:%3"]


# --- an outside stop reaches the session's own process group ---------------------------

@needs_tmux
def test_a_stop_of_the_unit_also_stops_a_session_that_ignores_the_hangup(tmp_path, short_base):
    """tmux runs each pane in a process group of its own, so the daemon's stop of the unit's
    group reaches the session only through the server's SIGHUP. A session that ignores it, and
    SIGTERM too, must still be gone before the wrapper returns (MIS-0002-R48), or a restart
    would start a second session beside it. CTB's probe on #652, as a test."""
    import subprocess
    import sys
    pidfile = tmp_path / "child.pid"
    child = _child(tmp_path, f"trap '' HUP TERM\necho $$ > {pidfile}\nsleep 300\n")
    code = (
        "import sys; from pathlib import Path; from macf.pd import session_unit as su; "
        f"sys.exit(su.run('Resident_1a2b3c', Path({str(child)!r}), environ={_unit_env(tmp_path)!r}, "
        f"base=Path({str(short_base)!r})))"
    )
    env = {k: v for k, v in os.environ.items() if k != "TMUX"}
    wrapper = subprocess.Popen([sys.executable, "-c", code], env=env, start_new_session=True)
    deadline = time.monotonic() + 15
    while not (pidfile.exists() and pidfile.read_text().strip()) and time.monotonic() < deadline:
        time.sleep(0.1)
    stand_in = int(pidfile.read_text())
    os.killpg(wrapper.pid, signal.SIGTERM)          # the daemon's stop: the unit's group
    assert wrapper.wait(timeout=30) == 0
    assert not _alive(stand_in), "the session outlived its unit"


def _alive(pid: int) -> bool:
    """Running, not a zombie waiting to be reaped."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[0]
    except (OSError, IndexError):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    return state != "Z"


def test_reaping_a_group_escalates_to_sigkill(tmp_path):
    import subprocess
    p = subprocess.Popen(["bash", "-c", "trap '' TERM; sleep 300"], start_new_session=True)
    time.sleep(0.2)
    t0 = time.monotonic()
    assert su.reap_group(os.getpgid(p.pid), grace=0.5)
    assert time.monotonic() - t0 < 5
    p.wait(timeout=5)


def test_without_proc_a_zombie_group_counts_as_gone(monkeypatch):
    """Where there is no /proc (macOS), ``ps`` lists the members, and a killed child of
    ours, a zombie until we wait for it, does not keep its group alive."""
    import subprocess
    real_path = su.Path
    monkeypatch.setattr(su, "Path", lambda p: real_path("/nonexistent-proc") if p == "/proc"
                        else real_path(p))
    p = subprocess.Popen(["bash", "-c", "trap '' TERM; sleep 300"], start_new_session=True)
    time.sleep(0.2)
    pgid = os.getpgid(p.pid)
    assert su._group_alive(pgid)
    assert su.reap_group(pgid, grace=0.5)   # p is not waited for until here: a zombie
    p.wait(timeout=5)


def test_a_pane_read_before_its_setsid_still_gets_its_own_group(monkeypatch):
    """tmux's pane child calls setsid() just after the fork. Read in between, it still has the
    server's group, which is the unit's own; the group recorded must be the pane's, not
    nothing, or a stop has no group to reap (seen in CI on a loaded runner)."""
    own, pane = 4000, 4242
    answers = iter([own, own, pane])                 # before setsid, then after
    monkeypatch.setattr(su.os, "getpgid", lambda pid: next(answers))
    assert su.pane_group(pane, own, timeout=1.0) == pane
    monkeypatch.setattr(su.os, "getpgid", lambda pid: own)   # setsid never seen in time
    assert su.pane_group(pane, own, timeout=0.05) == pane


def test_a_pane_already_gone_has_no_group(monkeypatch):
    def gone(pid):
        raise ProcessLookupError(pid)
    monkeypatch.setattr(su.os, "getpgid", gone)
    assert su.pane_group(4242, 4000, timeout=0.05) is None
