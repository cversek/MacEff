"""The inbound tunnel as a primal daemon's unit: cloudflared, supervised, alive only when connected.

A deployment that fronts its receiver with a Cloudflare tunnel declares this module as a unit of
the tunnel account's primal daemon (persistent_layer 10.1). The account is the only holder of the
tunnel credential: a receiver that held it could be made to carry the tunnel, and with it the
deployment's inbound mail, somewhere else.

WHY A WRAPPER. cloudflared is a third-party binary that writes no liveness of its own, and a
process that exists says nothing about whether it reaches the edge (MIS-0002-R14). This runs it as
a child with its metrics server on loopback and asks ``/ready``: 200 means at least one edge
connection is registered. A beat is written only after a ready answer, so a tunnel that is up but
not connected reads overdue to its daemon, as it should.

WHY IT EXITS. When cloudflared exits, this exits with the same code, and the daemon restarts the
unit under its declared policy. A bad configuration therefore shows as a failing unit with its
reason in the unit's log, not as a launched process nobody looks at again.

STARTED MEANS CONNECTED. "connected" is printed on the first ready answer. If none comes within
``--startup-s``, a warning says so and names the metrics address, and the wait continues: the
daemon's overdue reading is the alarm, this line is the explanation.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Optional, Tuple

from macf.pd.liveness import heartbeat_from_env

DEFAULT_CONFIG = "/etc/cloudflared/config.yml"
DEFAULT_METRICS = "127.0.0.1:20241"
DEFAULT_STARTUP_S = 60.0
POLL_S = 5.0


def ready(metrics: str, timeout: float = 3.0) -> Tuple[bool, str]:
    """Whether cloudflared reports at least one registered edge connection, and why not."""
    url = f"http://{metrics}/ready"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(4096)
    except urllib.error.HTTPError as e:
        return False, f"/ready answered {e.code}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"/ready unreachable ({e})"
    try:
        n = int(json.loads(body or b"{}").get("readyConnections", 0))
    except (ValueError, TypeError, AttributeError):
        return False, "/ready answered 200 with no readable readyConnections"
    return (n > 0), (f"{n} edge connection(s)" if n > 0 else "no edge connections")


PR_SET_PDEATHSIG = 1
# Read in the wrapper at import, before any fork, so the child can tell whether its parent
# is still the wrapper that started it.
_WRAPPER_PID = os.getpid()


def die_with_parent() -> None:
    """In the child, before exec: have the kernel send SIGTERM when this wrapper dies.

    The daemon stops a unit by its process group, which takes cloudflared with it. A wrapper killed
    any other way (the kernel's OOM killer, a SIGKILL from a person) would otherwise leave an
    orphaned cloudflared holding the tunnel and the metrics port, so the restarted wrapper's
    /ready would answer for the orphan. Linux only; elsewhere the process group is the cover.

    The signal follows the THREAD that forked, not the process: if the Popen ran on a worker
    thread, the child would be killed when that thread exited, with the wrapper still alive. Keep
    the Popen on the main thread. A wrapper that died between the fork and this call would never
    send the signal, so the child checks that its parent is still the one that started it."""
    if not sys.platform.startswith("linux"):
        return
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
        err = ctypes.get_errno()
        raise OSError(err, "prctl(PR_SET_PDEATHSIG) failed: " + os.strerror(err))
    if os.getppid() != _WRAPPER_PID:
        os._exit(1)  # the wrapper is already gone; don't start an orphaned tunnel


def supervise(child: "subprocess.Popen", metrics: str, startup_s: float,
              tick: Optional[Callable[[], None]] = None,
              probe: Callable[[str], Tuple[bool, str]] = ready,
              sleep: Callable[[float], None] = time.sleep,
              clock: Callable[[], float] = time.monotonic,
              stopping: Callable[[], bool] = lambda: False) -> int:
    """Poll the child's readiness until it exits; tick on each ready answer. Returns its exit code,
    or 0 when the exit followed a stop this wrapper was asked for."""
    began = clock()
    connected = warned = False
    while True:
        code = child.poll()
        if code is not None:
            if stopping():
                print(f"amail tunnel stopped on request (cloudflared exited with {code})", flush=True)
                return 0
            print(f"amail tunnel: cloudflared exited with {code}; the daemon restarts this unit",
                  file=sys.stderr, flush=True)
            return code if code != 0 else 1   # a tunnel that stops unasked is never a clean exit
        ok, why = probe(metrics)
        if ok:
            if tick:
                tick()
            if not connected:
                print(f"amail tunnel connected: {why}", flush=True)
                connected = True
        elif not connected and not warned and clock() - began > startup_s:
            print(f"⚠️ MACF: amail tunnel not connected after {startup_s:g} s ({why}; metrics at "
                  f"{metrics}); inbound mail cannot reach the receiver until it is", file=sys.stderr,
                  flush=True)
            warned = True
        elif connected and not ok:
            print(f"⚠️ MACF: amail tunnel lost its edge connections ({why})", file=sys.stderr,
                  flush=True)
            connected = False
        sleep(POLL_S)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m macf.amail.daemons.tunnel")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--metrics", default=DEFAULT_METRICS,
                   help="loopback address for cloudflared's metrics server, where /ready is asked")
    p.add_argument("--startup-s", type=float, default=DEFAULT_STARTUP_S)
    p.add_argument("--binary", default=shutil.which("cloudflared") or "/usr/local/bin/cloudflared")
    args = p.parse_args(argv)
    if not os.path.exists(args.config):
        print(f"refusing to start: no tunnel config at {args.config}", file=sys.stderr)
        return 78   # EX_CONFIG: restarting cannot fix a missing file
    if not os.access(args.binary, os.X_OK):
        print(f"refusing to start: cloudflared is not installed at {args.binary}", file=sys.stderr)
        return 78
    child = subprocess.Popen([args.binary, "tunnel", "--config", args.config,
                              "--metrics", args.metrics, "run"], preexec_fn=die_with_parent)
    asked = []

    def stop(signum, _frame):
        asked.append(signum)
        child.send_signal(signum)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    heartbeat = heartbeat_from_env()   # already started when this runs as a declared unit
    try:
        return supervise(child, args.metrics, args.startup_s,
                         tick=heartbeat.tick if heartbeat else None, stopping=lambda: bool(asked))
    finally:
        if heartbeat is not None:
            heartbeat.stop()


if __name__ == "__main__":
    sys.exit(main())
