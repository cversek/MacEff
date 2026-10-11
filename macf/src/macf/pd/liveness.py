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
from typing import Callable, Optional

from macf.agent_events_log import append_event
from macf.notify.session import proc_start
from macf.pd.interface import EVENT_LIVENESS, IdentityError, Liveness, agent_card

ENV_UNIT = "MACF_PD_UNIT"
ENV_INTERVAL = "MACF_PD_LIVENESS_S"
ENV_HOME = "MACEFF_AGENT_HOME_DIR"


def liveness_event(card: str, unit: str, interval_s: float,
                   in_flight: Optional[int] = None) -> Liveness:
    """This process's liveness as the named unit of the agent *card*."""
    pid = os.getpid()
    return Liveness(agent=card, unit=unit, pid=pid, proc_start=proc_start(pid) or "unknown",
                    interval_s=interval_s, in_flight=in_flight)


def emit(card: str, unit: str, interval_s: float, in_flight: Optional[int] = None,
         append: Optional[Callable[[str, dict], bool]] = None) -> bool:
    """Write one liveness event; True when the log took it."""
    append = append or append_event
    return append(EVENT_LIVENESS, liveness_event(card, unit, interval_s, in_flight).model_dump())


class Heartbeat:
    """Emits liveness every *interval_s* from a daemon thread until ``stop``. The first event
    goes out at once, so the unit reads alive as soon as its loop has started."""

    def __init__(self, card: str, unit: str, interval_s: float,
                 in_flight: Optional[Callable[[], Optional[int]]] = None,
                 append: Optional[Callable[[str, dict], bool]] = None):
        self.card, self.unit, self.interval_s = card, unit, interval_s
        self._in_flight = in_flight or (lambda: None)
        self._append = append
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"pd-liveness-{unit}", daemon=True)

    def start(self) -> "Heartbeat":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while True:
            if not emit(self.card, self.unit, self.interval_s, self._in_flight(), self._append):
                print(f"⚠️ MACF: pd: liveness for {self.unit} was not recorded (the unit will read "
                      f"overdue if this persists)", file=sys.stderr)
            if self._stop.wait(self.interval_s):
                return


def heartbeat_from_env(in_flight: Optional[Callable[[], Optional[int]]] = None,
                       environ=os.environ,
                       append: Optional[Callable[[str, dict], bool]] = None) -> Optional[Heartbeat]:
    """Start a heartbeat when this process runs as a declared unit, else return None.

    Runs as a unit when the environment names the unit, its interval and the agent home.
    A partial or malformed setting is reported on stderr and no heartbeat starts: liveness
    for the wrong unit or agent would be worse than none, since the daemon reads it."""
    unit, raw, home = environ.get(ENV_UNIT), environ.get(ENV_INTERVAL), environ.get(ENV_HOME)
    if not unit and not raw:
        return None
    try:
        interval = float(raw or "")
        if interval <= 0 or not unit or not home:
            raise ValueError("needs a unit name, a positive interval and the agent home")
        card = agent_card(Path(home))
    except (ValueError, IdentityError) as e:
        print(f"⚠️ MACF: pd: no liveness from this unit ({ENV_UNIT}={unit!r}, "
              f"{ENV_INTERVAL}={raw!r}): {e}", file=sys.stderr)
        return None
    return Heartbeat(card, unit, interval, in_flight, append).start()
