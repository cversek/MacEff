"""One transcript monitor per transcript, found in the process table (#529).

On a host where two agents shared a login, twelve monitors ran: five on one
agent's transcript, five on the other's current one, and two on transcripts of
sessions long ended. Every compaction was recorded four times. One pid file per
account stood for both agents, every monitor that exited deleted it, and each
monitor was a fork that kept the command line of the hook or command that
started it, so nothing could find the monitors the file had lost.

A monitor is now a process of its own; the process table says which run; each
serves one Claude Code process and ends with it; a second monitor on a
transcript gives way to the first.
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from subprocess import DEVNULL

import pytest

from macf.transcript_monitor import daemon
from macf.transcript_monitor.daemon import MonitorProcess

PROJECTS = Path("/home/u/.claude/projects")
A = PROJECTS / "-home-u-agent-a"   # two agents under one account
B = PROJECTS / "-home-u-agent-b"


def _m(pid, started, owner, transcript):
    return MonitorProcess(pid, float(started), owner, Path(transcript))


def _ended_pid():
    """A pid whose process has ended."""
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def _born(pid):
    """When *pid* started, from the process table. A monitor that serves it
    started later, so fixtures give monitors start times after this one."""
    started = daemon._process_started(pid)
    assert started is not None, f"the process table does not say when {pid} started"
    return started


PS_OUTPUT = """\
  101 Mon Sep 21 18:18:25 2026     /usr/bin/python3 -m macf.transcript_monitor --interval 1.0 --owner 4001 --transcript /home/u/.claude/projects/-home-u-agent-a/s1.jsonl
  102 Tue Oct  6 21:47:27 2026     /opt/py/bin/python3.10 -m macf.transcript_monitor --interval 0.5 --owner 0 --transcript /home/u/.claude/projects/-home-u-agent b/my session.jsonl
  103 Mon Aug 10 12:46:46 2026     /usr/bin/python3 /home/u/agent-a/.claude/hooks/session_start.py
  104 Mon Aug 10 12:46:46 2026     grep macf.transcript_monitor --transcript s1.jsonl
"""


def test_ps_names_each_monitor_with_its_owner_and_transcript():
    """A path with spaces survives ps joining the arguments; a hook, and a grep
    for the module's name, are not monitors."""
    found = daemon._parse_ps(PS_OUTPUT)
    assert [(m.pid, m.owner, str(m.transcript)) for m in found] == [
        (101, 4001, "/home/u/.claude/projects/-home-u-agent-a/s1.jsonl"),
        (102, 0, "/home/u/.claude/projects/-home-u-agent b/my session.jsonl"),
    ]
    assert found[0].started < found[1].started


