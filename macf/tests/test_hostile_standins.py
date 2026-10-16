"""The hostile stand-ins resist the way they say they do (``tests/hostile.py``, idea 405).

A stand-in that dies on the first signal tests nothing, so each one is checked here against
the stop it is meant to beat before any supervision test leans on it.
"""
import os
import signal
import subprocess
import time

from hostile import alive


def _start(argv):
    """A stand-in started as a supervisor starts a unit: in a process group of its own."""
    return subprocess.Popen(argv, start_new_session=True)


def _gone(pid, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and alive(pid):
        time.sleep(0.05)
    return not alive(pid)


def test_ignores_term_survives_term_and_hup(hostile):
    argv = hostile.ignores_term()
    proc = _start(argv)
    pid = hostile.pid(argv)
    assert pid == proc.pid
    for sig in (signal.SIGTERM, signal.SIGHUP):
        os.killpg(proc.pid, sig)
    time.sleep(0.3)
    assert alive(pid), "a TERM-ignoring stand-in that dies on TERM tests nothing"


def test_leaves_a_child_in_the_group_when_its_leader_dies(hostile):
    """The shape a stop that waits only for the leader misses (#656, #671)."""
    argv = hostile.leaves_a_child()
    proc = _start(argv)
    child = hostile.pid(argv)
    assert child != proc.pid and os.getpgid(child) == proc.pid
    os.killpg(proc.pid, signal.SIGTERM)
    proc.wait(timeout=5)                                   # the leader is gone...
    time.sleep(0.2)
    assert alive(child) and os.getpgid(child) == proc.pid  # ...and its group lives on


def test_a_leader_can_leave_on_its_own(hostile):
    argv = hostile.leaves_a_child(leader_for=0.3)
    proc = _start(argv)
    child = hostile.pid(argv)
    assert proc.wait(timeout=5) == 0
    assert alive(child)


def test_own_session_escapes_the_group(hostile):
    argv = hostile.own_session()
    proc = _start(argv)
    child = hostile.pid(argv)
    assert os.getsid(child) == child and os.getpgid(child) != proc.pid
    os.killpg(proc.pid, signal.SIGKILL)                    # a group SIGKILL does not reach it
    proc.wait(timeout=5)
    time.sleep(0.2)
    assert alive(child)


def test_zombie_lingers_while_its_parent_lives(hostile):
    argv = hostile.zombie()
    proc = _start(argv)
    child = hostile.pid(argv)
    time.sleep(0.3)
    os.kill(child, 0)                                      # the number answers a signal 0...
    assert not alive(child)                                # ...but the process has ended
    assert proc.poll() is None


def test_teardown_leaves_nothing_running(hostile):
    """What a failing test would leave is killed: leaders, children, escapees."""
    pids = []
    for argv in (hostile.ignores_term(), hostile.leaves_a_child(), hostile.own_session()):
        proc = _start(argv)
        pids += [proc.pid, hostile.pid(argv)]
    hostile.cleanup()
    assert all(_gone(pid) for pid in pids)


def test_teardown_never_kills_a_number_someone_else_now_holds(hostile, monkeypatch):
    """A pid is killed only while it is the process that reported it, by its start."""
    import hostile as module
    argv = hostile.ignores_term()
    proc = _start(argv)
    pid = hostile.pid(argv)
    try:
        # Only the start lookup is patched, never os.kill: a test failing here must still
        # leave the fixture's teardown a real kill.
        monkeypatch.setattr(module, "proc_start", lambda p: "a later process")
        hostile.cleanup()
        time.sleep(0.2)
        assert alive(pid), "teardown killed a process whose start no longer matched"
    finally:
        monkeypatch.undo()
        os.killpg(proc.pid, signal.SIGKILL)
    assert _gone(pid)
