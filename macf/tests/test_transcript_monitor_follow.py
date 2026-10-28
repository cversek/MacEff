"""The transcript monitor as a declared unit of the agent's primal daemon.

Follow mode (``python -m macf.transcript_monitor --follow``) follows the agent's live session,
announced by the SessionStart hook, and moves to the next one instead of exiting; it beats its
own unit's liveness, and the session unit's while it follows a session that runs as one. Where
the declaration names such a unit, no ad-hoc start site starts a monitor of its own.
"""
import argparse
import json
import os
import pwd
import subprocess
import sys
import time

import pytest

from macf.agent_events_log import append_event, get_log_path
from macf.notify.session import proc_start
from macf.pd import liveness as lv
from macf.pd.monitor_unit import MONITOR_MODULE, declared_monitor_unit
from macf.transcript_monitor import daemon

CARD = "Resident@1a2b3c"


def _identify(home):
    (home / ".maceff").mkdir(parents=True, exist_ok=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Resident"}}))
    (home / ".maceff_primary_agent.id").write_text("1a2b3c4d-0000\n")
    return home


def _declare_monitor(home, name="monitor"):
    """A declaration, the one the daemon reads, with a unit that runs the follow-mode monitor."""
    _identify(home)
    path = home / ".maceff" / "pd" / "declaration.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "agent": CARD, "units": [{
        "name": name, "command": [sys.executable, "-m", MONITOR_MODULE, "--follow"],
        "account": pwd.getpwuid(os.getuid()).pw_name, "restart": "always",
        "liveness_interval_s": 30, "memory_limit_mb": 128}]}))


def _announce(transcript, owner, session_unit=None):
    data = {"session_id": transcript.stem, "transcript": str(transcript), "owner": owner,
            "owner_start": proc_start(owner)}
    if session_unit:
        data["session_unit"] = session_unit
    append_event(daemon.EVENT_SESSION_ANNOUNCED, data)


def _transcript(tmp_path, name):
    path = tmp_path / f"{name}.jsonl"
    path.write_text("")
    return path


@pytest.fixture
def quiet(monkeypatch):
    """No per-session monitor runs beside the follower, and a beat goes nowhere real."""
    monkeypatch.setattr(daemon, "find_monitors", list)


def _sleeper(follower, after, then=None):
    """A sleep that stops the follower once it has waited *after* times, running *then* first."""
    count = []

    def sleep(_s):
        count.append(1)
        if then is not None and len(count) == 1:
            then()
        if len(count) >= after:
            follower.stop("test done")
    return sleep


def test_the_module_named_in_a_unit_is_the_monitors_module():
    assert MONITOR_MODULE == daemon.MONITOR_MODULE


def test_follow_moves_to_a_new_transcript_when_another_session_is_announced(tmp_path, monkeypatch, quiet):
    a, b = _transcript(tmp_path, "a"), _transcript(tmp_path, "b")
    _announce(a, os.getpid())
    runs = []

    def fake_run(self, start_from_end=True):
        runs.append((self.jsonl_path, self.owner))
        if len(runs) == 1:
            _announce(b, os.getppid())          # a restart: a new transcript and a new process
            self.on_pass()
            assert not self.running or self.stop_reason, "the monitor on a was not told to stop"
        else:
            follower.stop("test done")

    monkeypatch.setattr(daemon.TranscriptMonitor, "run", fake_run)
    follower = daemon.Follower(0.01, environ={}, sleep=lambda s: follower.stop("no session"))
    follower.run()
    assert runs == [(a, os.getpid()), (b, os.getppid())]


def test_a_compaction_reannouncing_the_same_session_does_not_restart_the_monitor(tmp_path, monkeypatch, quiet):
    a = _transcript(tmp_path, "a")
    _announce(a, os.getpid())
    stopped = []

    def fake_run(self, start_from_end=True):
        _announce(a, os.getpid())
        self.on_pass()
        stopped.append(self.stop_reason)
        follower.stop("test done")

    monkeypatch.setattr(daemon.TranscriptMonitor, "run", fake_run)
    follower = daemon.Follower(0.01, environ={}, sleep=lambda s: None)
    follower.run()
    assert stopped == [None]