def _proc_entry(proc, pid, argv, start_ticks=None):
    entry = proc / str(pid)
    entry.mkdir()
    (entry / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    if start_ticks is not None:
        # The command name may hold spaces and parentheses; the start time is
        # field 22, counted after its closing parenthesis.
        fields = ["S", "1"] + ["0"] * 17 + [str(start_ticks), "0"]
        (entry / "stat").write_text(f"{pid} (python3 (x)) {' '.join(fields)}\n")


def test_proc_gives_each_monitor_its_exact_arguments_and_start(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "self").mkdir()
    ticks = os.sysconf("SC_CLK_TCK")
    argv = [sys.executable, "-m", "macf.transcript_monitor", "--interval", "1.0",
            "--owner", "7", "--transcript", "/p/with space/t.jsonl"]
    _proc_entry(proc, 201, argv, 5 * ticks)
    _proc_entry(proc, 202, ["bash", "-c", "sleep 1"], 3)
    _proc_entry(proc, 203, argv)  # ended while being read: no stat left

    assert daemon._monitors_from_proc(proc) == [
        MonitorProcess(201, 5.0, 7, Path("/p/with space/t.jsonl"))]


def test_a_monitor_counts_only_for_its_own_transcript(monkeypatch):
    """The #529 case: another agent's monitor, or one on an older session of
    this agent, does not stand for this session's."""
    alive = os.getpid()
    t0 = _born(alive)
    monitors = [_m(301, t0 + 1, alive, B / "s9.jsonl"),   # another agent, same account
                _m(302, t0 + 2, alive, A / "s0.jsonl")]   # this agent, an earlier session
    monkeypatch.setattr(daemon, "find_monitors", lambda: monitors)
    assert daemon.is_running(A / "s1.jsonl") is False

    monitors.append(_m(303, t0 + 3, alive, A / "s1.jsonl"))
    assert daemon.is_running(A / "s1.jsonl") is True
    assert daemon.is_running(B / "s9.jsonl") is True


def test_an_unreadable_process_table_starts_nothing(monkeypatch):
    """Unknown is not 'none': starting blind is how duplicates were made."""
    monkeypatch.setattr(daemon, "find_monitors", lambda: None)
    assert daemon.is_running(A / "s1.jsonl") is True


def test_a_monitor_ends_with_its_claude_code_process(monkeypatch, tmp_path):
    gone = _ended_pid()
    monkeypatch.setattr(daemon, "find_monitors", lambda: [_m(401, 1, gone, A / "s1.jsonl")])
    assert daemon.is_running(A / "s1.jsonl") is False, "a monitor whose session ended still counted"

    transcript = tmp_path / "s1.jsonl"
    transcript.write_text("")
    monitor = daemon.TranscriptMonitor(transcript, poll_interval=0.01, owner=gone)
    loop = threading.Thread(target=monitor.run, daemon=True)
    loop.start()
    loop.join(timeout=5)
    if loop.is_alive():
        monitor.stop()
        pytest.fail("the monitor outlived its Claude Code process")
    assert monitor.stop_reason == f"its Claude Code process {gone} ended"


@pytest.mark.skipif(os.geteuid() == 0, reason="root may signal pid 1")
def test_a_pid_that_another_user_now_holds_is_not_the_owner():
    """The kernel reuses pids: one that answers with PermissionError belongs to
    someone else now, so the process recorded under it has ended (#490)."""
    assert daemon._alive(1) is False


def test_a_second_monitor_on_a_transcript_gives_way_to_the_first():
    alive, gone = os.getpid(), _ended_pid()
    t0 = _born(alive)
    t = A / "s1.jsonl"
    first, second = _m(501, t0 + 10, alive, t), _m(502, t0 + 20, alive, t)
    assert daemon._duplicate_of(502, t, [first, second]) == first
    assert daemon._duplicate_of(501, t, [first, second]) is None

    # Started in the same second: the pid decides, the same way from both sides.
    a, b = _m(503, t0 + 30, alive, t), _m(504, t0 + 30, alive, t)
    assert daemon._duplicate_of(504, t, [a, b]) == a
    assert daemon._duplicate_of(503, t, [a, b]) is None

    # An older monitor that no longer serves, or that watches another
    # transcript, is no reason to give way.
    assert daemon._duplicate_of(502, t, [_m(501, t0 + 10, gone, t), second]) is None
    assert daemon._duplicate_of(502, t, [_m(501, t0 + 10, alive, A / "s0.jsonl"), second]) is None


def test_a_younger_process_under_the_owners_pid_is_not_the_owner(monkeypatch):
    """The kernel reuses pids, also for the same user, whom `kill(pid, 0)`
    cannot tell apart. The owner started its monitor, so a process under the
    owner's pid that started after the monitor took the number later."""
    heir = subprocess.Popen(["sleep", "30"])  # stands in for the process that took the number
    try:
        born = _born(heir.pid)
        stuck = _m(601, born - 5, heir.pid, A / "s1.jsonl")   # started before its "owner"
        assert daemon._serving(stuck) is False
        monkeypatch.setattr(daemon, "find_monitors", lambda: [stuck])
        assert daemon.is_running(A / "s1.jsonl") is False, "a monitor counted for a stranger"

        assert daemon._serving(_m(602, born + 5, heir.pid, A / "s1.jsonl")) is True
    finally:
        heir.kill()
        heir.wait()


def test_without_a_start_time_the_pid_alone_decides(monkeypatch):
    """A process table that cannot say when the owner started must not stop a
    monitor that serves: unknown is not 'reused'."""
    monkeypatch.setattr(daemon, "_process_started", lambda pid: None)
    assert daemon._serving(_m(701, 1, os.getpid(), A / "s1.jsonl")) is True
    assert daemon._serving(_m(702, 1, _ended_pid(), A / "s1.jsonl")) is False


def test_the_process_table_says_when_a_process_started():
    """In order, from the real table on this platform; nothing for an ended one."""
    later = subprocess.Popen(["sleep", "30"])
    try:
        assert _born(later.pid) >= _born(os.getpid())
    finally:
        later.kill()
        later.wait()
    assert daemon._process_started(_ended_pid()) is None


def test_start_runs_a_fresh_interpreter_named_as_a_monitor(
        monkeypatch, tmp_path, capsys, no_transcript_monitor_started):
    monkeypatch.delenv(daemon.DISABLE_ENV)  # this test is about the real start path
    transcript = tmp_path / "s1.jsonl"
    transcript.write_text("")
    monkeypatch.setattr(daemon, "find_current_transcript", lambda: transcript)
    monkeypatch.setattr(daemon, "find_monitors", list)  # no monitors
    monkeypatch.setenv("CLAUDE_PID", "4242")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    assert daemon.start_daemon() == 0

    (argv, kwargs), = no_transcript_monitor_started
    assert argv == [sys.executable, "-m", "macf.transcript_monitor", "--interval", "1.0",
                    "--owner", "4242", "--transcript", str(transcript)]
    assert kwargs["start_new_session"] is True and kwargs["close_fds"] is True
    assert kwargs["stdin"] == DEVNULL and kwargs["stdout"] == DEVNULL
    assert kwargs["stderr"] not in (None, 2), "the monitor would hold the caller's stderr"
    out = capsys.readouterr()
    assert out.out == "", "the SessionStart hook's stdout must stay JSON"
    assert "Transcript Monitor started" in out.err


def test_every_event_a_monitor_writes_names_it(monkeypatch, tmp_path):
    emitted = []
    monkeypatch.setattr(daemon, "append_event", lambda name, data: emitted.append((name, data)))
    transcript = tmp_path / "s1.jsonl"
    transcript.write_text("")
    me = os.getpid()

    # Started second on a transcript another monitor serves: it records its
    # start and why it ended, and never runs. Its own owner has ended, so a
    # monitor that ran anyway would stop at once instead of hanging the suite.
    monkeypatch.setattr(daemon, "find_monitors",
                        lambda: [_m(11, 1, 0, transcript), _m(me, 2, 0, transcript)])
    assert daemon.run_monitor(transcript, owner=_ended_pid()) == 0
    assert [(name, data["pid"], data.get("reason")) for name, data in emitted] == [
        ("transcript_monitor_started", me, None),
        ("transcript_monitor_stopped", me, "monitor 11 already serves this transcript"),
    ]

    emitted.clear()
    daemon.TranscriptMonitor(transcript)._process_line(json.dumps(
        {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"trigger": "manual"}}))
    assert [(name, data["monitor_pid"]) for name, data in emitted] == [
        ("compact_boundary_detected", me)]


def test_the_switch_starts_nothing_even_with_a_transcript_and_no_monitor(
        monkeypatch, tmp_path, no_transcript_monitor_started):
    """MACF_TRANSCRIPT_MONITOR_DISABLED=1 returns before anything is looked up or spawned.

    The integration test that runs the SessionStart hook as a subprocess resolved
    the developer's live transcript and started a real monitor on it: patched names
    stay in the test process, and only the environment crosses into the hook's.
    """
    transcript = tmp_path / "s1.jsonl"
    transcript.write_text("")
    monkeypatch.setattr(daemon, "find_current_transcript", lambda: transcript)
    monkeypatch.setattr(daemon, "find_monitors", lambda: [])
    monkeypatch.setenv(daemon.DISABLE_ENV, "1")
    assert daemon.start_daemon() == 0
    assert no_transcript_monitor_started == []


def test_the_suite_sets_the_switch_where_a_subprocess_inherits_it():
    """Every test runs with the switch in os.environ, so a hook a test runs as a
    subprocess inherits it, whichever file starts that subprocess."""
    import os
    assert os.environ.get(daemon.DISABLE_ENV) == "1"
