"""A program that isn't MacEff code, declared as a unit and judged by its own heartbeat file (#934).

A daemon credits a unit only for ``pd_unit_alive`` events naming the incarnation it started
(MIS-0002-R14, R15). A program that isn't MacEff code writes none, so declared bare it reads
``starting`` and then fails. Such programs were therefore run detached, and a container recreate
ended them with nothing to start them again.

This wrapper is the process the daemon starts. It runs the program as its child and ticks the
unit's heartbeat only while a file the program writes was modified within a bound: a program
that is running but stuck stops touching its file, the beats stop, and the daemon sees the unit
go overdue. Like the broker's wrapper (``broker_unit``), it ends with the child's exit status,
passes a stop on to the child (killing it after a grace), passes SIGHUP on, and records the child
so that a wrapper killed with SIGKILL doesn't leave a second copy running beside the next one.

Declared as:
    python -m macf.pd.watched_unit --fresh <file> --within <seconds> -- <command> [args...]
"""
import argparse
import os
import signal
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

from macf.pd.broker_unit import end_orphan, record_child, run


def fresh(path: Path, within_s: float, now: Callable[[], float] = time.time) -> bool:
    """Whether *path* was modified within the last *within_s* seconds. A missing file isn't."""
    try:
        return now() - os.stat(path).st_mtime <= within_s
    except OSError:
        return False


def pidfile_for(fresh_file: Path) -> Path:
    """Where the wrapper records its child, unless told: beside the program's heartbeat file."""
    return fresh_file.with_name(fresh_file.name + ".wrapped.pid")


def main(argv: Optional[List[str]] = None) -> int:
    from macf.pd.liveness import heartbeat_from_env
    parser = argparse.ArgumentParser(
        prog="python -m macf.pd.watched_unit",
        description="Run a program that isn't MacEff code as a unit, alive while its heartbeat file is fresh.")
    parser.add_argument("--fresh", type=Path, required=True,
                        help="the file the program modifies while it is working")
    parser.add_argument("--within", type=float, required=True,
                        help="seconds: the file must have been modified this recently for the unit to beat")
    parser.add_argument("--pidfile", type=Path, default=None,
                        help="where the child is recorded (default: beside the heartbeat file)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- then the program and its arguments")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no program given: put it after --")
    if args.within <= 0:
        parser.error("--within must be more than 0 seconds")
    pidfile = args.pidfile or pidfile_for(args.fresh)
    end_orphan(pidfile, what=f"{Path(command[0]).name}")   # a copy a SIGKILLed wrapper left (#921)
    beat = heartbeat_from_env()
    stop = {"asked": False, "reload": False}
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.__setitem__("asked", True))
    signal.signal(signal.SIGHUP, lambda *_: stop.__setitem__("reload", True))

    def reloading() -> bool:
        asked, stop["reload"] = stop["reload"], False
        return asked
    try:
        # Look a little more often than a beat is owed, so a beat is never missed for want of one.
        every = beat.interval_s / 2 if beat is not None else 60.0
        return run(command, 0, beat.tick if beat is not None else (lambda: None), probe_every_s=every,
                   probe=lambda _port: fresh(args.fresh, args.within),
                   stopping=lambda: stop["asked"], reloading=reloading,
                   on_start=lambda pid: record_child(pidfile, pid))
    finally:
        if beat is not None:
            beat.stop()


if __name__ == "__main__":
    sys.exit(main())