def test_follow_waits_for_the_next_session_when_its_owner_ends(tmp_path, monkeypatch, quiet):
    a, b = _transcript(tmp_path, "a"), _transcript(tmp_path, "b")
    owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        _announce(a, owner.pid)
        runs = []

        def fake_run(self, start_from_end=True):
            runs.append(self.jsonl_path)
            if len(runs) == 1:                   # the session's process ends, as the loop sees it
                owner.kill()
                owner.wait()
                self.stop(f"its Claude Code process {self.owner} ended")
            else:
                follower.stop("test done")

        monkeypatch.setattr(daemon.TranscriptMonitor, "run", fake_run)
        follower = daemon.Follower(0.01, environ={})
        follower.sleep = _sleeper(follower, after=50, then=lambda: _announce(b, os.getpid()))
        assert follower.run() == 0
        assert runs == [a, b], "the follower exited, or never moved to the next session"
        assert follower.stop_reason == "test done"
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait()


def test_follow_beats_its_own_unit_while_it_waits(tmp_path, monkeypatch, quiet, isolated_agent_home):
    _identify(isolated_agent_home)
    beats = []
    monkeypatch.setattr(lv, "append_event", lambda n, d: beats.append(d) or True)
    env = {lv.ENV_UNIT: "monitor", lv.ENV_INTERVAL: "0.02", lv.ENV_HOME: str(isolated_agent_home)}
    follower = daemon.Follower(0.01, environ=env)
    waits = []

    def sleep(s):
        waits.append(1)
        time.sleep(0.03)
        if len(waits) >= 5:
            follower.stop("test done")

    follower.sleep = sleep
    follower.run()
    assert beats and all(b["unit"] == "monitor" and b["pid"] == os.getpid() for b in beats)


def test_follow_beats_the_session_unit_of_the_session_it_follows(tmp_path, monkeypatch, quiet,
                                                                   isolated_agent_home):
    _identify(isolated_agent_home)
    beats = []
    monkeypatch.setattr(lv, "append_event", lambda n, d: beats.append(d) or True)
    wrapper = os.getppid()
    a = _transcript(tmp_path, "a")
    _announce(a, os.getpid(), session_unit={"unit": "session", "interval_s": 0.05, "pid": wrapper,
                                             "proc_start": proc_start(wrapper)})

    def fake_run(self, start_from_end=True):
        for _ in range(3):
            self.on_pass()
            time.sleep(0.08)
        follower.stop("test done")

    monkeypatch.setattr(daemon.TranscriptMonitor, "run", fake_run)
    follower = daemon.Follower(0.01, environ={lv.ENV_HOME: str(isolated_agent_home)}, sleep=lambda s: None)
    follower.run()
    assert any(b["unit"] == "session" and b["pid"] == wrapper for b in beats), beats


def test_follow_defers_to_a_per_session_monitor_on_the_same_transcript(tmp_path, monkeypatch):
    a = _transcript(tmp_path, "a")
    _announce(a, os.getpid())
    old = daemon.MonitorProcess(pid=999999, started=0, owner=0, transcript=a)
    reads = []
    monkeypatch.setattr(daemon, "find_monitors", lambda: reads.append(1) or ([old] if len(reads) <= 3 else []))
    ran_after = []

    def fake_run(self, start_from_end=True):
        ran_after.append(len(reads))
        follower.stop("test done")

    monkeypatch.setattr(daemon.TranscriptMonitor, "run", fake_run)
    follower = daemon.Follower(0.01, environ={}, sleep=lambda s: None)
    follower.run()
    assert ran_after == [4], "the follower ran beside the old monitor, or never took over"


