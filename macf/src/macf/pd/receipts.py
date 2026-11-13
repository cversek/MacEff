"""Notices written to the channel that the session never took (cversek/MacEff#904).

The daemon counts a notice delivered when it writes it to the channel process
(``pd_notice_delivered``), and the session's prompt hook records ``notice_received`` when the
client hands it over (MIS-0002-R120). A client that refuses the channel drops the notice in
between and says nothing, so the delivery reads as healthy. Comparing the two catches that
whatever the cause.

A busy session takes a notice when its turn ends, so a missing receipt counts only once the
session has started a turn after the notice was written, and after a grace for that turn's
hook. Read only; nothing is stored.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

DELIVERED = "pd_notice_delivered"
RECEIVED = "notice_received"
#: A turn starting: the prompt hook's own record, which a notice's turn writes too.
TURN = "dev_drv_started"
EVENTS = (DELIVERED, RECEIVED, TURN)
#: How long after a notice is written a turn must start before its missing receipt counts.
GRACE_S = 120.0


@dataclass(frozen=True)
class Unreceived:
    source: str
    arrival_id: str
    sent_at: float


def unreceived(events: Iterable[dict], grace_s: float = GRACE_S) -> List[Unreceived]:
    """The channel notices among *events* with no receipt, though a turn started more than
    *grace_s* after each was written; oldest first. Keystroke wakes are not counted: the
    session's own turn is their receipt."""
    sent, received, turns = [], set(), []
    for event in events:
        name, data = event.get("event"), event.get("data") or {}
        if name == DELIVERED and data.get("via") == "channel" and data.get("arrival_id"):
            sent.append(Unreceived(str(data.get("source")), str(data["arrival_id"]),
                                   float(data.get("sent_at") or event.get("timestamp") or 0)))
        elif name == RECEIVED and data.get("notice_id"):
            received.add(str(data["notice_id"]))
        elif name == TURN:
            turns.append(float(event.get("timestamp") or 0))
    latest_turn = max(turns, default=None)
    return sorted((n for n in sent if n.arrival_id not in received
                   and latest_turn is not None and latest_turn > n.sent_at + grace_s),
                  key=lambda n: n.sent_at)


def after_last_receipt(events: Iterable[dict], grace_s: float = GRACE_S) -> List[Unreceived]:
    """:func:`unreceived`, less every notice written before the newest receipt: once a receipt
    arrives the channel works, and what it dropped earlier is history, not a live fault."""
    events = list(events)
    last = max((float(e.get("timestamp") or 0) for e in events if e.get("event") == RECEIVED),
               default=None)
    return [n for n in unreceived(events, grace_s) if last is None or n.sent_at > last]
