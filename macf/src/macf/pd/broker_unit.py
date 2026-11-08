"""The broker unit's wrapper: mosquitto as a declared unit that reports its own liveness
(PROTOTYPE, mission B).

A daemon credits a unit only for ``pd_unit_alive`` events naming the incarnation it started
(MIS-0002-R14, R15), and mosquitto writes none, so declared bare it would read ``starting``
and then fail. This wrapper is the process the daemon starts. It runs mosquitto as its child,
and on each pass it ticks the unit's heartbeat only when the broker accepts a connection on its
listener: a broker process that exists but no longer listens stops the beats, and the daemon
sees the unit go overdue, as it should. The wrapper ends with mosquitto's exit status when
mosquitto ends, passes a stop signal on to it, and passes SIGHUP on as a reload.

Declared as:  python -m macf.pd.broker_unit {runtime_dir}/<card>.broker/mosquitto.conf
"""
import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

from macf.pd.broker import LOOPBACK

#: The longest a pass waits; the heartbeat's interval sets how often a beat is owed.
POLL_S = 2.0


def listener_port(conf: Path) -> int:
    """The port of the ``listener`` line in a rendered mosquitto.conf."""
    for line in Path(conf).read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "listener":
            return int(parts[1])
    raise ValueError(f"{conf} names no listener")


def accepts(port: int, host: str = LOOPBACK, timeout: float = 1.0) -> bool:
    """Whether something accepts a TCP connection on *host*:*port*."""
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


#: Beside the configuration: the pid and start time of the mosquitto this wrapper started.
PIDFILE_NAME = "mosquitto.pid"


def end_orphan(pidfile: Path, *, grace_s: float = 5.0) -> Optional[int]:
    """End the mosquitto a previous wrapper started, when it is still that very process: a wrapper
    killed with SIGKILL can't stop its child, which then holds the port, and every new broker
    fails to bind (#921). The recorded start time is checked, so a reused pid is never signalled.
    The pid ended, or None. Linux could ask the kernel to end the child with its parent; macOS
    can't, so the record is how both find it."""
    from macf.notify.session import verify_incarnation
    try:
        pid_text, start = Path(pidfile).read_text().split(None, 1)
        pid = int(pid_text)
    except (OSError, ValueError):
        return None  # noqa: MACEFF003 - no record, or an unreadable one: nothing to end
    if not verify_incarnation(pid, start.strip()):
        return None
    try:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + grace_s
        while time.monotonic() < deadline and verify_incarnation(pid, start.strip()):
            time.sleep(0.1)
        if verify_incarnation(pid, start.strip()):
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # noqa: MACEFF003 - it ended on its own between the check and the signal, which is the goal
    print(f"⚠️ MACF: pd: ended the broker a previous wrapper left running (pid {pid})", file=sys.stderr)
    return pid


def record_child(pidfile: Path, pid: int) -> None:
    """Record the broker this wrapper started, for the next wrapper's ``end_orphan``."""
    from macf.notify.session import proc_start
    start = proc_start(pid)
    if start:
        Path(pidfile).write_text(f"{pid} {start}\n")


def run(command: List[str], port: int, tick: Callable[[], None], *, poll_s: float = POLL_S,
        probe_every_s: float = 0.0, probe: Callable[[int], bool] = accepts,
        stopping: Callable[[], bool] = lambda: False,
        reloading: Callable[[], bool] = lambda: False,
        on_start: Callable[[int], None] = lambda pid: None) -> int:
    """Run *command* until it ends, ticking after each probe that finds it accepting on *port*;
    its exit status. A probe runs at most once per *probe_every_s* (each one is a connection
    the broker logs as a protocol error), while the child's exit and a stop are checked every
    *poll_s*. When *stopping* turns true, the child is asked to end and the wrapper waits. When
    *reloading* turns true, the child is sent SIGHUP: mosquitto rereads its access rules then,
    and they apply to the connections it already holds (MIS-0002-R152)."""
    child = subprocess.Popen(command)
    on_start(child.pid)
    probed_at = None
    try:
        while True:
            code = child.poll()
            if code is not None:
                return code
            if stopping():
                child.terminate()
                return child.wait(timeout=10)
            if reloading():
                child.send_signal(signal.SIGHUP)
            now = time.monotonic()
            if probed_at is None or now - probed_at >= probe_every_s:
                probed_at = now
                if probe(port):
                    tick()
            time.sleep(poll_s)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def main(argv: Optional[List[str]] = None) -> int:
    from macf.pd.liveness import heartbeat_from_env
    parser = argparse.ArgumentParser(prog="python -m macf.pd.broker_unit",
                                     description="Run a daemon's own mosquitto as a unit that reports liveness.")
    parser.add_argument("conf", type=Path, help="the mosquitto.conf the daemon rendered")
    parser.add_argument("--mosquitto", default="mosquitto", help="the broker binary")
    args = parser.parse_args(argv)
    if shutil.which(args.mosquitto) is None:
        print(f"⚠️ MACF: pd: the broker unit can't find {args.mosquitto!r} on its PATH: every daemon runs "
              f"its own broker (persistent_layer 11.4). Install mosquitto (apt install mosquitto; on macOS "
              f"brew install mosquitto, without brew services start, which runs a second broker of its "
              f"own), then restart the daemon.", file=sys.stderr)
        return 127
    port = listener_port(args.conf)
    pidfile = args.conf.parent / PIDFILE_NAME
    end_orphan(pidfile)                    # a previous wrapper's broker, left by a SIGKILL (#921)
    beat = heartbeat_from_env()
    stop = {"asked": False, "reload": False}
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.__setitem__("asked", True))
    # SIGHUP is the daemon asking the broker to reread its access rules, not to stop.
    signal.signal(signal.SIGHUP, lambda *_: stop.__setitem__("reload", True))

    def reloading() -> bool:
        asked, stop["reload"] = stop["reload"], False
        return asked
    try:
        # Probe a little more often than a beat is owed, so a beat is never missed for want of one.
        every = beat.interval_s / 2 if beat is not None else 60.0
        return run([args.mosquitto, "-c", str(args.conf)], port,
                   beat.tick if beat is not None else (lambda: None), probe_every_s=every,
                   stopping=lambda: stop["asked"], reloading=reloading,
                   on_start=lambda pid: record_child(pidfile, pid))
    finally:
        if beat is not None:
            beat.stop()


if __name__ == "__main__":
    sys.exit(main())