def test_the_hook_announces_instead_of_starting_when_a_unit_is_declared(monkeypatch, isolated_agent_home,
                                                                         no_transcript_monitor_started):
    from macf.hooks import handle_session_start as hook
    _declare_monitor(isolated_agent_home)
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    monkeypatch.setattr(daemon, "is_running", lambda *a: False)
    started = []
    monkeypatch.setattr(daemon, "start_daemon", lambda *a, **k: started.append(1) or 0)
    hook.run(json.dumps({"session_id": "s" * 36, "transcript_path": "/tmp/x/" + "s" * 36 + ".jsonl"}))
    assert started == []
    said = [json.loads(l)["data"] for l in get_log_path().read_text().splitlines()
            if json.loads(l)["event"] == daemon.EVENT_SESSION_ANNOUNCED]
    assert len(said) == 1 and said[0]["owner"] == os.getpid()
    assert said[0]["transcript"] == "/tmp/x/" + "s" * 36 + ".jsonl"


def test_the_announcement_carries_the_session_unit_the_session_runs_as(tmp_path, isolated_agent_home):
    """What the follower beats for: the wrapper named in the session's own environment."""
    _identify(isolated_agent_home)
    env = {"CLAUDE_PID": str(os.getpid()), lv.ENV_HOME: str(isolated_agent_home),
           lv.ENV_SESSION_UNIT: "session", lv.ENV_SESSION_INTERVAL: "60", lv.ENV_SESSION_PID: str(os.getppid())}
    t = _transcript(tmp_path, "s" * 36)
    assert daemon.announce_session({"session_id": t.stem, "transcript_path": str(t)}, environ=env)
    event = [json.loads(l) for l in get_log_path().read_text().splitlines()][-1]
    session = daemon.AnnouncedSession.from_event(event)
    assert session.session_env({lv.ENV_HOME: str(isolated_agent_home)})[lv.ENV_SESSION_PID] == str(os.getppid())


def test_the_hook_starts_a_monitor_as_before_without_a_declared_unit(monkeypatch, isolated_agent_home):
    from macf.hooks import handle_session_start as hook
    monkeypatch.setattr(daemon, "is_running", lambda *a: False)
    started = []
    monkeypatch.setattr(daemon, "start_daemon", lambda *a, **k: started.append(1) or 0)
    hook.run(json.dumps({"session_id": "s" * 36}))
    assert started == [1]


@pytest.mark.parametrize("declared", [True, False])
def test_task_creation_leaves_the_monitor_to_a_declared_unit(monkeypatch, isolated_agent_home, declared):
    from macf.task import create
    if declared:
        _declare_monitor(isolated_agent_home)
    monkeypatch.setattr(daemon, "is_running", lambda *a: False)
    started = []
    monkeypatch.setattr(daemon, "start_daemon", lambda *a, **k: started.append(1) or 0)
    ok = create._verify_tm_running()
    assert started == ([] if declared else [1])
    assert ok is declared    # declared: the unit runs it; not: the patched check still reads down


def test_start_daemon_itself_starts_nothing_when_a_unit_is_declared(tmp_path, monkeypatch, isolated_agent_home,
                                                                     no_transcript_monitor_started):
    """The backstop for every other caller (AUTO_MODE entry, ensure_running)."""
    _declare_monitor(isolated_agent_home)
    monkeypatch.delenv(daemon.DISABLE_ENV)
    monkeypatch.setattr(daemon, "is_running", lambda *a: False)
    monkeypatch.setattr(daemon, "find_current_transcript", lambda: _transcript(tmp_path, "t"))
    assert daemon.start_daemon() == 0
    assert no_transcript_monitor_started == []


def test_cli_start_refuses_naming_the_unit_and_pd_status(monkeypatch, isolated_agent_home, capsys,
                                                          no_transcript_monitor_started):
    from macf import cli
    _declare_monitor(isolated_agent_home, name="tm-follow")
    assert cli._cmd_tm_start(argparse.Namespace(foreground=False, interval=1.0)) == 1
    err = capsys.readouterr().err
    assert "'tm-follow'" in err and "macf_tools pd status" in err
    assert no_transcript_monitor_started == []


