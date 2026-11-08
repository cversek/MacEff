"""Associations: a daemon whose broker also admits member daemons (PROTOTYPE, mission B phase B3).

A member exports what its declaration chooses to its association's broker, under its own subtree
``members/<card>/``, and never content. The association reads every member's subtree, compares the
members it declares with the members present, and reports the difference. Members can't write as
a sibling or read one: the broker's access rules give each member ``write members/<card>/#`` and
nothing else (``broker.render_acl``).

Presence is MQTT's own. A member publishes ``online``, retained, when it connects, and registers
``offline`` as its will, which the broker publishes when the connection dies uncleanly. Before a
clean disconnect the member publishes ``offline`` itself, since a will fires only on an unclean one.
"""
import fnmatch
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from macf.pd import broker as b

#: The record fields an export may carry. Everything else in a record (its data, which may hold
#: notice text, mail, unit arguments) stays home: exports are summaries, never content.
EXPORT_FIELDS = ("source", "agent", "time", "position")
#: The fields of a record's data an export may carry, for the unit-state family.
EXPORT_DATA_FIELDS = ("unit", "state")
#: Sources a member exports when its declaration names none: liveness and unit states.
DEFAULT_EXPORTS = ("pd_unit_state", "pd_carried")


def member_topic(card: str, rest: str) -> str:
    return f"members/{card}/{rest}"


def presence_topic(card: str) -> str:
    return member_topic(card, "presence")


def summarize(stream_record: dict) -> dict:
    """What an export carries for one stream record: its stamp and, for a unit's state, which
    unit and what state. Nothing a record's data says beyond that leaves the member."""
    out = {k: stream_record[k] for k in EXPORT_FIELDS if k in stream_record}
    data = (stream_record.get("record") or {}).get("data") or {}
    kept = {k: data[k] for k in EXPORT_DATA_FIELDS if isinstance(data.get(k), str)}
    if kept:
        out["data"] = kept
    return out


def exported(source: str, exports: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(source, e) for e in exports)


def export_message(card: str, stream_record: dict, exports: Sequence[str]) -> Optional[b.Message]:
    """The message one stream record exports as, on the member's own subtree; None when the
    declaration doesn't export its source."""
    source = stream_record.get("source")
    if not isinstance(source, str) or not exported(source, exports):
        return None
    topic = member_topic(card, "events/" + source.replace("_", "/"))
    return b.Message(topic=topic, payload=json.dumps(summarize(stream_record), separators=(",", ":")).encode(),
                     properties={})


class Exporter:
    """A member daemon's exports: the records its declaration exports, summarized, published to
    its association's broker. Pending on failure, like the publisher (R153)."""

    def __init__(self, card: str, stream, publish, exports: Sequence[str] = DEFAULT_EXPORTS):
        self.card, self.stream, self.publish = card, stream, publish
        self.exports = tuple(exports)
        self.pending: List[b.Message] = []

    def pump(self) -> int:
        records, _gap = self.stream.take()
        self.pending += [m for m in (export_message(self.card, r, self.exports) for r in records) if m]
        if len(self.pending) > b.PENDING_MAX:
            self.pending = self.pending[-b.PENDING_MAX:]
        sent = 0
        while self.pending:
            self.publish(self.pending[0])
            self.pending.pop(0)
            sent += 1
        return sent


@dataclass
class MemberState:
    present: bool = False
    last_export: Optional[float] = None


@dataclass
class MembershipView:
    """The association's view of its members: declared against present, and when each was last
    heard from. ``observe`` takes every message under ``members/#``."""
    expected: Sequence[str]
    silent_after_s: float = 300.0
    members: Dict[str, MemberState] = field(default_factory=dict)

    def observe(self, topic: str, payload: bytes, now: float) -> None:
        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != "members":
            return
        card = parts[1]
        state = self.members.setdefault(card, MemberState())
        if parts[2] == "presence":
            state.present = payload == b"online"
        else:
            state.last_export = now

    def findings(self, now: float) -> List[str]:
        """Each difference between the members declared and the members present, one line each,
        for the association's own log and the outside watch's alert path."""
        out = []
        for card in self.expected:
            s = self.members.get(card)
            if s is None:
                out.append(f"{card}: declared, never present")
            elif not s.present:
                out.append(f"{card}: offline")
            elif s.last_export is not None and now - s.last_export > self.silent_after_s:
                out.append(f"{card}: present but silent for {now - s.last_export:.0f} s")
        for card in sorted(set(self.members) - set(self.expected)):
            out.append(f"{card}: present but not declared")
        return out
