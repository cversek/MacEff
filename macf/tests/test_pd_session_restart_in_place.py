"""The daemon restarts a session unit in its pane when the unit's wrapper can do that
(cversek/MacEff#726).

A wrapper that can respawn its session says so with ``pd_session_pane``, at its start and after
each respawn. For such a wrapper a restart is SIGUSR1 to the wrapper alone: the unit's process,
its tmux server and any attached client stay, and the respawn's announcement is the session's
new incarnation, reported as a restart (MIS-0002-R47). A wrapper that never announced is
restarted whole, as before, because SIGUSR1 would end it. One that announced but doesn't
report the respawn within the unit's stop grace is restarted whole too, and the record says why.
"""
import json
import os
import signal
import sys
import time

import pytest

from macf.agent_events_log import get_log_path, read_events
from macf.pd import core as pd_core
from macf.pd.interface import EVENT_SESSION_PANE, EVENT_STATE, Unit

from test_primal_daemon import CARD, MACF_SRC, ME, _crash, drive, make_core  # noqa: F401 - fixture

#: A stand-in for the session unit's wrapper: it announces its pane unless told not to, and
#: answers SIGUSR1 with a respawn's announcement unless told not to. One that does not announce
#: keeps SIGUSR1's default action, as a wrapper from before #726 does.
WRAPPER = r'''
import json, os, signal, sys, time
from macf.agent_events_log import append_event
from macf.notify.session import proc_start
spec = json.loads(sys.argv[1])
def say(n):
    append_event("pd_session_pane", {"agent": spec["agent"], "wrapper_pid": os.getpid(),
                 "wrapper_start": proc_start(os.getpid()), "pane_pid": 40000 + n, "respawns": n})
asked = []
if spec["announce"]:
    signal.signal(signal.SIGUSR1, lambda s, f: asked.append(True))
    say(0)
respawns, beat_at = 0, 0.0
while True:
    time.sleep(0.05)
    if time.monotonic() - beat_at > 0.5:      # liveness, as the session's monitor gives it
        beat_at = time.monotonic()
        append_event("pd_unit_alive", {"agent": spec["agent"], "unit": "session", "pid": os.getpid(),
                     "proc_start": proc_start(os.getpid()), "interval_s": 60})
    if asked:
        asked.clear()
        if spec["answer"]:
            respawns += 1
            say(respawns)
'''


@pytest.fixture
def wrapper(tmp_path):
    path = tmp_path / "wrapper.py"
    path.write_text(WRAPPER)
    return path


def _session(wrapper, *, announce=True, answer=True, stop_grace_s=1.0):
    env = {"MACF_EVENTS_LOG_PATH": str(get_log_path()), "PYTHONPATH": MACF_SRC}
    spec = json.dumps({"agent": CARD, "announce": announce, "answer": answer})
    return Unit(name="session", kind="session", command=[sys.executable, str(wrapper), spec],
                account=ME, restart="always", liveness_interval_s=60, memory_limit_mb=64,
                environment=env, stop_grace_s=stop_grace_s)


def _carried():
    return [e["data"] for e in read_events(reverse=False, scope="all", only=(pd_core.EVENT_CARRIED,))]


def _states():
    return [e["data"] for e in read_events(reverse=False, scope="all", only=(EVENT_STATE,))
            if e["data"].get("unit") == "session"]


def _announced(pid, respawns=0):
    return any(e["data"].get("wrapper_pid") == pid and e["data"].get("respawns") == respawns
               for e in read_events(reverse=False, scope="all", only=(EVENT_SESSION_PANE,)))


def test_an_announced_wrapper_restarts_its_session_in_place(make_core, wrapper):
    core = make_core([_session(wrapper)], hosted=lambda: [])
    core.boot()
    assert drive(core, lambda: core.state("session") == "running")
    pid = core.pid("session")
    assert drive(core, lambda: _announced(pid))
    before = core.session_incarnation_key()

    core.restart("session", pd_core.POLICY, "asked from the tray")
    assert drive(core, lambda: any(c["after"] == "the session restarted in its pane" for c in _carried()))
    assert core.pid("session") == pid, "the unit was restarted whole"
    assert core.state("session") == "running"
    assert core.session_incarnation() == before[:2], "the lineage root is still the unit's process"
    assert core.session_incarnation_key() != before, "a respawn is a new incarnation"
    assert any("in its pane" in s.get("reason", "") for s in _states())
    report = [c for c in _carried() if c["after"] == "the session restarted in its pane"][-1]
    assert report["changed"] == ["session"] and report["lost"] == [pd_core.CONTEXT_LOST]


def test_a_wrapper_that_never_announced_is_restarted_whole(make_core, wrapper):
    core = make_core([_session(wrapper, announce=False)], hosted=lambda: [])
    core.boot()
    assert drive(core, lambda: core.state("session") == "running")
    pid = core.pid("session")
    core.restart("session", pd_core.POLICY, "asked from the tray")
    assert drive(core, lambda: core.state("session") == "running" and core.pid("session") not in (None, pid))
    assert any(c["after"] == "the session unit restarted" for c in _carried())


def test_a_respawn_not_reported_within_the_grace_restarts_the_unit_whole(make_core, wrapper):
    core = make_core([_session(wrapper, answer=False, stop_grace_s=1.0)], hosted=lambda: [])
    core.boot()
    assert drive(core, lambda: core.state("session") == "running")
    pid = core.pid("session")
    assert drive(core, lambda: _announced(pid))
    core.restart("session", pd_core.POLICY, "asked from the tray")
    assert drive(core, lambda: core.state("session") == "running" and core.pid("session") not in (None, pid),
                 timeout=10)
    assert any("did not restart in its pane" in s.get("reason", "") for s in _states())


def test_a_daemon_that_adopted_the_wrapper_finds_its_announcement(make_core, wrapper):
    """The announcement came before this daemon's tail began, so it is read back from the log."""
    first = make_core([_session(wrapper)], hosted=lambda: [])
    first.record_start(os.getpid(), "the first daemon's start")
    first.boot()
    assert drive(first, lambda: first.state("session") == "running")
    pid = first.pid("session")
    assert drive(first, lambda: _announced(pid))
    left = _crash(first)
    try:
        second = make_core([_session(wrapper)], hosted=lambda: [])
        second.record_start(os.getpid(), "the second daemon's start")
        second.boot()
        assert drive(second, lambda: second.pid("session") == pid)
        second.restart("session", pd_core.POLICY, "asked from the tray")
        assert drive(second, lambda: _announced(pid, respawns=1))
        assert second.pid("session") == pid
    finally:
        for proc in left.values():
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
