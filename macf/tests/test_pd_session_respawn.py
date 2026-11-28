"""A restart of the session unit restarts the session in its pane and keeps its tmux server
(cversek/MacEff#726).

The unit is the session, not the server. A restart that ended the server ended every client
attached to it, and an operator's iTerm2 window in control mode crashed with it. The wrapper
now restarts the session in place on SIGUSR1: the pane stays while the old session is reaped
by the same SIGTERM-then-SIGKILL reap the unit's own end uses, so two sessions never run on
one conversation, and then the pane runs the session again. Each pane it starts is announced
as a ``pd_session_pane`` event. The first, at start, is also what tells the daemon that this
wrapper can respawn; a wrapper that never announced is restarted whole, as before, because
SIGUSR1 would end it.
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from macf.agent_events_log import read_events
from macf.pd import session_unit as su
from macf.pd.interface import EVENT_SESSION_PANE

from test_pd_session_unit import _alive, _child, _unit_env, needs_tmux, short_base

AGENT = "Resident_1a2b3c"


def _wrapper(tmp_path, child, base):
    code = (
        "import sys; from pathlib import Path; from macf.pd import session_unit as su; "
        f"sys.exit(su.run({AGENT!r}, Path({str(child)!r}), environ={_unit_env(tmp_path)!r}, "
        f"base=Path({str(base)!r})))"
    )
    env = {k: v for k, v in os.environ.items() if k != "TMUX"}
    return subprocess.Popen([sys.executable, "-c", code], env=env, start_new_session=True)


def _wait_for(predicate, timeout, what):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


def _pids(path: Path):
    return [int(p) for p in path.read_text().split()] if path.exists() else []


def _panes():
    return [e for e in read_events(only=(EVENT_SESSION_PANE,)) if e.get("event") == EVENT_SESSION_PANE]


def _tmux_out(base, *args):
    env = su.client_environment(AGENT, base)
    return subprocess.run(["tmux", *args], env=env, capture_output=True, text=True).stdout.strip()


def _end(wrapper, pids_file):
    try:
        os.killpg(wrapper.pid, signal.SIGTERM)
        wrapper.wait(timeout=30)
    except ProcessLookupError:
        pass
    for pid in _pids(pids_file):
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


@needs_tmux
def test_a_respawn_keeps_the_server_and_its_attached_client(tmp_path, short_base):
    pids = tmp_path / "pids"
    child = _child(tmp_path, f"trap '' HUP\necho $$ >> {pids}\nsleep 300\n")
    wrapper = _wrapper(tmp_path, child, short_base)
    client = None
    try:
        _wait_for(lambda: _pids(pids), 15, "the first session")
        first_event = _wait_for(lambda: _panes(), 5, "the wrapper's announcement")[-1]
        assert first_event["data"]["wrapper_pid"] == wrapper.pid
        assert first_event["data"]["respawns"] == 0
        server = _tmux_out(short_base, "display-message", "-p", "#{pid}")
        # An attached client in control mode, as iTerm2 attaches.
        client = subprocess.Popen(["tmux", "-C", "attach", "-t", f"={AGENT}"],
                                  env=su.client_environment(AGENT, short_base),
                                  stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        assert client.poll() is None, "the client did not attach"

        os.kill(wrapper.pid, signal.SIGUSR1)
        _wait_for(lambda: len(_pids(pids)) == 2, 20, "the respawned session")
        first, second = _pids(pids)
        _wait_for(lambda: not _alive(first), 5, "the old session to end")
        assert _tmux_out(short_base, "display-message", "-p", "#{pid}") == server, "the server was replaced"
        assert client.poll() is None, "the attached client did not survive the restart"
        assert wrapper.poll() is None, "the unit ended"
        last = _wait_for(lambda: [e for e in _panes() if e["data"]["respawns"] == 1], 5,
                         "the respawn's announcement")[-1]["data"]
        assert last["wrapper_pid"] == wrapper.pid and last["pane_pid"] == second
    finally:
        if client is not None and client.poll() is None:
            client.kill()
        _end(wrapper, pids)
    assert all(not _alive(p) for p in _pids(pids)), "a session outlived its unit"


@needs_tmux
def test_the_old_session_is_gone_before_the_new_one_starts(tmp_path, short_base):
    """``claude -c`` resumes the conversation, so two sessions at once would share it. A
    session that ignores both the hangup and SIGTERM is killed before the pane runs again."""
    pids, overlap = tmp_path / "pids", tmp_path / "overlap"
    child = _child(tmp_path, (
        f"for p in $(cat {pids} 2>/dev/null); do kill -0 $p 2>/dev/null && echo $p >> {overlap}; done\n"
        f"trap '' HUP TERM\necho $$ >> {pids}\nsleep 300\n"))
    wrapper = _wrapper(tmp_path, child, short_base)
    try:
        _wait_for(lambda: _pids(pids), 15, "the first session")
        _wait_for(lambda: _panes(), 5, "the wrapper's announcement")
        os.kill(wrapper.pid, signal.SIGUSR1)
        _wait_for(lambda: len(_pids(pids)) == 2, su.PANE_GRACE_S + 15, "the respawned session")
        assert not overlap.exists(), f"the new session started beside the old one: {overlap.read_text()}"
        assert wrapper.poll() is None
    finally:
        _end(wrapper, pids)


@needs_tmux
def test_the_unit_still_ends_with_its_respawned_session(tmp_path, short_base):
    """The respawned pane's group is the one the unit's end reaps, and the one recorded for
    the next wrapper, so a stop after a respawn leaves nothing running."""
    pids = tmp_path / "pids"
    child = _child(tmp_path, f"trap '' HUP TERM\necho $$ >> {pids}\nsleep 300\n")
    wrapper = _wrapper(tmp_path, child, short_base)
    try:
        _wait_for(lambda: _pids(pids), 15, "the first session")
        _wait_for(lambda: _panes(), 5, "the wrapper's announcement")
        os.kill(wrapper.pid, signal.SIGUSR1)
        _wait_for(lambda: len(_pids(pids)) == 2, su.PANE_GRACE_S + 15, "the respawned session")
        second = _pids(pids)[1]
        os.killpg(wrapper.pid, signal.SIGTERM)          # the daemon's stop
        assert wrapper.wait(timeout=su.PANE_GRACE_S + 20) == 0
        assert not _alive(second), "the respawned session outlived its unit"
    finally:
        _end(wrapper, pids)
