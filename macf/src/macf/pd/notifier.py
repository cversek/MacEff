"""The notifier: notices from an agent's sources, delivered into its live session through
the MacEff channel, and held while they can't be.

MIS-0002 step 2. The daemon hosts it because the daemon runs while the session is down.
A notifier inside the session (the transcript monitor's sources) is down exactly when a
notice has to be held, and when it comes back it primes on what is already waiting and
says nothing about it.

- **Intake** is the daemon's own poll of each declared source, with the monitor's
  ``StoreSource``: names only, never contents, and one detection per burst. Each
  detection is appended to the agent's event log before anything is delivered.
- **Holding** is the log. A detection with no ``pd_notice_delivered`` after it is still
  owed, and a daemon that restarts reads that back, so nothing is kept outside the log
  [MIS-0002-R41 (pd_MUST_hold_notices_while_down), MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)].
- **Delivery** is one closed record per notice on the channel socket, to a channel whose
  process descends from the session unit (the daemon checks that before attaching it).
  The record names the source and carries the time the store was read and the time it
  was sent; the channel adds the time it was received [MIS-0002-R38
  (notice_MUST_name_source), MIS-0002-R39 (notice_MUST_carry_three_times)].
- **Nothing for no change.** A source reports arrivals, never a quiet poll, so no
  notice says that nothing happened [MIS-0002-R46 (layer_MUST-NOT_report_no_change)].

Routing follows the declaration's ``notice_routes`` [MIS-0002-R42
(notice_source_MUST_be_routed)]. This module delivers the agent's share, ``agent`` and
the agent half of ``both``. A source routed only to the operator is not polled here.
"""
from __future__ import annotations

import hashlib
import json
import socket
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from macf.agent_events_log import append_event, read_events
from macf.transcript_monitor.sources import StoreSource, agent_store_source

#: The detection a source's poll produces, as the monitor names it.
EVENT_DETECTED = "store_arrival_detected"
#: One notice written to a channel.
EVENT_DELIVERED = "pd_notice_delivered"
#: Who wrote a detection: the daemon's notifier, as against any other poller of a store.
NOTIFIER = "pd"

#: How far back a restarted daemon looks for notices it still owes. Older ones were
#: either delivered, or describe mail the agent has long since read or been told of.
HOLD_MAX_S = 24 * 3600

#: The routes whose notices go to the agent's session.
AGENT_ROUTES = ("agent", "both")

#: Each source this notifier can poll, by the name the channel's records use.
SOURCES: Dict[str, Callable[[Path], StoreSource]] = {
    "amail": lambda home: agent_store_source(home, "amail"),
}


@dataclass
class Owed:
    source: str
    arrival_id: str
    count: Optional[int]
    read_at: float


def burst_id(source: str, names: Iterable[str]) -> str:
    """The arrival id ``StoreSource`` gives a burst of new names, for a set read at start."""
    return f"{source}-" + hashlib.sha256("\0".join(sorted(names)).encode()).hexdigest()[:16]


class Notifier:
    """Poll the declared sources, hold what is owed, and write it to the attached channel."""

    def __init__(self, agent_home: Path, routes: Dict[str, str], *,
                 append: Callable[[str, dict], bool] = append_event,
                 clock: Callable[[], float] = time.time,
                 events: Optional[Callable[[], Iterable[dict]]] = None):
        self._append, self._clock = append, clock
        self._events = events or (lambda: read_events(reverse=True, scope="all",
                                                      only=(EVENT_DETECTED, EVENT_DELIVERED)))
        self.owed: "OrderedDict[str, Owed]" = OrderedDict()
        self.sources: List[StoreSource] = []
        self._channels: List[socket.socket] = []
        #: Called with a channel just before it is closed, so its owner can stop watching it.
        self.on_detach: Optional[Callable[[socket.socket], None]] = None
        for name, route in sorted(routes.items()):
            if route not in AGENT_ROUTES:
                continue
            make = SOURCES.get(name)
            if make is None:
                print(f"⚠️ MACF: pd: notice source {name!r} is declared but this daemon has no "
                      f"poller for it; its notices are not delivered", file=sys.stderr)
                continue
            self.sources.append(make(Path(agent_home)))

    # ------------------------------------------------------------------ intake

    def boot(self) -> None:
        """Read back what is still owed, then start each source from what its store holds
        now, giving one notice for that if any of it was never announced."""
        now = self._clock()
        delivered, detected = set(), OrderedDict()
        for event in self._events():
            ts = event.get("timestamp") or 0
            if now - ts > HOLD_MAX_S:
                break
            data = event.get("data") or {}
            if not isinstance(data, dict) or data.get("notifier") != NOTIFIER:
                continue
            aid = data.get("arrival_id")
            if not isinstance(aid, str):
                continue
            if event.get("event") == EVENT_DELIVERED:
                delivered.add(aid)
            elif aid not in delivered and aid not in detected and data.get("source") in SOURCES:
                count = data.get("count")
                count = count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else None
                detected[aid] = Owed(data["source"], aid, count, float(ts))
        for aid in reversed(list(detected)):     # read newest first; owe oldest first
            self.owed[aid] = detected[aid]
        known = set(detected) | delivered
        for source in self.sources:
            current = source.start()
            if current is None:
                continue                         # unreadable: the source says so, and polls again
            if current and burst_id(source.name, current) not in known:
                self._detect(source.name, burst_id(source.name, current), len(current), source.store_dir)

    def poll(self) -> None:
        for source in self.sources:
            for d in source.poll():
                self._detect(source.name, d.data["arrival_id"], d.data.get("count"), source.store_dir)

    def _detect(self, source: str, arrival_id: str, count: Optional[int], store: Path) -> None:
        now = self._clock()
        self._append(EVENT_DETECTED, {"source": source, "arrival_id": arrival_id, "count": count,
                                      "store": str(store), "notifier": NOTIFIER})
        self.owed[arrival_id] = Owed(source, arrival_id, count, now)

    # ------------------------------------------------------------------ delivery

    def attach(self, conn: socket.socket) -> None:
        """A channel whose peer the daemon has checked. The newest is written to first: a
        session that restarted has a new channel, and its old one is gone or going."""
        self._channels.insert(0, conn)

    def detach(self, conn: socket.socket) -> None:
        if conn not in self._channels:
            return
        self._channels.remove(conn)
        if self.on_detach is not None:
            self.on_detach(conn)
        try:
            conn.close()
        except OSError:
            pass  # noqa: MACEFF003 - closing a socket that already failed; nothing is lost

    @property
    def channels(self) -> List[socket.socket]:
        return list(self._channels)

    def flush(self) -> int:
        """Write every owed notice to the newest channel that takes it; return how many went."""
        sent = 0
        while self.owed and self._channels:
            aid, owed = next(iter(self.owed.items()))
            conn = self._channels[0]
            sent_at = self._clock()
            record = {"source": owed.source, "arrival_id": aid, "read_at": owed.read_at, "sent_at": sent_at}
            if owed.count is not None:
                record["count"] = owed.count
            try:
                conn.sendall(json.dumps(record).encode() + b"\n")
            except OSError as e:
                print(f"⚠️ MACF: pd: a channel went away while a notice was written ({e}); "
                      f"the notice stays owed", file=sys.stderr)
                self.detach(conn)
                continue
            self._append(EVENT_DELIVERED, {"source": owed.source, "arrival_id": aid,
                                           "read_at": owed.read_at, "sent_at": sent_at,
                                           "via": "channel", "notifier": NOTIFIER})
            del self.owed[aid]
            sent += 1
        return sent
