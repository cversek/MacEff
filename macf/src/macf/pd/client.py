"""Asking an agent's primal daemon, and reading its units from the event log when no
daemon can be believed.

A daemon is believed only after it is checked. Its record must name a live process by
pid and start time, and the process answering on the control socket must be that pid, as
the kernel reports it. That is the check the MacEff channel makes before it trusts its
peer (MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)). A socket file alone proves
nothing: any process of the same user can bind the path while the daemon is down.
"""
import json
import socket
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, List, Optional

from pydantic import ValidationError

from macf.agent_events_log import read_events
from macf.notify.session import verify_incarnation
from macf.pd.core import DeclarationRefused, load_declaration
from macf.pd.health import SCHEDULE_EVENTS, UNHEALTHY_RUNS, health, schedule_health
from macf.pd.interface import (
    EVENT_DAEMON_START,
    EVENT_LIVENESS,
    EVENT_STATE,
    DaemonRecord,
    Declaration,
    Response,
    control_socket,
    declaration_path,
    record_path,
)
from macf.pd.scheduler import EVENT_DONE, EVENT_NOT_RUN, EVENT_SEEN, EVENT_STARTED
from macf.platform.tray_host import TrayHost, tray_host
from macf.utils.peercred import peer_credentials

#: How long a client waits for the daemon to connect and reply.
REPLY_TIMEOUT_S = 5.0

#: The longest reply read; a longer one is refused rather than buffered.
MAX_REPLY_BYTES = 1024 * 1024


class DaemonUnavailable(RuntimeError):
    """No daemon of this agent can be believed: none is recorded, its record is stale, the
    socket is answered by another process, or its reply cannot be read."""


def ask(card: str, request: dict, *, base: Optional[Path] = None,
        timeout: float = REPLY_TIMEOUT_S) -> Response:
    """Send one request to the agent's daemon, after checking that the process answering is
    the daemon its record names, and return the daemon's reply."""
    path = record_path(card, base)
    try:
        daemon = DaemonRecord.model_validate_json(path.read_text())
    except (OSError, ValidationError) as e:
        raise DaemonUnavailable(f"no usable daemon record at {path}: {e}") from e
    if not verify_incarnation(daemon.pid, daemon.proc_start):
        raise DaemonUnavailable(f"the record names pid {daemon.pid}, which is no longer that daemon")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        try:
            conn.connect(str(control_socket(card, base)))
            answering = peer_credentials(conn).pid
            if answering != daemon.pid:
                raise DaemonUnavailable(
                    f"the control socket is answered by pid {answering}, not the recorded "
                    f"daemon's pid {daemon.pid}")
            conn.sendall(json.dumps(request).encode() + b"\n")
            reply = _read_line(conn)
        except OSError as e:
            raise DaemonUnavailable(f"the daemon did not answer: {e}") from e
    try:
        return Response.model_validate_json(reply)
    except ValidationError as e:
        raise DaemonUnavailable(f"the daemon's reply could not be read: {e}") from e


def _read_line(conn: socket.socket) -> bytes:
    data = b""
    while b"\n" not in data:
        if len(data) > MAX_REPLY_BYTES:
            raise OSError(f"the reply is longer than {MAX_REPLY_BYTES} bytes")
        chunk = conn.recv(65536)
        if not chunk:
            break
        data += chunk
    return data.split(b"\n", 1)[0]


@dataclass(frozen=True, kw_only=True)
class StatusReport:
    """The agent's units, and where the answer came from: ``daemon``, ``event log``, or
    ``none`` when the agent declares no daemon. ``why`` says how that source was chosen.
    ``tray`` is the readout's line on whether this host can show the tray, and why not
    (MIS-0002-R73 (readout_MUST_say_tray_unavailable)); it is the host's answer, so it is
    given whatever the source.

    ``schedules`` is each declared schedule's runs owed and done, derived from the event log
    whatever the source (MIS-0002-R17 (readout_MUST_derive_health_from_runs)). ``runs`` is the
    daemon's health by those runs: ``unhealthy`` when a run it owes is overdue or failed while
    it answers, which is how it is known alive (MIS-0002-R18 (overdue_run_MUST_read_unhealthy)),
    ``healthy`` when none is, and empty when no daemon answered."""

    card: str
    source: str
    why: str
    units: List[dict] = field(default_factory=list)
    tray: str = ""
    schedules: List[dict] = field(default_factory=list)
    runs: str = ""


