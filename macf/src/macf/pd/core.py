"""The primal daemon's core: one supervisor for one agent's declared units.

This is the part of MIS-0002 step 1 that decides, not the part that listens. It loads
the agent's declaration, starts each unit as that unit's parent, reaps it, applies its
restart policy, reads the liveness the unit writes to the agent's event log, and
records every state change and every act there. The control socket, the readout and
the session unit's specifics build on it.

What it never does: answer a prompt, widen a permission, or touch a unit outside its
own declaration (MIS-0002-R23 (layer_MUST-NOT_answer_prompts), MIS-0002-R78
(layer_MUST-NOT_widen_permissions), MIS-0002-R07 (pd_MUST-NOT_control_other_agents)). The
event log is its only record (MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)): the
state below lives in memory for the life of the process, and every change to it is
also an event.

A unit's liveness also says what it has in hand, ``in_flight``, which a restart waits on
(MIS-0002-R49 (pd_MUST_check_work_in_flight)), and what it is blocked on that only a
person can give, ``waiting_on`` (MIS-0002-R21 (pd_MUST_report_waiting_on_person)). A
unit that reports no work in flight is taken as idle, and its restart says so.
"""
import json
import os
import pwd
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from macf.agent_events_log import append_event, get_log_path, read_events
from macf.notify.session import proc_start, proc_start_key, verify_incarnation
from macf.pd.interface import (
    EVENT_CONTROL,
    EVENT_DAEMON_START,
    EVENT_LIVENESS,
    EVENT_STATE,
    Asker,
    Control,
    DaemonStart,
    Declaration,
    Liveness,
    Peer,
    State,
    Unit,
    UnitState,
    UnitStatus,
    declaration_path,
    render,
)
from macf.pd.schedule import CronExpr, check_window

#: A unit is overdue once its last liveness is older than this many of its intervals.
#: The interval is the one the unit published, so a unit that changes its cadence
#: changes its own bound (service_supervision: publish the cadence, let the observer
#: compute from it). Before its first liveness, the declared interval stands in.
#: Three tolerates two missed writes. It was chosen in 2026-10 without a measurement of
#: real write jitter, and is to be re-derived once units have run under load.
LIVENESS_TOLERANCE = 3

#: Restart backoff: the first restart after a failure waits the base, each further
#: consecutive failure doubles it, and it never exceeds the cap.
BACKOFF_BASE_S = 1.0
BACKOFF_CAP_S = 300.0

#: A unit that has run this many of its intervals since it started has its failure
#: count cleared, so a crash today does not inherit last week's backoff.
STABLE_INTERVALS = 10

#: How long an asked restart waits for a unit's work in flight to drain (R49) before
#: it goes ahead anyway, and says so.
DRAIN_TIMEOUT_S = 300.0

#: Where the reasoning behind every refusal lives. A refusal names it, so a reader who
#: has just been stopped finds the why without the message restating it
#: (capability_boundaries: a refusal names its policy).
POLICY_POINTER = "macf_tools policy navigate persistent_layer"

#: The asker for what the declaration itself calls for: boot starts, and restarts
#: under a unit's restart policy.
POLICY = Asker(kind="policy")


class DeclarationRefused(ValueError):
    """The declaration cannot be used. Nothing is started: a refusal installs nothing."""


def load_declaration(agent_home: Path, card: str) -> Declaration:
    """Read and validate the agent's declaration, or refuse it whole with the reason.

    ``card`` is the agent's calling card, read from its home's own files. A declaration
    that names another agent declares that agent's units, and this daemon must not
    start them (MIS-0002-R07 (pd_MUST-NOT_control_other_agents)).
    """
    path = declaration_path(agent_home)
    try:
        text = path.read_text()
    except OSError as e:
        raise DeclarationRefused(f"cannot read {path}: {e}") from e
    try:
        declaration = Declaration.model_validate_json(text)
    except ValidationError as e:
        raise DeclarationRefused(f"{path} is not a valid declaration: {e}") from e
    if declaration.agent != card:
        raise DeclarationRefused(
            f"{path} declares the units of {declaration.agent}, and this home belongs to "
            f"{card}. A declaration copied from another agent's home must not run under "
            "this one's name (MIS-0002-R07 (pd_MUST-NOT_control_other_agents))"
        )
    for schedule in declaration.schedules:
        # A schedule that can never fire is refused now, not found out when it is due.
        try:
            CronExpr.parse(schedule.cron, tz=ZoneInfo(declaration.timezone))
            if schedule.missed_run.window is not None:
                check_window(schedule.missed_run.window)
        except ValueError as e:
            raise DeclarationRefused(f"{path}: schedule {schedule.name}: {e}") from e
    for window in declaration.quiet_windows:
        try:
            check_window(window)
        except ValueError as e:
            raise DeclarationRefused(f"{path}: quiet window: {e}") from e
    me = pwd.getpwuid(os.getuid()).pw_name
    foreign = [u.name for u in declaration.units if u.account != me]
    if foreign:
        raise DeclarationRefused(
            f"{', '.join(foreign)} name an account other than {me}. Step 1 starts units only "
            "as the daemon's own user; any other account needs a grant the agent cannot "
            "write itself (MIS-0002-R78 (layer_MUST-NOT_widen_permissions))"
        )
    return declaration


def quiet_window_at(declaration: Declaration, at: float):
    """The declared quiet window the time ``at`` (epoch seconds) falls in, or None.

    MIS-0002-R50 (layer_MUST-NOT_act_in_quiet_window). Windows are read in the declaration's
    timezone, which the interface requires once any window is declared, and one whose end
    comes before its start runs past midnight. Times compare as ``HH:MM``, so a window ends
    at its minute.
    """
    if not declaration.quiet_windows:
        return None
    hhmm = datetime.fromtimestamp(at, ZoneInfo(declaration.timezone)).strftime("%H:%M")
    for window in declaration.quiet_windows:
        if window.start <= window.end:
            inside = window.start <= hhmm < window.end
        else:
            inside = hhmm >= window.start or hhmm < window.end
        if inside:
            return window
    return None


