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

A program that writes no such file, such as a web server whose log moves only when a request
arrives, is judged instead by an HTTP probe (#977): the unit beats while a loopback URL has
answered below 500 within the bound. Probes reach loopback only, and ignore proxy settings, so a
unit can't be used to reach the network. A program that answers on no port but ships its own
health check, such as a job worker, is judged by that command instead: the unit beats while the
check exited 0 within the bound.

Declared as:
    python -m macf.pd.watched_unit --fresh <file> --within <seconds> -- <command> [args...]
    python -m macf.pd.watched_unit --probe <loopback url> --within <seconds> --pidfile <file> -- <command> [args...]
    python -m macf.pd.watched_unit --check '<check command>' --within <seconds> --pidfile <file> -- <command> [args...]
"""
import argparse
import ipaddress
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional

from macf.pd.broker_unit import end_orphan, record_child, run

# One request never waits longer than this, whatever the bound, so a hung server can't hold the
# wrapper's loop past the next beat.
PROBE_TIMEOUT_S = 5.0


def fresh(path: Path, within_s: float, now: Callable[[], float] = time.time) -> bool:
    """Whether *path* was modified within the last *within_s* seconds. A missing file isn't."""
    try:
        return now() - os.stat(path).st_mtime <= within_s
    except OSError:
        return False


def loopback_url(url: str) -> str:
    """*url* if it is an http(s) URL naming a loopback host; ValueError, saying why, if not."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"{url}: a probe is an http:// or https:// URL")
    host = parts.hostname
    if host == "localhost":
        # A name is only as loopback as the resolver says: a hosts file can map it elsewhere.
        addresses = _resolve(host)
    else:
        addresses = [host] if host else []
    try:
        loopback = bool(addresses) and all(ipaddress.ip_address(a).is_loopback for a in addresses)
    except ValueError:
        loopback = False
    if not loopback:
        raise ValueError(f"{url}: probes go to loopback only (127.0.0.1, ::1 or localhost), "
                         "so a unit can't be used to reach the network")
    return url


def _resolve(name: str) -> List[str]:
    """Every address *name* resolves to, or none if it doesn't resolve."""
    try:
        return sorted({info[4][0].split("%")[0] for info in socket.getaddrinfo(name, None)})
    except OSError:
        return []


def _direct_opener() -> urllib.request.OpenerDirector:
    """An opener that makes exactly the one request it is given. No proxy, so the request stays
    on loopback; no redirect handler, so a 3xx is reported, never followed off the host; no FTP
    or file handler. With no error processor, every status comes back as a response."""
    opener = urllib.request.OpenerDirector()
    for handler in (urllib.request.ProxyHandler({}), urllib.request.HTTPHandler(),
                    urllib.request.HTTPSHandler()):
        opener.add_handler(handler)
    return opener


_DIRECT = _direct_opener()


def answers(url: str, timeout_s: float, open_url: Callable = _DIRECT.open) -> bool:
    """Whether *url* answers with a status below 500 within *timeout_s*. A 3xx or 4xx is an
    answer: the server is up and replying, and a redirect is never followed. A refusal, a
    timeout or a server error is no answer. Proxy settings are ignored."""
    try:
        with open_url(url, timeout=timeout_s) as response:
            return response.status < 500
    except urllib.error.HTTPError as error:     # an opener that raises on 4xx (tests pass one)
        return error.code < 500
    except (OSError, ValueError):               # refused, reset, timed out, unreadable
        return False


# A health check runs its own program (an interpreter, a client), so it gets longer than a request.
CHECK_TIMEOUT_S = 15.0


def check_passes(argv: List[str], timeout_s: float) -> bool:
    """Whether the check *argv* exits 0 within *timeout_s*. Its output is discarded; a check that
    can't start, or doesn't finish in time, fails."""
    try:
        return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout_s).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class Probe:
    """Alive while *url* last answered within *within_s*, the way ``fresh`` judges a file. One
    slow request doesn't drop the unit; a server that stopped answering does, within the bound.
    A server still starting has never answered, so it reads as not alive yet."""

    def __init__(self, url: str, within_s: float, ask: Callable[[str, float], bool] = answers,
                 now: Callable[[], float] = time.monotonic, cap_s: float = PROBE_TIMEOUT_S):
        self.url, self.within_s, self._ask, self._now = url, within_s, ask, now
        self.cap_s = cap_s
        self.last_answer: Optional[float] = None

    def __call__(self, _port: object = None) -> bool:
        if self._ask(self.url, min(self.within_s, self.cap_s)):
            self.last_answer = self._now()
        return self.last_answer is not None and self._now() - self.last_answer <= self.within_s


def pidfile_for(fresh_file: Path) -> Path:
    """Where the wrapper records its child, unless told: beside the program's heartbeat file."""
    return fresh_file.with_name(fresh_file.name + ".wrapped.pid")


def main(argv: Optional[List[str]] = None) -> int:
    from macf.pd.liveness import heartbeat_from_env
    parser = argparse.ArgumentParser(
        prog="python -m macf.pd.watched_unit",
        description="Run a program that isn't MacEff code as a unit, alive while its heartbeat file "
                    "is fresh or while it answers on loopback.")
    judge = parser.add_mutually_exclusive_group(required=True)
    judge.add_argument("--fresh", type=Path,
                       help="the file the program modifies while it is working")
    judge.add_argument("--probe",
                       help="a loopback http(s) URL the program answers while it is working")
    judge.add_argument("--check",
                       help="a health-check command, one quoted string, that exits 0 while the "
                            "program is working")
    parser.add_argument("--within", type=float, required=True,
                        help="seconds: the file was modified, or the URL answered, this recently")
    parser.add_argument("--pidfile", type=Path, default=None,
                        help="where the child is recorded (default: beside the heartbeat file; "
                             "required with --probe)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- then the program and its arguments")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no program given: put it after --")
    if args.within <= 0:
        parser.error("--within must be more than 0 seconds")
    if args.probe is not None:
        try:
            loopback_url(args.probe)
        except ValueError as refused:
            parser.error(str(refused))
        if args.pidfile is None:
            parser.error("--probe needs --pidfile: there is no heartbeat file to record the child beside")
        alive: Callable[[object], bool] = Probe(args.probe, args.within)
    elif args.check is not None:
        check = shlex.split(args.check)
        if not check:
            parser.error("--check needs a command")
        if args.pidfile is None:
            parser.error("--check needs --pidfile: there is no heartbeat file to record the child beside")
        alive = Probe(args.check, args.within, ask=lambda _what, t: check_passes(check, t),
                      cap_s=CHECK_TIMEOUT_S)
    else:
        alive = lambda _port: fresh(args.fresh, args.within)
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
                   probe=alive,
                   stopping=lambda: stop["asked"], reloading=reloading,
                   on_start=lambda pid: record_child(pidfile, pid))
    finally:
        if beat is not None:
            beat.stop()


if __name__ == "__main__":
    sys.exit(main())
