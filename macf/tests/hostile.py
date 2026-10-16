"""Hostile stand-ins: processes a stop has to beat, for supervision tests (idea 405).

A stop tested against a process that dies on the first signal proves only that the signal
arrived. These stand-ins resist it the ways real ones do:

- ``ignores_term``: traps HUP, INT and TERM, so only SIGKILL ends it.
- ``leaves_a_child``: its leader exits (on SIGTERM, or after ``leader_for`` seconds) and
  leaves a child in the same process group that ignores TERM. A stop that takes the
  leader's exit for the end of the run misses it.
- ``own_session``: its child calls ``setsid()``, leaving the group a group signal reaches.
- ``zombie``: its child exits and is never reaped while the parent lives, so a liveness
  probe that counts zombies sees a group that has already ended.

Each is a Python script, not a shell line, so it runs the same on macOS (which has no
``setsid`` command) and needs no quoting: a nested ``sh -c "... $$ ..."`` expands ``$$`` in
the outer shell, and the pid it writes is the leader's, not the child's.

The ``hostile`` fixture (conftest) records every pid a stand-in writes and SIGKILLs each,
and its group, at teardown, so a failing test leaves nothing running.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from macf.notify.session import proc_start

STANDIN = r'''
import os, signal, sys, time
mode, pidfile = sys.argv[1], sys.argv[2]
arg = float(sys.argv[3]) if len(sys.argv) > 3 else -1.0

def mark(pid, path=pidfile):
    open(path + ".tmp", "w").write(str(pid))
    os.replace(path + ".tmp", path)

mark(os.getpid(), pidfile + ".leader")   # so teardown can reach the leader too

def resist():
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)

def forever():
    while True:
        time.sleep(1)

if mode == "ignores_term":
    resist(); mark(os.getpid()); forever()
if mode == "leaves_a_child":
    if os.fork() == 0:
        resist(); mark(os.getpid()); forever()
    if arg < 0:
        forever()                      # the leader dies only on a signal
    time.sleep(arg); os._exit(0)       # the leader leaves on its own
if mode == "own_session":
    if os.fork() == 0:
        os.setsid(); resist(); mark(os.getpid()); forever()
    forever()
if mode == "zombie":
    child = os.fork()
    if child == 0:
        os._exit(0)
    mark(child); forever()             # never reaps it
sys.exit("unknown mode " + mode)
'''


def alive(pid: int) -> bool:
    """Running, and not a zombie waiting to be reaped."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[0]
        return state != "Z"
    except OSError:
        pass
    if not Path("/proc/self").exists():               # macOS: ask ps
        out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
        return out.returncode == 0 and bool(out.stdout.strip()) and not out.stdout.strip().startswith("Z")
    return False


class Hostile:
    """Stand-in commands for one test, and the pids they report, killed at teardown."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.script = self.dir / "hostile_standin.py"
        self.script.write_text(STANDIN)
        self._seen: List[Tuple[int, Optional[str]]] = []
        self._n = 0

    def _argv(self, mode: str, arg: Optional[float] = None) -> List[str]:
        self._n += 1
        pidfile = self.dir / f"{mode}-{self._n}.pid"
        argv = [sys.executable, str(self.script), mode, str(pidfile)]
        return argv + ([str(arg)] if arg is not None else [])

    def ignores_term(self) -> List[str]:
        return self._argv("ignores_term")

    def leaves_a_child(self, leader_for: Optional[float] = None) -> List[str]:
        """The leader dies on SIGTERM, or leaves after *leader_for* seconds."""
        return self._argv("leaves_a_child", leader_for)

    def own_session(self) -> List[str]:
        return self._argv("own_session")

    def zombie(self) -> List[str]:
        return self._argv("zombie")

    def pid(self, argv: List[str], timeout: float = 10.0) -> int:
        """The pid a stand-in started with *argv* reports: the resisting process (the child,
        for the forking modes), or the zombie's. Recorded for teardown."""
        path = Path(argv[3])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists() and path.read_text().strip():
                leader = Path(f"{path}.leader")
                if leader.exists() and leader.read_text().strip():
                    self.track(int(leader.read_text()))
                return self.track(int(path.read_text()))
            time.sleep(0.02)
        raise AssertionError(f"the {argv[2]} stand-in never reported its pid ({path})")

    def track(self, pid: int) -> int:
        """Record a pid the test started itself, such as a stand-in's leader, with its start,
        so teardown never kills a process that has since taken the number."""
        self._seen.append((pid, proc_start(pid)))
        return pid

    def cleanup(self) -> None:
        for pid, start in self._seen:
            if start is None or proc_start(pid) != start:
                continue                                   # gone, or the number is someone else's
            for kill in (lambda: os.killpg(pid, signal.SIGKILL), lambda: os.kill(pid, signal.SIGKILL)):
                try:
                    kill()
                except (ProcessLookupError, PermissionError):
                    pass  # noqa: MACEFF003 - already gone, or not a group leader: nothing to clean
