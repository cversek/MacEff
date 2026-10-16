"""A unit's own liveness, written by the unit: MIS-0002-R14 (unit_MUST_emit_liveness_events).

A process that merely exists says nothing about whether its work loop runs, so a unit
writes a ``pd_unit_alive`` event at its declared interval, and its primal daemon credits
it only when the event names the incarnation the daemon started (pid and start time,
MIS-0002-R15 (readout_MUST_probe_liveness)). Without these events a unit reads
``starting`` for as long as it runs.

A unit learns which unit it is, and how often to report, from its declaration's
environment, the only environment a unit gets (MIS-0002-R12, R13): ``MACF_PD_UNIT`` and
``MACF_PD_LIVENESS_S``, next to ``MACEFF_AGENT_HOME_DIR``. A process started any other way
has none of them, and ``heartbeat_from_env`` then does nothing, so the same program runs
with or without a daemon.
"""
import os
import sys
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional

from macf.agent_events_log import append_event
from macf.notify.session import proc_start
from macf.pd.interface import EVENT_LIVENESS, IdentityError, Liveness, agent_card

ENV_UNIT = "MACF_PD_UNIT"
ENV_INTERVAL = "MACF_PD_LIVENESS_S"
ENV_HOME = "MACEFF_AGENT_HOME_DIR"
#: The session unit's identity, handed by its wrapper (``pd.session_unit``) to the
#: session's transcript monitor, which reports liveness for it naming the wrapper's pid.
#: Names of their own, so that no other process the session starts, which inherits them,
#: can take them for its own unit.
ENV_SESSION_UNIT = "MACF_PD_SESSION_UNIT"
ENV_SESSION_INTERVAL = "MACF_PD_SESSION_LIVENESS_S"
ENV_SESSION_PID = "MACF_PD_SESSION_PID"


def liveness_event(card: str, unit: str, interval_s: float,
                   in_flight: Optional[int] = None, pid: Optional[int] = None) -> Liveness:
    """The liveness of process *pid* (this process by default) as the named unit of *card*."""
    pid = pid or os.getpid()
    return Liveness(agent=card, unit=unit, pid=pid, proc_start=proc_start(pid) or "unknown",
                    interval_s=interval_s, in_flight=in_flight)


def emit(card: str, unit: str, interval_s: float, in_flight: Optional[int] = None,
         append: Optional[Callable[[str, dict], bool]] = None, pid: Optional[int] = None) -> bool:
    """Write one liveness event for *pid* (this process by default); True when the log took it."""
    append = append or append_event
    return append(EVENT_LIVENESS, liveness_event(card, unit, interval_s, in_flight, pid).model_dump())


class Heartbeat:
    """Emits liveness for a work loop that calls ``tick`` once per pass, until ``stop``.

    A beat follows a pass, not the clock: each interval it writes only when the loop has
    ticked since the last beat, so a loop that wedges stops the events and the daemon
    sees the unit go overdue (MIS-0002-R14, R18). A thread on its own timer would keep
    writing while the loop it speaks for is stuck. The first beat goes out on the first
    tick, so the unit reads alive as soon as its loop has passed once. A loop that can
    block for longer than its interval, on a quiet socket say, needs a timeout so that it
    passes at least once per interval: that is the unit's contract with its daemon."""

    def __init__(self, card: str, unit: str, interval_s: float,
                 in_flight: Optional[Callable[[], Optional[int]]] = None,
                 append: Optional[Callable[[str, dict], bool]] = None,
                 pid: Optional[int] = None):
        # pid: the unit's process when the beat speaks for another one (the session
        # unit's wrapper, from its transcript monitor); this process by default.
        self.card, self.unit, self.interval_s, self.pid = card, unit, interval_s, pid
        self._in_flight = in_flight or (lambda: None)
        self._append = append
        self._stop = threading.Event()
        self._ticked = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"pd-liveness-{unit}", daemon=True)

    def start(self) -> "Heartbeat":
        self._thread.start()
        return self

    def tick(self) -> None:
        """The work loop has passed once. Cheap enough to call on every pass."""
        self._ticked.set()

    def stop(self) -> None:
        """Stop, and return only once no beat can follow: a beat already past its stop
        check finishes first, so nothing is written for a loop that has ended."""
        self._stop.set()
        self._ticked.set()
        if self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        stalled = False
        while True:
            if not self._ticked.wait(self.interval_s):
                if not stalled:
                    print(f"⚠️ MACF: pd: {self.unit}'s loop has not passed in {self.interval_s:g} s, "
                          f"so no liveness is written until it does", file=sys.stderr)
                    stalled = True
                continue
            if self._stop.is_set():
                return
            self._ticked.clear()
            stalled = False
            if not emit(self.card, self.unit, self.interval_s, self._in_flight(), self._append, self.pid):
                print(f"⚠️ MACF: pd: liveness for {self.unit} was not recorded (the unit will read "
                      f"overdue if this persists)", file=sys.stderr)
            if self._stop.wait(self.interval_s):
                return