def test_a_declaration_without_the_monitor_declares_none(isolated_agent_home):
    assert declared_monitor_unit(isolated_agent_home) is None          # no declaration at all
    _declare_monitor(isolated_agent_home)
    assert declared_monitor_unit(isolated_agent_home) == "monitor"


def _another_start(pid):
    """A start time one tick (or second) away from *pid*'s real one: a different incarnation."""
    from macf.notify.session import proc_start_from_key, proc_start_key
    return proc_start_from_key(proc_start_key(proc_start(pid)) + 1)


def test_a_resume_on_the_same_transcript_under_a_new_process_moves_to_the_new_owner(tmp_path, monkeypatch, quiet):
    a = _transcript(tmp_path, "a")
    _announce(a, os.getpid())
    runs = []

    def fake_run(self, start_from_end=True):
        runs.append(self.owner)
        if len(runs) == 1:
            _announce(a, os.getppid())          # resumed: same conversation, new client process
            self.on_pass()
        else:
            follower.stop("test done")

    monkeypatch.setattr(daemon.TranscriptMonitor, "run", fake_run)
    follower = daemon.Follower(0.01, environ={}, sleep=lambda s: follower.stop("no session"))
    follower.run()
    assert runs == [os.getpid(), os.getppid()]


def test_no_session_beat_for_a_wrapper_whose_start_does_not_match(tmp_path, isolated_agent_home):
    wrapper = os.getppid()
    session = daemon.AnnouncedSession("s", tmp_path / "s.jsonl", os.getpid(), proc_start(os.getpid()),
                                      {"unit": "session", "interval_s": 60, "pid": wrapper,
                                       "proc_start": _another_start(wrapper)})
    assert session.session_env({lv.ENV_HOME: str(isolated_agent_home)}) == {}


def test_a_partly_written_announcement_is_read_once_it_is_whole(tmp_path):
    log = tmp_path / "events.jsonl"
    log.write_text("")
    tail = daemon._AnnouncementTail(log)
    line = json.dumps({"event": daemon.EVENT_SESSION_ANNOUNCED,
                       "data": {"session_id": "s", "transcript": str(tmp_path / "s.jsonl"), "owner": 42}})
    half = len(line) // 2
    with open(log, "a") as f:
        f.write(line[:half])
    assert tail.poll() is None
    with open(log, "a") as f:
        f.write(line[half:] + "\n")
    got = tail.poll()
    assert got is not None and got.owner == 42


def test_a_partial_line_after_a_whole_one_is_kept_for_the_next_poll(tmp_path):
    """A poll that finds one whole announcement and the start of another takes the first and
    keeps its place before the second, so the second is read once it is whole."""
    log = tmp_path / "events.jsonl"
    log.write_text("")
    tail = daemon._AnnouncementTail(log)

    def line(owner):
        return json.dumps({"event": daemon.EVENT_SESSION_ANNOUNCED,
                           "data": {"session_id": f"s{owner}", "transcript": str(tmp_path / f"s{owner}.jsonl"),
                                    "owner": owner}})

    second = line(43)
    with open(log, "a") as f:
        f.write(line(42) + "\n" + second[:len(second) // 2])
    first = tail.poll()
    assert first is not None and first.owner == 42
    with open(log, "a") as f:
        f.write(second[len(second) // 2:] + "\n")
    got = tail.poll()
    assert got is not None and got.owner == 43


def test_a_recycled_client_pid_is_not_live(tmp_path):
    me = os.getpid()
    assert daemon.AnnouncedSession("s", tmp_path / "s.jsonl", me, proc_start(me)).live()
    assert not daemon.AnnouncedSession("s", tmp_path / "s.jsonl", me, _another_start(me)).live()