def backoff_s(failures: int, base: float = BACKOFF_BASE_S, cap: float = BACKOFF_CAP_S) -> float:
    """The wait before restarting a unit after its ``failures``-th consecutive failure."""
    if failures < 1:
        return 0.0
    return min(cap, base * 2 ** (failures - 1))


#: How long a unit, or what is left of its group, is given to end after SIGKILL, by
#: shutdown and by a stop's remnant, before the core stops waiting and says so.
KILL_WAIT_S = 5.0

#: The exit status of a unit this daemon adopted rather than started. It is not the
#: unit's parent, so the status cannot be read; it is taken as a failure, so the restart
#: policy keeps the unit up.
EXIT_NOT_SEEN = -1000

#: Unit states with a process behind them, which a restarted daemon may adopt.
LIVE_STATES = ("starting", "running", "waiting_on_a_person")


def start_epoch(start) -> Optional[float]:
    """When the process whose start fingerprint is ``start`` began, in epoch seconds, or None.

    macOS records the start as a UTC time already. Linux records clock ticks since boot,
    which become a time with the boot time from ``/proc/stat``."""
    key = proc_start_key(start)
    if key is None:
        return None
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/stat") as f:
                btime = next(int(line.split()[1]) for line in f if line.startswith("btime "))
            return btime + key / os.sysconf("SC_CLK_TCK")
        except (OSError, StopIteration, ValueError) as e:
            print(f"⚠️ MACF: pd: cannot read the boot time for a start time: {e}", file=sys.stderr)
            return None
    return float(key)


def _describe_exit(code: int) -> str:
    if code == EXIT_NOT_SEEN:
        return "exited with a status this daemon cannot see (it adopted the unit, so it is not its parent)"
    if code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = str(-code)
        return f"killed by {name}"
    return f"exited {code}"


def _pid_in_use(pid: int) -> bool:
    """Whether some process holds ``pid``. Permission to signal it doesn't matter: a pid
    that exists, whoever owns it, is in use."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def group_members(pgid: int) -> List[tuple]:
    """The live members of process group ``pgid``, as (pid, start time), zombies left out.

    A unit leads its own group, so once its leader is reaped these are the processes it
    started that outlived it. Read from /proc on Linux and from ``ps`` on macOS, where
    there is no /proc; a member that ends while it is read is left out.
    """
    pids: List[int] = []
    proc = Path("/proc")
    if proc.is_dir():
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                stat = (entry / "stat").read_text()
            except OSError:
                continue  # ended while the table was read
            fields = stat[stat.rfind(")") + 2:].split()
            if len(fields) > 2 and fields[0] != "Z" and fields[2] == str(pgid):
                pids.append(int(entry.name))
    else:
        try:
            out = subprocess.run(["ps", "-A", "-o", "pid=,pgid=,stat="], capture_output=True,
                                 text=True, timeout=10, env={**os.environ, "LC_ALL": "C"})
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"⚠️ MACF: pd: cannot list process group {pgid}: {e}", file=sys.stderr)
            return []
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] == str(pgid) and not parts[2].startswith("Z"):
                pids.append(int(parts[0]))
    members = []
    for pid in pids:
        start = proc_start(pid)
        if start:
            members.append((pid, start))
    return members


class _Adopted:
    """A unit the previous daemon started that outlived it, in the place of a ``Popen``.

    The units outlive the daemon's exit, so a daemon restarted after a crash finds them
    still running and adopts them instead of starting second copies. It is not their
    parent, so it reads neither their exit status nor their end from the kernel: it asks
    whether the process is still the one its record names, by pid and start time
    (MIS-0002-R15 (readout_MUST_probe_liveness)). Each unit leads its own
    process group, so the core's existing ``killpg`` stops an adopted one too.
    """

    def __init__(self, pid: int, start: str, probe: Callable[[int, str], bool]):
        self.pid = pid
        self._start = start
        self._probe = probe
        self.returncode: Optional[int] = None

    def poll(self) -> Optional[int]:
        if self.returncode is None and not self._probe(self.pid, self._start):
            self.returncode = EXIT_NOT_SEEN
        return self.returncode

    def wait(self, timeout: Optional[float] = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(f"adopted pid {self.pid}", timeout)
            time.sleep(0.02)
        return self.returncode


@dataclass
class _Runner:
    """What the core knows about one unit, for the life of the daemon."""

    spec: Unit
    state: State = "declared"
    since: float = 0.0                  # wall time of the last state change
    proc: Optional[object] = None       # a Popen, or _Adopted after a restart
    pid: Optional[int] = None
    proc_start: Optional[str] = None
    started_at: float = 0.0             # monotonic, at the last start
    alive_at: Optional[float] = None    # monotonic, at the last accepted liveness
    alive_interval_s: Optional[float] = None
    in_flight: Optional[int] = None     # as the unit last reported it; None if it never has
    failures: int = 0
    want_up: bool = False               # whether the unit should be running
    restart_at: Optional[float] = None  # monotonic: a restart under its policy is due
    kill_at: Optional[float] = None     # monotonic: SIGKILL if it has not exited
    stopping: Optional[str] = None      # why a stop is under way, until the exit is reaped
    then_start: bool = False            # the stop under way is half of a restart
    drain: Optional[tuple] = None       # (asker, reason, deadline) of a restart waiting on R49
    held_restart: Optional[tuple] = None  # (asker, reason, peer) of an asked restart a quiet window holds (R50)
    client_session: Optional[str] = None  # session id, when the client's own daemon hosts this session (R66)
    awaiting_respawn: Optional[float] = None  # monotonic deadline for a respawned worker to be listed
    client_escalated: bool = False      # a stop the client accepted outlived its grace, so signals followed
    client_binary: Optional[str] = None  # the claude found on the session unit's declared PATH
    remnant: Optional[tuple] = None     # (pgid, [(pid, start)], kill_at, killed_at): members left after a stop reaped the leader
    start_after_remnant: bool = False   # a start waits for the remnant to end
    stop_pending: Optional[str] = None  # the stopped transition's reason, recorded once the remnant ends


class _LivenessTail:
    """The liveness events appended to the agent's event log since the core started.

    It reads only what is new, from an offset, so a long log costs nothing per pass, and
    it starts at the end: liveness written before this daemon started belongs to units
    it did not start. A log that shrinks or is replaced (rotation) is read from its
    start. A line that names the liveness event but does not parse is counted, never
    credited: liveness that cannot be read is unknown, and unknown is not alive.
    """

    def __init__(self, path: Path):
        self.path = path
        self.unreadable = 0
        self._partial = b""
        try:
            st = path.stat()
            self._offset, self._inode = st.st_size, st.st_ino
        except FileNotFoundError:
            self._offset, self._inode = 0, None

    def read(self) -> List[dict]:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return []
        if st.st_ino != self._inode or st.st_size < self._offset:
            self._offset, self._inode, self._partial = 0, st.st_ino, b""
        if st.st_size == self._offset:
            return []
        with open(self.path, "rb") as f:
            f.seek(self._offset)
            chunk = f.read(st.st_size - self._offset)
        self._offset += len(chunk)
        lines = (self._partial + chunk).split(b"\n")
        self._partial = lines.pop()
        events = []
        for line in lines:
            if EVENT_LIVENESS.encode() not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError as e:
                self.unreadable += 1
                print(f"⚠️ MACF: pd: a liveness line in {self.path} does not parse "
                      f"(not credited): {e}", file=sys.stderr)
                continue
            if event.get("event") == EVENT_LIVENESS:
                events.append(event)
        return events


def _harness_hosted_sessions() -> list:
    from macf.notify.session import harness_hosted_sessions
    return harness_hosted_sessions()


#: How long a client verb may run. The serve loop answers requests between passes, so a
#: hung CLI holds a pd status or an operator's stop for at most this long.
CLIENT_TIMEOUT_S = 10.0

#: How long a respawn the client accepted may take to show its worker in the readout,
#: checked on each pass, before the session unit is decided afresh.
RESPAWN_WAIT_S = 30.0


def _run_client(argv: List[str]) -> "subprocess.CompletedProcess":
    """The client's own verb, bounded by CLIENT_TIMEOUT_S."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=CLIENT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(argv, 1, "", str(e))


