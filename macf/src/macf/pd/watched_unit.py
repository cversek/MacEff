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
check exited 0 within the bound. Either way, when the unit stops answering the wrapper says why on
stderr, once, and the probe or check runs in a thread the loop doesn't wait on, so a hung one never
delays a stop.

Declared as:
    python -m macf.pd.watched_unit --fresh <file> --within <seconds> -- <command> [args...]
    python -m macf.pd.watched_unit --probe <loopback url> --within <seconds> --pidfile <file> -- <command> [args...]
    python -m macf.pd.watched_unit --check '<check command>' --within <seconds> --pidfile <file> -- <command> [args...]
"""
import argparse
import http.client
import ipaddress
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional

from macf.pd.broker_unit import end_orphan, record_child, run

# One request never waits longer than this, whatever the bound. Requests run off the wrapper's loop
# (Probe's background), so this bounds how long a verdict can lag, not how long the loop waits.
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


def answer_failure(url: str, timeout_s: float, open_url: Callable = _DIRECT.open) -> Optional[str]:
    """Why *url* gave no answer within *timeout_s*, or None if it answered with a status below
    500. A 3xx or 4xx is an answer: the server is up and replying, and a redirect is never
    followed. A refusal, a timeout or a server error is no answer, and the reason says which.
    Proxy settings are ignored."""
    try:
        with open_url(url, timeout=timeout_s) as response:
            status = response.status
    except urllib.error.HTTPError as error:     # an opener that raises on 4xx (tests pass one)
        status = error.code
    # Refused, reset, timed out, unreadable; or something on the port that doesn't speak HTTP,
    # which http.client reports as an HTTPException (BadStatusLine for a banner, say).
    except (OSError, ValueError, http.client.HTTPException) as error:
        return f"{url} gave no answer: {type(error).__name__}: {error}"
    return None if status < 500 else f"{url} answered {status}"


# A health check runs its own program (an interpreter, a client), so it gets longer than a request.
CHECK_TIMEOUT_S = 15.0

# How much of a failed check's output its reason keeps: the last lines are where errors land.
CHECK_TAIL_LINES = 3


class Check:
    """Runs the health check *argv*. Calling it gives why the check failed, or None if it
    exited 0 within the time allowed. The check's output, stdout and stderr together, is kept
    only for the reason, as its last few lines. ``close`` ends a run still under way, so a
    wrapper that is stopping never leaves a check behind it."""

    def __init__(self, argv: List[str]):
        self.argv = argv
        self._running: Optional[subprocess.Popen] = None

    def __call__(self, _what: object, timeout_s: float) -> Optional[str]:
        name = Path(self.argv[0]).name
        try:
            child = subprocess.Popen(self.argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
        except OSError as error:
            return f"the check {name} could not start: {error}"
        self._running = child
        try:
            output, _ = child.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            return f"the check {name} did not finish within {timeout_s:g} s"
        finally:
            self._running = None
        if child.returncode == 0:
            return None
        tail = output.decode(errors="replace").strip().splitlines()[-CHECK_TAIL_LINES:]
        return f"the check {name} exited {child.returncode}" + (f": {' | '.join(tail)}" if tail else "")

    def close(self) -> None:
        child = self._running
        if child is not None and child.poll() is None:
            child.kill()


def _say(line: str) -> None:
    print(f"⚠️ MACF: watched_unit: {line}", file=sys.stderr, flush=True)


class Probe:
    """Alive while *what* (a URL, or a check) last answered within *within_s*, the way ``fresh``
    judges a file. One slow or failed answer doesn't drop the unit; a program that stopped
    answering does, within the bound. A program still starting has never answered, so it reads
    as not alive yet.

    *ask* gives why *what* didn't answer, or None if it did. When the verdict turns from
    answering to not, the last reason is written to stderr once, and once more when it answers
    again, so a flapping unit logs its transitions rather than every pass. A program that hasn't
    answered within the bound of its start is reported the same way.

    With *background*, each ask runs in a thread the caller doesn't wait on, so a hung server or
    check never holds the wrapper's loop: a stop is still seen within one poll."""

    def __init__(self, what: str, within_s: float,
                 ask: Callable[[str, float], Optional[str]] = answer_failure,
                 now: Callable[[], float] = time.monotonic, cap_s: float = PROBE_TIMEOUT_S,
                 say: Callable[[str], None] = _say, background: bool = False):
        self.what, self.within_s, self._ask, self._now = what, within_s, ask, now
        self.cap_s, self._say, self._background = cap_s, say, background
        self.last_answer: Optional[float] = None
        self.last_failure: Optional[str] = None
        self._started_at = now()
        self._said_down = False
        self._asking: Optional[threading.Thread] = None

    def _ask_once(self) -> None:
        try:
            failure = self._ask(self.what, min(self.within_s, self.cap_s))
        except Exception as error:  # noqa: BLE001 - an ask that raises is a failed attempt; its reason is said on the transition line, not lost with the thread
            failure = f"the attempt raised {type(error).__name__}: {error}"
        if failure is None:
            self.last_answer = self._now()
            self.last_failure = None    # a later hang mustn't report an earlier outage as its reason
        else:
            self.last_failure = failure

    def __call__(self, _port: object = None) -> bool:
        if not self._background:
            self._ask_once()
        elif self._asking is None or not self._asking.is_alive():
            self._asking = threading.Thread(target=self._ask_once, daemon=True)
            self._asking.start()
        now = self._now()
        alive = self.last_answer is not None and now - self.last_answer <= self.within_s
        if alive and self._said_down:
            self._say(f"{self.what} is answering again")
            self._said_down = False
        elif not alive and not self._said_down and \
                (self.last_answer is not None or now - self._started_at > self.within_s):
            why = self.last_failure or "no attempt has finished yet"
            self._say(f"{self.what} has not answered within {self.within_s:g} s; last: {why}")
            self._said_down = True
        return alive

    def close(self) -> None:
        """End a check still running, if *ask* runs one."""
        close = getattr(self._ask, "close", None)
        if close is not None:
            close()


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
        alive: Callable[[object], bool] = Probe(args.probe, args.within, background=True)
    elif args.check is not None:
        check = shlex.split(args.check)
        if not check:
            parser.error("--check needs a command")
        if args.pidfile is None:
            parser.error("--check needs --pidfile: there is no heartbeat file to record the child beside")
        alive = Probe(args.check, args.within, ask=Check(check), cap_s=CHECK_TIMEOUT_S,
                      background=True)
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
        if isinstance(alive, Probe):
            alive.close()
        if beat is not None:
            beat.stop()


if __name__ == "__main__":
    sys.exit(main())
