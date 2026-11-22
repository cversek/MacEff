"""Run the capture unit as its own responsible process on macOS (MIS-0008 R14; docs/VOICE_PORTING.md section 6).

macOS decides microphone access by the *responsible* process: under a primal daemon that is the daemon's
Python, whose bundle has no microphone usage description, so the first request for access kills the unit
instead of asking the operator. Terminal and iTerm solve the same problem for the programs they run by
spawning them with responsibility disclaimed. This does the same: the capture unit re-spawns itself so
that the child answers for itself, under the bundle it runs from (MacEffVoice.app, which carries the
usage description), and the parent waits for it and passes on the daemon's signals.
"""
from __future__ import annotations

import ctypes
import os
import signal
import sys
from typing import List

#: Set in the child, so it runs the unit instead of spawning again.
DISCLAIMED = "MACF_VOICE_DISCLAIMED"
#: The pid the daemon started, which the child's liveness speaks for: the daemon knows only that one.
UNIT_PID = "MACF_VOICE_UNIT_PID"


def _spawn_disclaimed(argv: List[str], env: dict) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    attr = ctypes.c_void_p()
    if libc.posix_spawnattr_init(ctypes.byref(attr)) != 0:
        raise OSError(ctypes.get_errno(), "posix_spawnattr_init failed")
    try:
        if libc.responsibility_spawnattrs_setdisclaim(ctypes.byref(attr), 1) != 0:
            raise OSError(ctypes.get_errno(), "responsibility_spawnattrs_setdisclaim failed")
        c_argv = (ctypes.c_char_p * (len(argv) + 1))(*[a.encode() for a in argv], None)
        pairs = [f"{k}={v}".encode() for k, v in env.items()]
        c_env = (ctypes.c_char_p * (len(pairs) + 1))(*pairs, None)
        pid = ctypes.c_int()
        err = libc.posix_spawn(ctypes.byref(pid), argv[0].encode(), None, ctypes.byref(attr), c_argv, c_env)
        if err != 0:
            raise OSError(err, os.strerror(err))
        return pid.value
    finally:
        libc.posix_spawnattr_destroy(ctypes.byref(attr))


def run_disclaimed(argv: List[str]) -> int:
    """Spawn ``argv`` as its own responsible process, pass SIGTERM and SIGINT on, and return its exit code."""
    env = dict(os.environ, **{DISCLAIMED: "1", UNIT_PID: str(os.getpid())})
    if sys.prefix != sys.base_prefix:
        # Python drops __PYVENV_LAUNCHER__ from the environment once it has read it; the child needs it
        # to start inside the same venv rather than the bare interpreter the bundle wraps
        env["__PYVENV_LAUNCHER__"] = sys.executable
    # handlers first: a stop that arrives while the child starts is held and passed on once its pid
    # is known, rather than killing only this parent and leaving the child holding the microphone
    child: List[int] = []
    pending: List[int] = []

    def forward(sig, _frame):
        if child:
            os.kill(child[0], sig)
        else:
            pending.append(sig)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, forward)
    pid = _spawn_disclaimed(argv, env)
    child.append(pid)
    for sig in pending:
        os.kill(pid, sig)
    _, status = os.waitpid(pid, 0)  # PEP 475: a signal handled meanwhile resumes the wait, never raises EINTR
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return os.WEXITSTATUS(status)


def needed() -> bool:
    """Whether this process should hand the unit to a disclaimed child: on macOS, and not already one."""
    return sys.platform == "darwin" and os.environ.get(DISCLAIMED) != "1"


def own_executable() -> str:
    """The binary this process runs from, such as MacEffVoice.app's: not sys.executable, which in a venv
    names the venv's python and would start the child under another bundle, the one macOS would then ask about."""
    try:
        import psutil
        return psutil.Process().exe()
    except (ImportError, OSError) as e:
        print(f"⚠️ MACF: voice: can't read this process's own binary ({e}); spawning sys.executable", file=sys.stderr)
        return sys.executable


def unit_pid():
    """The daemon's pid for this unit when this is the disclaimed child, else None (this process)."""
    raw = os.environ.get(UNIT_PID)
    return int(raw) if raw and raw.isdigit() else None