class Core:
    """Supervises one agent's declared units. Drive it with ``boot`` and then ``tick``.

    ``clock`` is monotonic time and ``wall`` is epoch time; both are parameters so a test
    can drive the timers without sleeping. Processes are real: a unit is started as this
    process's child, in a process group of its own, so a stop reaches everything it
    started.
    """

    def __init__(
        self,
        declaration: Declaration,
        card: str,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        backoff_base_s: float = BACKOFF_BASE_S,
        backoff_cap_s: float = BACKOFF_CAP_S,
        drain_timeout_s: float = DRAIN_TIMEOUT_S,
        placeholders: Optional[Dict[str, str]] = None,
        probe: Callable[[int, str], bool] = verify_incarnation,
        hosted: Optional[Callable[[], list]] = None,
        client: Optional[Callable[[List[str]], "subprocess.CompletedProcess"]] = None,
    ):
        self.declaration = declaration
        self.card = card
        self._clock = clock
        self._wall = wall
        self._backoff = (backoff_base_s, backoff_cap_s)
        self._placeholders = dict(placeholders or {})
        self._drain_timeout = drain_timeout_s
        self._probe = probe
        # Claude Code's own background daemon, for the session unit (MIS-0002-R66): what it
        # hosts, and how to give it the client's own verbs. Both are seams for tests.
        self._hosted = hosted or _harness_hosted_sessions
        self._client = client or _run_client
        self._units: Dict[str, _Runner] = {
            u.name: _Runner(spec=u, since=wall()) for u in declaration.units
        }
        self._tail = _LivenessTail(get_log_path())
        self._own_start: Optional[tuple] = None  # (pid, proc_start) once record_start has run

    # ------------------------------------------------------------------ queries

    def state(self, unit: str) -> State:
        return self._runner(unit).state

    def pid(self, unit: str) -> Optional[int]:
        return self._runner(unit).pid

    def failures(self, unit: str) -> int:
        """Consecutive failures since the unit last ran stably; the restart backoff grows with them."""
        return self._runner(unit).failures

    def statuses(self) -> List[UnitStatus]:
        """Every declared unit as the core sees it now, for the control socket's status."""
        return [UnitStatus(unit=r.spec.name, state=r.state, pid=r.pid if r.proc else None,
                           proc_start=r.proc_start if r.proc else None, since=r.since,
                           restart_held_until=self._restart_held_until(r))
                for r in self._units.values()]

    def _restart_held_until(self, r: _Runner) -> Optional[str]:
        """The end of the quiet window a session's restart waits for, asked or due by its
        policy, or None when nothing waits (MIS-0002-R50 (layer_MUST-NOT_act_in_quiet_window))."""
        if r.spec.kind != "session":
            return None
        window = quiet_window_at(self.declaration, self._wall())
        if window is None:
            return None
        due = r.proc is None and r.want_up and r.restart_at is not None and self._clock() >= r.restart_at
        return window.end if r.held_restart is not None or due else None

    # ------------------------------------------------------------------ acts

    def record_start(self, pid: int, start: str) -> None:
        """Say that this daemon's life began, before any unit is adopted or started, so a
        fold of what the daemon observes can begin from it (``DaemonStart``)."""
        self._own_start = (pid, start)
        self._emit(EVENT_DAEMON_START, DaemonStart(agent=self.card, pid=pid, proc_start=start).model_dump())

    def boot(self) -> None:
        """Start every unit that is not optional, each on its own: one that fails to
        start delays and stops none of the others (MIS-0002-R58
        (optional_unit_MUST-NOT_delay_others)). A unit the previous daemon started that is
        still running is adopted, not started again."""
        carried = self._adopt_survivors()
        for r in self._units.values():
            if r.spec.name in carried:
                continue
            if not r.spec.optional:
                self._control("start", r, POLICY, "declared and not optional")
                r.want_up = True
                self._spawn(r)

    def _adopt_survivors(self) -> set:
        """Adopt each unit whose last recorded state names a process that is still the one
        the record names, and say that it was carried (MIS-0002-R47
        (pd_MUST_report_carried_changed_lost)). The record is this daemon's own event
        log, read back from the newest; a pid whose start time no longer matches belongs to
        another process now, and that unit is started fresh."""
        last: Dict[str, dict] = {}
        # The whole log, archives included: a unit that runs steadily writes no state event,
        # so its last one can sit before a compaction or a rotation. The scan is bounded by
        # meaning instead. Every unit a previous daemon left running has a state event since
        # that daemon's start, its own start or its adoption, so the scan stops there.
        for event in read_events(reverse=True, scope="all", only=(EVENT_STATE, EVENT_DAEMON_START)):
            data = event.get("data") or {}
            if data.get("agent") != self.card:
                continue
            if event.get("event") == EVENT_DAEMON_START:
                if (data.get("pid"), data.get("proc_start")) != self._own_start:
                    break
                continue
            unit = data.get("unit")
            if unit in self._units and unit not in last:
                last[unit] = data
                if len(last) == len(self._units):
                    break
        carried = set()
        for name, data in last.items():
            pid, start = data.get("pid"), data.get("proc_start")
            if data.get("state") not in LIVE_STATES or not pid or not start:
                continue
            if not self._probe(pid, start):
                continue
            r = self._units[name]
            r.proc, r.pid, r.proc_start = _Adopted(pid, start, self._probe), pid, start
            r.started_at = self._clock()
            # Its first liveness under this daemon is judged from the adoption, as a start is,
            # so a unit that went silent while no daemon ran becomes overdue, not running forever.
            r.alive_at = r.started_at
            r.want_up = True
            self._transition(r, data["state"],
                             f"carried from the previous daemon: pid {pid}, its start time confirmed")
            # Its state began with the process, not with this adoption, so a carried unit
            # doesn't read as just restarted.
            r.since = start_epoch(start) or r.since
            carried.add(name)
        return carried

    def start(self, unit: str, asked_by: Asker, reason: str, peer: Optional[Peer] = None) -> None:
        r = self._runner(unit)
        self._control("start", r, asked_by, reason, peer)
        r.want_up = True
        r.restart_at = None
        if r.proc is None:
            self._spawn(r)

    def stop(self, unit: str, asked_by: Asker, reason: str, peer: Optional[Peer] = None) -> None:
        """Stop a unit now. Nothing the unit or its session enforces can hold it
        (MIS-0002-R48 (outside_stop_MUST_override_gates))."""
        r = self._runner(unit)
        self._control("stop", r, asked_by, reason, peer)
        r.want_up = False
        r.restart_at = None
        r.drain = None
        r.then_start = False
        r.held_restart = None  # a stop also ends a restart a quiet window was holding
        if r.proc is not None:
            self._signal_stop(r, f"stopped as asked: {reason}")
        elif r.remnant is not None:
            # An earlier stop's group is still being ended. The unit reads stopped once, when
            # that is done; this act is already recorded above, with who asked (R52).
            if r.stop_pending is None:
                r.stop_pending = f"stopped as asked: {reason}"
        elif r.state != "stopped":
            caught = " (a respawn was in flight; its worker is stopped when the client lists it)" \
                if r.awaiting_respawn is not None else ""
            self._transition(r, "stopped", f"stopped as asked: {reason}{caught}")

    def restart(self, unit: str, asked_by: Asker, reason: str, peer: Optional[Peer] = None) -> None:
        """Restart a unit, once its work in flight has drained or the drain has timed
        out (MIS-0002-R49 (pd_MUST_check_work_in_flight))."""
        r = self._runner(unit)
        window = quiet_window_at(self.declaration, self._wall()) if r.spec.kind == "session" else None
        if window is not None:
            # Recorded now and carried out when the window ends (R50); a stop never waits (R48).
            self._control("restart", r, asked_by, f"{reason} (held: quiet window until {window.end})", peer)
            r.held_restart = (asked_by, reason, peer)
            return
        self._control("restart", r, asked_by, reason, peer)
        r.want_up = True
        if r.proc is None:
            r.restart_at = None
            self._spawn(r)
        elif r.in_flight:
            r.drain = (asked_by, reason, self._clock() + self._drain_timeout)
        elif r.in_flight is None:
            self._begin_restart(r, f"{reason} (it reports no work in flight, so it is taken as idle)")
        else:
            self._begin_restart(r, reason)

    def shutdown(self, reason: str) -> None:
        """Stop every running unit and wait for them, as the daemon itself stops.

        The wait is in real time whatever clock the core was given, because it waits on
        real processes; anything still running when the longest declared grace has passed
        is killed.
        """
        grace = 0.0
        for r in self._units.values():
            r.want_up = False
            r.restart_at = None
            r.drain = None
            r.held_restart = None
            if r.proc is not None:
                self._control("stop", r, POLICY, reason)
                self._signal_stop(r, reason)
                grace = max(grace, r.spec.stop_grace_s)
        deadline = time.monotonic() + grace
        while any(r.proc is not None or r.remnant is not None for r in self._units.values()):
            if time.monotonic() >= deadline:
                for r in self._units.values():
                    if r.proc is not None:
                        self._kill(r, signal.SIGKILL)
                        try:
                            # Bounded: an adopted unit's end is seen only by probing it,
                            # and a process that will not die must not hold the daemon.
                            r.proc.wait(timeout=KILL_WAIT_S)
                        except subprocess.TimeoutExpired:
                            print(f"⚠️ MACF: pd: {r.spec.name} (pid {r.pid}) has not ended "
                                  f"{KILL_WAIT_S:g} s after SIGKILL; leaving it", file=sys.stderr)
                            r.proc = None
                    if r.remnant is not None:
                        # The daemon is going: what is left of a stopped unit is killed now,
                        # if a recorded member still pins its group, and not waited on again.
                        pgid, members = r.remnant[0], r.remnant[1]
                        if any(self._probe(pid, start) for pid, start in members):
                            try:
                                os.killpg(pgid, signal.SIGKILL)
                            except (ProcessLookupError, PermissionError) as e:
                                print(f"⚠️ MACF: pd: cannot signal what is left of {r.spec.name} "
                                      f"(group {pgid}): {e}", file=sys.stderr)
                        self._end_remnant(r, "the rest of its group was killed as the daemon stopped")
            self.tick()
            time.sleep(0.02)

    # ------------------------------------------------------------------ the pass

    def tick(self) -> None:
        """One pass: credit new liveness, reap exits, and act on every timer that is due."""
        now = self._clock()
        for event in self._tail.read():
            self._on_liveness(event, now)
        for r in self._units.values():
            try:
                self._tick_unit(r, now)
            except Exception as e:  # noqa: BLE001 - GUARD, not handler: one unit must not stop the rest
                # Deliberately broad: a GUARD, not a handler. One unit's fault must not
                # stop the others from being supervised; it is announced, never absorbed.
                print(f"⚠️ MACF: pd: supervising {r.spec.name} failed this pass "
                      f"(continuing with the others): {e}", file=sys.stderr)

    def _tick_unit(self, r: _Runner, now: float) -> None:
        if r.remnant is not None:
            self._tick_remnant(r, now)
            if r.remnant is not None:
                return
        if r.proc is None and r.awaiting_respawn is not None:
            self._await_respawn(r, now)
            return
        if r.held_restart is not None and quiet_window_at(self.declaration, self._wall()) is None:
            asked_by, reason, peer = r.held_restart
            r.held_restart = None
            # The asked act itself, by its asker and the process that asked (R52).
            self.restart(r.spec.name, asked_by, f"{reason} (held until a quiet window ended)", peer=peer)
            return
        if r.proc is not None:
            code = r.proc.poll()
            if code is not None:
                self._on_exit(r, code, now)
                return
            if r.kill_at is not None and now >= r.kill_at:
                if r.client_session and not r.client_escalated:
                    # The client accepted the stop and the worker outlived the grace: an outside
                    # stop must still stop (R48), so signals follow, as for a refused stop.
                    print(f"⚠️ MACF: pd: session {r.client_session[:8]} still runs "
                          f"{r.spec.stop_grace_s:g} s after the client's stop; signalling it", file=sys.stderr)
                    r.client_escalated = True
                    self._kill(r, signal.SIGTERM)
                    r.kill_at = now + r.spec.stop_grace_s
                    return
                self._kill(r, signal.SIGKILL)
                r.kill_at = None
                return
            if r.stopping is None:
                self._check_liveness(r, now)
            if r.drain is not None and r.stopping is None:
                _, reason, deadline = r.drain
                if not r.in_flight:
                    r.drain = None
                    self._begin_restart(r, f"{reason} (work in flight drained)")
                elif now >= deadline:
                    r.drain = None
                    self._begin_restart(
                        r, f"{reason} (work in flight did not drain in {self._drain_timeout:g} s)")
            return
        if r.want_up and r.restart_at is not None and now >= r.restart_at:
            if r.spec.kind == "session" and quiet_window_at(self.declaration, self._wall()) is not None:
                return  # the session's restart waits for the window's end (R50)
            r.restart_at = None
            self._control("start", r, POLICY,
                          f"restart policy {r.spec.restart} after failure {r.failures}")
            self._spawn(r)

    def _check_liveness(self, r: _Runner, now: float) -> None:
        if r.state == "waiting_on_a_person":
            # Silence while a person is awaited is not death, and waiting is never a
            # reason to restart (MIS-0002-R22 (layer_MUST-NOT_restart_waiting_unit)).
            return
        if r.state == "starting":
            bound = LIVENESS_TOLERANCE * r.spec.liveness_interval_s
            if now - r.started_at > bound:
                self._fail(r, f"no liveness from pid {r.pid} within {bound:g} s of its start")
            return
        if r.state == "running" and r.alive_at is not None:
            interval = r.alive_interval_s or r.spec.liveness_interval_s
            bound = LIVENESS_TOLERANCE * interval
            age = now - r.alive_at
            if age > bound:
                self._fail(r, f"liveness stale: the last was {age:.1f} s ago, "
                              f"against an interval of {interval:g} s")
                return
            if r.failures and now - r.started_at >= STABLE_INTERVALS * interval:
                r.failures = 0

    # ------------------------------------------------------------------ events in

    def _on_liveness(self, event: dict, now: float) -> None:
        data = dict(event.get("data") or {})
        if data.get("agent") != self.card:
            return
        r = self._units.get(data.get("unit"))
        if r is None:
            return  # not a unit of this declaration (MIS-0002-R07)
        try:
            live = Liveness.model_validate(data)
        except ValidationError as e:
            self._tail.unreadable += 1
            print(f"⚠️ MACF: pd: liveness for {r.spec.name} is unreadable (not credited): {e}",
                  file=sys.stderr)
            return
        # Credit only the incarnation this core started: a pid alone can be recycled
        # (MIS-0002-R15 (readout_MUST_probe_liveness)).
        if live.pid != r.pid or proc_start_key(live.proc_start) != proc_start_key(r.proc_start):
            return
        if r.stopping is not None:
            return
        r.alive_at = now
        r.alive_interval_s = live.interval_s
        r.in_flight = live.in_flight
        if live.waiting_on:
            if r.state != "waiting_on_a_person":
                self._transition(r, "waiting_on_a_person", f"waiting on {live.waiting_on}")
        elif r.state == "waiting_on_a_person":
            self._transition(r, "running", "no longer waiting on a person")
        elif r.state == "starting":
            self._transition(r, "running", "first liveness from this incarnation")

    def _on_exit(self, r: _Runner, code: int, now: float) -> None:
        why = _describe_exit(code)
        stopping = r.stopping
        if stopping is not None and r.kill_at is not None and r.pid is not None:
            # A stop this core sent reaped the leader before its deadline. A member of the
            # unit's group that ignored SIGTERM is still the unit's, and the stop must reach it
            # (persistent_layer 10.2): keep the deadline for the group, not just the leader.
            # A member that forks and exits while the group is read can leave this first
            # listing empty, read before its replacement appeared and after it ended; the
            # second listing starts after the first ends, so it sees the replacement (#639 review).
            members = group_members(r.pid) or group_members(r.pid)
            if members:
                r.remnant = (r.pid, members, r.kill_at, None)
        # An asked restart is half done when the old incarnation exits, whether this
        # core stopped it or it exited while the restart waited on its work in flight.
        asked_restart = r.then_start or r.drain is not None
        r.proc, r.kill_at, r.stopping, r.then_start, r.drain = None, None, None, False, None
        r.alive_at, r.in_flight = None, None

        if stopping is None:
            # It exited on its own: record how.
            if code in r.spec.exit_codes.no_restart:
                self._transition(r, "stopped", f"{why}, which asks not to be restarted")
                if not asked_restart:
                    r.want_up = False
                    return
            elif code in r.spec.exit_codes.success:
                self._transition(r, "stopped", why)
            else:
                r.failures += 1
                self._transition(r, "failed", why)
        elif not r.want_up or r.state != "failed":
            # A stop this core sent. After a liveness failure the unit is already
            # recorded failed, and stays so unless the stop was asked for. While members of
            # its group outlive the leader, the unit has not stopped: the transition waits
            # for the group to end, so no reader is told the stop is done while it isn't.
            if r.remnant is not None:
                r.stop_pending = f"{stopping} ({why})"
            else:
                self._transition(r, "stopped", f"{stopping} ({why})")

        if not r.want_up:
            return
        if asked_restart:
            self._spawn(r)
        elif r.state == "failed" and r.spec.restart in ("always", "on-failure"):
            r.restart_at = now + backoff_s(r.failures, *self._backoff)
        elif r.state == "stopped" and r.spec.restart == "always":
            r.restart_at = now + self._backoff[0]

    # ------------------------------------------------------------------ helpers

    def _runner(self, unit: str) -> _Runner:
        try:
            return self._units[unit]
        except KeyError:
            raise KeyError(
                f"{unit} is not a unit of this agent's declaration "
                "(MIS-0002-R07 (pd_MUST-NOT_control_other_agents))") from None

    def _from_client(self, r: _Runner) -> bool:
        """For the session unit, give Claude Code's own daemon the first say, and return
        True when it took the unit, so nothing is spawned (MIS-0002-R66
        (pd_MUST_adopt_harness_supervisor)).

        A session the client hosted before is respawned by the client, under the same
        session id; if the client can no longer respawn it, it is decided afresh. A
        session the client hosts in the agent home is adopted, and two or more are
        refused, because picking one is a guess the operator makes (``client_daemon.decide``).
        """
        from macf.utils.client_daemon import ADOPT, REFUSE, client_command, decide
        if r.spec.kind != "session":
            return False
        respawned = False
        if r.client_session:
            if not self._find_client(r):
                return True
            out = self._client(client_command("start", r.client_session, claude=r.client_binary))
            if out.returncode != 0:
                print(f"⚠️ MACF: pd: the client could not respawn session {r.client_session[:8]} "
                      f"({(out.stderr or out.stdout or '').strip()[:200]}); deciding again", file=sys.stderr)
                r.client_session = None
            else:
                respawned = True
        try:
            hosted = self._hosted()
        except OSError as e:
            print(f"⚠️ MACF: pd: what the client hosts is unreadable ({e}); starting the session unit itself",
                  file=sys.stderr)
            return False
        if r.client_session:
            # Respawned under the same id: adopt whichever worker now carries it. The client
            # may list it a little later, so a respawn it accepted is waited for across passes;
            # starting the unit now would put a second session beside the client's.
            hosted = [h for h in hosted if h.session_id == r.client_session]
            if not hosted and respawned:
                r.awaiting_respawn = self._clock() + RESPAWN_WAIT_S
                r.proc, r.pid, r.proc_start = None, None, None
                self._transition(r, "starting", f"respawned by the client; waiting for session "
                                                f"{r.client_session[:8]}'s worker")
                return True
            if not hosted:
                r.client_session = None
                return False
        decision = decide(r.spec, hosted, Path(self._placeholders.get("agent_home", "")))
        if decision.action == REFUSE:
            r.want_up = False
            r.proc, r.pid, r.proc_start = None, None, None
            self._transition(r, "failed", f"not started: {decision.reason}")
            return True
        if decision.action != ADOPT:
            return False
        if not self._find_client(r):
            return True       # a hosted session exists: starting the unit's own would double it
        start = proc_start(decision.pid)
        if not start:
            return False   # the worker ended between the readout and now: start the unit as usual
        r.proc, r.pid, r.proc_start = _Adopted(decision.pid, start, self._probe), decision.pid, start
        r.client_session = decision.session_id
        r.started_at = self._clock()
        # The client's daemon supervises it, so its liveness is its process, probed by pid
        # and start time; it writes no liveness of its own for a stale check to judge.
        r.alive_at, r.alive_interval_s, r.in_flight = None, None, None
        self._transition(r, "running", f"adopted: {decision.reason} (session {decision.session_id[:8]}, "
                                       f"pid {decision.pid})")
        r.since = start_epoch(start) or r.since
        return True

    def _spawn(self, r: _Runner) -> None:
        """Start the unit as this process's child, with the declared environment and
        nothing inherited (MIS-0002-R12 (pd_MUST_start_units_itself)), read from the
        declaration at this start rather than from anything a volume carried forward
        (MIS-0002-R13 (pd_MUST_render_env_at_start)). The placeholders a declaration may
        use, the agent home, the card and the runtime directory, are filled in here from
        the daemon's own values, because the same agent's home differs between a host and a
        container. While the previous incarnation's group still has members, the start
        waits for them, so two copies never run side by side. The session unit asks Claude
        Code's own daemon first (``_from_client``)."""
        if r.remnant is not None:
            r.start_after_remnant = True
            return
        if self._from_client(r):
            return
        try:
            command = [render(a, self._placeholders) for a in r.spec.command]
            env = {k: render(v, self._placeholders) for k, v in r.spec.environment.items()}
        except KeyError as e:
            r.proc, r.pid, r.proc_start = None, None, None
            r.want_up = False
            self._transition(r, "failed", f"could not start: no value for the placeholder {{{e.args[0]}}}")
            return
        try:
            proc = subprocess.Popen(
                command,
                env=env,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as e:
            r.proc, r.pid, r.proc_start = None, None, None
            r.failures += 1
            self._transition(r, "failed", f"could not start: {e}")
            if r.want_up and r.spec.restart in ("always", "on-failure"):
                r.restart_at = self._clock() + backoff_s(r.failures, *self._backoff)
            return
        r.proc, r.pid = proc, proc.pid
        r.proc_start = proc_start(proc.pid)
        r.started_at = self._clock()
        r.alive_at, r.alive_interval_s, r.in_flight = None, None, None
        self._transition(r, "starting", f"started as pid {proc.pid}")

    def _tick_remnant(self, r: _Runner, now: float) -> None:
        """Members of a stopped unit's group that outlived its leader. A member still the
        process recorded, by pid and start time, keeps the group's id from being reused, so
        at the stop's deadline a SIGKILL to the group reaches only the unit's processes. If no
        recorded member is left, the pids may be others' now and nothing is signalled.

        A member that has ended but not been reaped still answers the probe. Where something
        reaps orphans promptly (tini in the images, systemd on a host) that is brief; if the
        daemon were ever PID 1 itself, such a zombie would hold the remnant until KILL_WAIT_S."""
        pgid, members, kill_at, killed_at = r.remnant
        live = [(pid, start) for pid, start in members if self._probe(pid, start)]
        if not live and not _pid_in_use(pgid):
            # Every recorded member is gone, but one may have forked and exited between two
            # passes, as a wrapper running `cmd &` does. While no process holds the group's id
            # as its pid, the id can't have been given to another group, so whatever is still
            # in the group is the unit's (#639 review).
            live = group_members(pgid)
        if not live:
            self._end_remnant(r, "the rest of its group was killed at the stop's deadline"
                              if killed_at is not None else "the rest of its group ended")
            return
        if killed_at is None and now >= kill_at:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # emptied between the probe and the signal
            except PermissionError as e:
                print(f"⚠️ MACF: pd: cannot signal what is left of {r.spec.name} (group {pgid}): {e}",
                      file=sys.stderr)
            r.remnant = (pgid, live, kill_at, now)
        elif killed_at is not None and now - killed_at >= KILL_WAIT_S:
            print(f"⚠️ MACF: pd: {len(live)} process(es) of {r.spec.name}'s group {pgid} have not ended "
                  f"{KILL_WAIT_S:g} s after SIGKILL; leaving them", file=sys.stderr)
            self._end_remnant(r, f"{len(live)} process(es) of its group outlived SIGKILL and were left")
        else:
            r.remnant = (pgid, live, kill_at, killed_at)

    def _end_remnant(self, r: _Runner, how: str) -> None:
        r.remnant = None
        if r.stop_pending is not None:
            reason, r.stop_pending = r.stop_pending, None
            self._transition(r, "stopped", f"{reason}; {how}")
        if r.start_after_remnant:
            r.start_after_remnant = False
            if r.want_up and r.proc is None:
                self._spawn(r)

    def _begin_restart(self, r: _Runner, reason: str) -> None:
        r.then_start = True
        self._signal_stop(r, f"stopped to restart: {reason}")

    def _fail(self, r: _Runner, reason: str) -> None:
        """A unit that is running but not working: record it failed, then stop what is
        left of it so the restart policy can act on the exit."""
        r.failures += 1
        self._transition(r, "failed", reason)
        self._signal_stop(r, reason)

    def _signal_stop(self, r: _Runner, reason: str) -> None:
        """SIGTERM now, and SIGKILL once the unit's own declared grace has passed, so a
        unit that flushes a spool can be given longer than one that holds nothing
        (MIS-0002-R48 (outside_stop_MUST_override_gates)).

        A session the client hosts is stopped with the client's own ``claude stop``, which
        keeps its conversation for a respawn; a signalled worker ends as done and nothing
        brings it back. Only when the client refuses does the stop fall back to signals,
        because an outside stop must still stop."""
        r.stopping = reason
        if r.client_session:
            from macf.utils.client_daemon import client_command
            out = self._client(client_command("stop", r.client_session, claude=r.client_binary or "claude"))
            if out.returncode == 0:
                r.client_escalated = False
                r.kill_at = self._clock() + r.spec.stop_grace_s   # escalates if the worker outlives it
                return
            print(f"⚠️ MACF: pd: the client could not stop session {r.client_session[:8]} "
                  f"({(out.stderr or out.stdout or '').strip()[:200]}); signalling it", file=sys.stderr)
        self._kill(r, signal.SIGTERM)
        r.kill_at = self._clock() + r.spec.stop_grace_s

    def _find_client(self, r: _Runner) -> bool:
        """Find ``claude`` on the session unit's own declared PATH, the environment the
        session runs in (MIS-0002-R12), else the daemon's. An installed daemon gets its
        service manager's PATH, launchd's /usr/bin:/bin:/usr/sbin:/sbin on macOS, where the
        client is rarely found. A client that cannot be found is not a client that refused:
        the unit is recorded failed with the binary and the PATH searched, nothing is
        signalled, and the hosted session is left alone."""
        import shutil
        try:
            declared = render(r.spec.environment["PATH"], self._placeholders) if "PATH" in r.spec.environment else None
        except KeyError:
            declared = None
        path = declared or os.environ.get("PATH", os.defpath)
        found = shutil.which("claude", path=path)
        if found:
            r.client_binary = found
            return True
        r.want_up = False
        r.proc, r.pid, r.proc_start = None, None, None
        where = "the session unit's declared PATH" if declared else "the daemon's PATH"
        self._transition(r, "failed", f"not adopted: claude is not on {where} ({path}); declare a PATH "
                                      f"that holds it in the session unit's environment")
        return False

    def _await_respawn(self, r: _Runner, now: float) -> None:
        """Adopt the respawned worker once the client lists it; past the deadline, decide afresh."""
        try:
            listed = [h for h in self._hosted() if h.session_id == r.client_session]
        except OSError as e:
            print(f"⚠️ MACF: pd: what the client hosts is unreadable ({e}); still waiting", file=sys.stderr)
            listed = []
        if not r.want_up:
            # A stop landed while the respawn was in flight. The worker the client brings up is
            # adopted only to be stopped through the client, with the grace escalation (R48).
            start = proc_start(listed[0].pid) if listed else None
            if start:
                r.awaiting_respawn = None
                r.proc, r.pid, r.proc_start = _Adopted(listed[0].pid, start, self._probe), listed[0].pid, start
                self._signal_stop(r, "stopped as asked while its respawn was in flight")
            elif now >= r.awaiting_respawn:
                r.awaiting_respawn = None
            return
        if listed or now >= r.awaiting_respawn:
            if not listed:
                print(f"⚠️ MACF: pd: session {r.client_session[:8]}'s respawned worker was not listed "
                      f"within {RESPAWN_WAIT_S:g} s; deciding again", file=sys.stderr)
                r.client_session = None
            r.awaiting_respawn = None
            self._spawn(r)

    def _kill(self, r: _Runner, sig: signal.Signals) -> None:
        if r.pid is None:
            return
        if isinstance(r.proc, _Adopted) and not self._probe(r.pid, r.proc_start or ""):
            # Not this daemon's child, so its pid may have ended and been reused since the last
            # pass. Signal only the process adopted, by pid and start time (MIS-0002-R15
            # (readout_MUST_probe_liveness)); its end is seen on the next pass.
            print(f"⚠️ MACF: pd: {r.spec.name}'s adopted pid {r.pid} is no longer the process "
                  f"adopted; not signalling it", file=sys.stderr)
            return
        try:
            # A unit this daemon started leads its own group; a worker the client hosts may not,
            # and killpg on a pid that leads no group reaches nothing.
            if os.getpgid(r.pid) != r.pid:
                os.kill(r.pid, sig)
                return
            os.killpg(r.pid, sig)
        except ProcessLookupError:
            pass  # already gone; the exit is reaped on the next pass
        except PermissionError as e:
            if r.proc is not None and r.proc.poll() is not None:
                return  # exited and not yet reaped: macOS refuses to signal a group of zombies
            print(f"⚠️ MACF: pd: cannot signal {r.spec.name} (pid {r.pid}): {e}", file=sys.stderr)

    def _transition(self, r: _Runner, state: State, reason: str) -> None:
        r.state = state
        r.since = self._wall()
        self._emit(EVENT_STATE, UnitState(
            agent=self.card, unit=r.spec.name, state=state,
            pid=r.pid, proc_start=r.proc_start, reason=reason,
        ).model_dump())

    def _control(self, act: str, r: _Runner, asked_by: Asker, reason: str,
                 peer: Optional[Peer] = None) -> None:
        """Every act names who asked and why (MIS-0002-R52 (control_act_MUST_name_who_asked)):
        the asker as claimed, and for an act asked over the control socket the process the
        kernel says asked. The record is built before the act, so an operator's act that
        comes with no observed peer raises here and nothing is done."""
        self._emit(EVENT_CONTROL, Control(
            agent=self.card, act=act, unit=r.spec.name, asked_by=asked_by, peer=peer, reason=reason,
        ).model_dump())

    @staticmethod
    def _emit(event: str, data: dict) -> None:
        if not append_event(event, data):
            print(f"⚠️ MACF: pd: the {event} event was not recorded: {data}", file=sys.stderr)