def status(home: Path, card: str, *, base: Optional[Path] = None,
           now: Optional[float] = None,
           host: Optional[Callable[[], TrayHost]] = None) -> StatusReport:
    """Each declared unit as the daemon reports it, or as the event log shows it when no
    daemon can be believed, with whether this host can show the tray."""
    when = time.time() if now is None else now
    report = _units(home, card, base=base, now=when)
    if report.source != "none":
        report = _with_runs(report, home, card, when)
    return replace(report, tray=(host or tray_host)().said())


def _with_runs(report: StatusReport, home: Path, card: str, now: float) -> StatusReport:
    try:
        declaration = load_declaration(home, card)
    except DeclarationRefused:
        return report  # noqa: MACEFF003 - the units' readout already says why it can't be used
    if not declaration.schedules:
        return report
    found = schedule_health(declaration, _schedule_events(declaration, card), now)
    bad = [f"{h.schedule} {h.verdict}" for h in found if h.verdict in UNHEALTHY_RUNS]
    runs = ""
    if report.source == "daemon":
        runs = ("unhealthy: " + ", ".join(bad)) if bad else "healthy"
    return replace(report, schedules=[h.model_dump() for h in found], runs=runs)


def _units(home: Path, card: str, *, base: Optional[Path] = None,
           now: Optional[float] = None) -> StatusReport:
    path = declaration_path(home)
    if not path.exists():
        return StatusReport(card=card, source="none",
                            why=f"no declaration at {path}, so this agent has no primal daemon")
    try:
        reply = ask(card, {"op": "status"}, base=base)
    except DaemonUnavailable as e:
        try:
            declaration = load_declaration(home, card)
        except DeclarationRefused as refused:
            return StatusReport(card=card, source="none",
                                why=f"no daemon can be asked ({e}), and the declaration cannot be used: {refused}")
        units = [h.model_dump() for h in health(declaration, _last_unit_events(declaration, card),
                                                time.time() if now is None else now)]
        return StatusReport(card=card, source="event log", why=f"no daemon can be asked: {e}",
                            units=units)
    if not reply.ok:
        return StatusReport(card=card, source="daemon", why=f"the daemon refused: {reply.error}")
    return StatusReport(card=card, source="daemon", why="its record and its socket agree",
                        units=[u.model_dump() for u in reply.units or []])


def _schedule_events(declaration: Declaration, card: str) -> List[dict]:
    """The scheduler's events for this agent, newest first, reading back until each declared
    schedule has its newest start and end, or the sighting before its first run; whatever is
    older can't change what is owed now. The daemon's newest start comes with them, since it
    says which not-run records are the current daemon's (#735)."""
    wanted = {s.name for s in declaration.schedules}
    found: List[dict] = []
    kinds: Dict[str, set] = {name: set() for name in wanted}
    booted: Optional[float] = None
    for event in read_events(reverse=True, scope="all", only=SCHEDULE_EVENTS):
        data = event.get("data") or {}
        if data.get("agent") != card:
            continue
        if event.get("event") == EVENT_DAEMON_START:
            if booted is None:                       # newest first: the current daemon's
                booted = float(event.get("timestamp") or 0.0)
                found.append(event)
            continue
        name = data.get("schedule")
        if name not in wanted:
            continue
        found.append(event)
        if event.get("event") == EVENT_NOT_RUN and booted is not None \
                and float(event.get("timestamp") or 0.0) < booted:
            continue                                 # an earlier daemon's refusal settles nothing
        kinds[name].add(event.get("event"))
        # A prompt run the daemon can't start never has a start; its not-run record settles it.
        if all(EVENT_SEEN in k or EVENT_NOT_RUN in k or {EVENT_STARTED, EVENT_DONE} <= k
               for k in kinds.values()):
            break
    return found


def _last_unit_events(declaration: Declaration, card: str) -> List[dict]:
    """Each declared unit's last state and last liveness events, oldest first.

    A unit's state is lifetime state, so the whole log is in scope; the scan reads backward
    and stops once every declared unit has both, so its cost is the events since each unit
    last changed. A declared unit that never ran makes it read to the start of the log.
    """
    wanted = {u.name for u in declaration.units}
    if not wanted:
        return []
    found: Dict[tuple, dict] = {}
    for event in read_events(reverse=True, scope="all", only=(EVENT_STATE, EVENT_LIVENESS)):
        data = event.get("data") or {}
        if data.get("agent") != card:
            continue
        found.setdefault((event.get("event"), data.get("unit")), event)
        if all((kind, unit) in found for unit in wanted
                          for kind in (EVENT_STATE, EVENT_LIVENESS)):
            break
    return sorted(found.values(), key=lambda e: e.get("timestamp") or 0)