def heartbeat_from_env(in_flight: Optional[Callable[[], Optional[int]]] = None,
                       environ=os.environ,
                       append: Optional[Callable[[str, dict], bool]] = None) -> Optional[Heartbeat]:
    """Start a heartbeat when this process runs as a declared unit, else return None. The
    caller's work loop calls ``tick`` on the result once per pass; nothing is written until
    it does.

    Runs as a unit when the environment names the unit, its interval and the agent home.
    A partial or malformed setting is reported on stderr and no heartbeat starts: liveness
    for the wrong unit or agent would be worse than none, since the daemon reads it."""
    found = unit_from_env(environ)
    if found is None:
        return None
    return Heartbeat(found.card, found.unit, found.interval_s, in_flight, append).start()


@dataclass(frozen=True)
class DeclaredUnit:
    card: str
    unit: str
    interval_s: float
    pid: Optional[int] = None


def unit_from_env(environ=os.environ) -> Optional[DeclaredUnit]:
    """The unit this process runs as, when this process runs as a declared unit; None when the
    environment names no unit at all. A partial or malformed setting is reported on stderr
    and read as None, because liveness for the wrong unit or agent would be worse than none."""
    unit, raw, home = environ.get(ENV_UNIT), environ.get(ENV_INTERVAL), environ.get(ENV_HOME)
    if not unit and not raw:
        return None
    try:
        interval = float(raw or "")
        if interval <= 0 or not unit or not home:
            raise ValueError("needs a unit name, a positive interval and the agent home")
        return DeclaredUnit(agent_card(Path(home)), unit, interval)
    except (ValueError, IdentityError) as e:
        print(f"⚠️ MACF: pd: no liveness from this unit ({ENV_UNIT}={unit!r}, "
              f"{ENV_INTERVAL}={raw!r}): {e}", file=sys.stderr)
        return None


def session_unit_from_env(environ=os.environ) -> Optional[DeclaredUnit]:
    """The session unit a transcript monitor reports for, from what the session unit's
    wrapper put in the session's environment; None outside such a session. A partial or
    malformed setting is reported and read as None, as ``unit_from_env`` does."""
    unit, raw, pid, home = (environ.get(ENV_SESSION_UNIT), environ.get(ENV_SESSION_INTERVAL),
                            environ.get(ENV_SESSION_PID), environ.get(ENV_HOME))
    if not unit and not raw and not pid:
        return None
    try:
        interval, owner = float(raw or ""), int(pid or "")
        if interval <= 0 or owner <= 1 or not unit or not home:
            raise ValueError("needs a unit name, a positive interval, the unit's pid and the agent home")
        return DeclaredUnit(agent_card(Path(home)), unit, interval, owner)
    except (ValueError, IdentityError) as e:
        print(f"⚠️ MACF: pd: no session liveness from this monitor ({ENV_SESSION_UNIT}={unit!r}, "
              f"{ENV_SESSION_INTERVAL}={raw!r}, {ENV_SESSION_PID}={pid!r}): {e}", file=sys.stderr)
        return None


def session_heartbeat_from_env(environ=os.environ,
                               append: Optional[Callable[[str, dict], bool]] = None) -> Optional[Heartbeat]:
    """Start the session unit's heartbeat in its transcript monitor, else return None.
    The beat names the wrapper's pid, so the daemon credits it to the process it started."""
    found = session_unit_from_env(environ)
    if found is None:
        return None
    return Heartbeat(found.card, found.unit, found.interval_s, append=append, pid=found.pid).start()
