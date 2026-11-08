"""The event stream's source: the event log, followed, for the daemon's own MQTT broker.

Every daemon publishes its stream on its own broker (persistent_layer 11.4; MIS-0002 R150 to R156,
``macf.pd.broker``). This module is the part that reads the log: it follows the log as the core
does, renders each new line as a stream record, and answers a replay from a position. The log stays
the only store; nothing here writes to it.

A stream record is ``{"type": "record", "position", "source", "agent", "time", "origin", "record"}``.
``position`` names the log (its inode and the digest of its first line) and the byte offset just past
this record, which is a line boundary. ``source`` is the record's event name, ``agent`` the daemon's
own card and ``time`` the log's timestamp, never fields of the record's data. ``origin`` is
``daemon`` for a line this daemon's process appended (it learns the line as it writes it, and checks
the bytes in the log are the very bytes it wrote) and ``log`` for every other line.

The operator's rules (MIS-0002 R152) fold here too, and act in the daemon before anything is
published: a silenced source isn't published, and the notifier reads the same rules for notices.
"""
import collections
import dataclasses
import fnmatch
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from pydantic import ValidationError

from macf.pd.interface import EVENT_STREAM_RULE, StreamGrant, StreamRule
from macf import calling_card

#: The most of the log a resume reads at once; a position further back gets a gap to here.
MAX_CATCHUP_BYTES = 8 * 1024 * 1024
#: How much of the log's first line names it, with its inode.
FINGERPRINT_BYTES = 4096
#: How many of the daemon's own appends are remembered, for their origin.
OWN_REMEMBERED = 10000

Position = Dict[str, object]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Chunk:
    """One bounded step of a replay (``EventStream.since_chunk``): the gap owed first, if any;
    the records read; the position to continue from (None when there was nothing to read); and
    whether the step reached what the stream has read."""
    gap: Optional[tuple]
    records: List[dict]
    next: Optional[Position]
    at_end: bool


def log_identity(path: Path, ino: int) -> str:
    """The log's name in a position: its inode and the digest of its first line. Rotation keeps
    the inode and rewrites the file from a later line, so the first line is what tells a rotated
    log from the one a position was taken in. A log with no complete line yet is ``empty``."""
    try:
        with open(path, "rb") as f:
            head = f.read(FINGERPRINT_BYTES)
    except OSError:
        head = b""
    newline = head.find(b"\n")
    if newline >= 0:
        head = head[:newline + 1]
    elif len(head) < FINGERPRINT_BYTES:
        return f"{ino}-empty"
    return f"{ino}-{hashlib.sha256(head).hexdigest()[:16]}"


def matches(source: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(source, p) for p in patterns)


class Rules:
    """The operator's rules in force: what the ``pd_stream_rule`` events fold to. The notifier
    reads the same rules, live, for the agent's session under the name ``channel``
    (``CHANNEL_SUBSCRIBER``), so a rule silences or reroutes a notice to the session as it does
    a record to a subscriber (MIS-0002-R152)."""

    def __init__(self):
        self.silenced: List[str] = []
        self.routes: Dict[str, str] = {}

    def apply(self, act: str, target: str, subscriber: Optional[str] = None) -> None:
        if act == "silence" and target not in self.silenced:
            self.silenced.append(target)
        elif act == "unsilence" and target in self.silenced:
            self.silenced.remove(target)
        elif act == "route":
            self.routes[target] = subscriber
        elif act == "unroute":
            self.routes.pop(target, None)

    def fold(self, events: Iterable[dict], card: str) -> "Rules":
        for event in events:
            try:
                rule = StreamRule.model_validate(event.get("data") or {})
            except ValidationError:
                continue    # noqa: MACEFF003 - a line that isn't a rule sets none
            if calling_card.is_agent(rule.agent, card):    # a rule stored under the old card still holds (R166)
                self.apply(rule.act, rule.target, rule.subscriber)
        return self

    def delivers(self, source: str, name: Optional[str]) -> bool:
        """Whether *source* reaches the subscriber *name* (a broker reader's card, or ``channel``
        for the session). Names compare without regard to case, as cards do (R164)."""
        if name is not None and name.casefold() in self.silenced_subscribers():
            return False
        if self.source_silenced(source):
            return False
        routed = self.routed_to(source)
        return routed is None or (name is not None and name.casefold() in routed)

    def source_silenced(self, source: str) -> bool:
        return matches(source, (p for p in self.silenced if not p.startswith("@")))

    def silenced_subscribers(self) -> List[str]:
        """The subscribers silenced by name (``@name``), casefolded."""
        return [p[1:].casefold() for p in self.silenced if p.startswith("@")]

    def routed_to(self, source: str) -> Optional[List[str]]:
        """The subscribers *source* is routed to, casefolded, or None where no route takes it."""
        routed = sorted({n.casefold() for p, n in self.routes.items() if n and fnmatch.fnmatchcase(source, p)})
        return routed or None

    def as_dict(self) -> dict:
        return {"silenced": list(self.silenced), "routes": dict(self.routes)}


class EventStream:
    """One daemon's log, followed: ``take`` what it gained, ``since`` a position for a replay."""

    def __init__(self, card: str, log_path: Path, grants: Iterable[StreamGrant] = (),
                 rules: Optional[Rules] = None, *, clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time, own_uid: Optional[int] = None):
        self.card = card
        self.log_path = Path(log_path)
        self.grants = {g.uid: list(g.sources) for g in grants}
        self.rules = rules or Rules()
        self._clock, self._wall = clock, wall
        self._own_uid = os.getuid() if own_uid is None else own_uid
        self._own: "collections.OrderedDict[int, bytes]" = collections.OrderedDict()
        self._pending_own: List[Tuple[int, bytes]] = []
        self._ino: Optional[int] = None
        self.identity: Optional[str] = None
        self.offset = 0
        self._last_line = b""
        self._start_at_end()

    # ------------------------------------------------------------------ the log

    def _start_at_end(self) -> None:
        """Start at the log's end, on a line boundary: a subscriber that names no position takes
        what is recorded from now; one that does reads back to it."""
        try:
            st = self.log_path.stat()
        except FileNotFoundError:
            return  # noqa: MACEFF003 - no log yet: the position stays at its start, which is the end
        self._ino, self.identity = st.st_ino, log_identity(self.log_path, st.st_ino)
        self.offset = self._boundary_at_or_before(st.st_size)

    def _boundary_at_or_before(self, size: int) -> int:
        with open(self.log_path, "rb") as f:
            back = min(size, 1024 * 1024)
            f.seek(size - back)
            chunk = f.read(back)
        cut = chunk.rfind(b"\n")
        if cut >= 0:
            self._last_line = chunk[chunk.rfind(b"\n", 0, cut) + 1:cut + 1]
            return size - back + cut + 1
        return 0

    def position(self, offset: Optional[int] = None) -> Position:
        return {"log": self.identity or "none", "offset": self.offset if offset is None else offset}

    def note_own_append(self, path: Path, start: int, raw: bytes) -> None:
        """What ``append_event`` wrote from this process: the line, and where it starts."""
        if Path(path) == self.log_path:
            self._pending_own.append((start, raw))

    def _settle_own(self) -> None:
        for start, raw in self._pending_own:
            self._own[start] = raw
            if len(self._own) > OWN_REMEMBERED:
                self._own.popitem(last=False)
        self._pending_own.clear()

    def start_at_end(self) -> None:
        """Follow from what the log holds now, not from its start: for a publisher or an
        exporter, whose readers catch up from the log by replay. Without it, the first pass
        read the whole log in one go (hundreds of megabytes on a long-lived host), published
        it, and flooded an association with every export ever recorded (seen live, Nov 8)."""
        try:
            st = self.log_path.stat()
        except FileNotFoundError:
            return      # noqa: MACEFF003 - no log yet: its first line is new, followed from 0
        # From the end as it stands. A line half-written at this moment is finished after
        # it; its tail isn't JSON, so the next pass skips it as it skips any such line.
        self._ino, self.identity, self.offset = st.st_ino, log_identity(self.log_path, st.st_ino), st.st_size

    def _follow(self) -> Tuple[List[Tuple[int, int, bytes]], Optional[Tuple[Position, Position]]]:
        """The complete lines appended since the last pass, as (start, end, line), and a gap
        when the log was replaced under them."""
        try:
            st = self.log_path.stat()
        except FileNotFoundError:
            return [], None
        gap = None
        if self._ino is None:
            self._ino, self.identity, self.offset = st.st_ino, log_identity(self.log_path, st.st_ino), 0
        replaced = st.st_ino != self._ino or st.st_size < self.offset
        if not replaced and st.st_size == self.offset:
            return [], None
        if not replaced:
            now = log_identity(self.log_path, st.st_ino)
            if now != self.identity:
                if self.offset == 0 or self.identity.endswith("-empty"):
                    self.identity = now       # its first line arrived: the same log
                else:
                    replaced = True
        if replaced:
            gap = self._after_rotation(st)
            if gap is False:
                return [], None               # mid-rotation: read it next pass
        lines = self._read_lines(self.offset, self.log_path.stat().st_size if replaced else st.st_size)
        if lines:
            self.offset = lines[-1][1]
            self._last_line = lines[-1][2]
        return lines, gap

    def _after_rotation(self, st):
        """Find where the stream stood in the replaced log. Rotation keeps the log's newest
        cycle, so the last line delivered is still there unless it was archived; past it is
        everything unread. Not found, the records between are owed a gap. Rotation holds the
        log's lock while it rewrites, so this waits for a pass where the lock is free."""
        import fcntl
        try:
            f = open(self.log_path, "rb")
        except OSError:
            return False
        with f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                return False
            try:
                data = f.read(MAX_CATCHUP_BYTES)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        before = self.position()
        self._ino, self.identity = st.st_ino, log_identity(self.log_path, st.st_ino)
        self._own.clear()
        found = -1
        if self._last_line:
            if data.startswith(self._last_line):
                found = 0
            else:
                at = data.find(b"\n" + self._last_line)
                found = at + 1 if at >= 0 else -1
        if found >= 0:
            self.offset = found + len(self._last_line)
            return None
        self.offset = 0
        return before, self.position(0)

    def _read_lines(self, start: int, end: int) -> List[Tuple[int, int, bytes]]:
        if end <= start:
            return []
        with open(self.log_path, "rb") as f:
            f.seek(start)
            chunk = f.read(end - start)
        out, at = [], 0
        while True:
            nl = chunk.find(b"\n", at)
            if nl < 0:
                break
            out.append((start + at, start + nl + 1, chunk[at:nl + 1]))
            at = nl + 1
        return out

    def _record(self, start: int, end: int, line: bytes) -> Optional[dict]:
        """A log line as the stream's record: the layer's stamp, never the line's claims."""
        try:
            record = json.loads(line)
        except ValueError:
            return None  # noqa: MACEFF003 - a line that isn't JSON is no record; the caller skips it by design
        if not isinstance(record, dict) or not isinstance(record.get("event"), str):
            return None
        stamp = record.get("timestamp")
        # The daemon's own line only where the log holds, at that offset, the very bytes it wrote.
        origin = "daemon" if self._own.get(start) == line else "log"
        return {"type": "record", "position": self.position(end), "source": record["event"],
                "agent": self.card,
                "time": stamp if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) else self._wall(),
                "origin": origin, "record": record}

    def _render(self, start: int, end: int, line: bytes) -> Optional[Tuple[str, bytes]]:
        out = self._record(start, end, line)
        return None if out is None else (out["source"], json.dumps(out).encode() + b"\n")

    def since(self, log: str, offset: int) -> Tuple[Optional[Tuple[Position, Position, str]], List[dict]]:
        """For a replay (R154 as amended): the gap owed before a resume from this position, if
        any, and the stream records from where the resume can start up to what the stream has
        read."""
        self._settle_own()
        gap, read_from = self._resume_from(log, offset)
        if read_from is None:
            return gap, []
        lines = self._read_lines(read_from, self.offset)
        return gap, [r for r in (self._record(s, e, line) for s, e, line in lines) if r is not None]

    def since_chunk(self, log: str, offset: int, max_bytes: Optional[int]) -> "Chunk":
        """``since`` in bounded steps, for a replay answered over several passes of the daemon's
        loop: at most *max_bytes* of log, and at least one whole line, so a long line still makes
        progress."""
        self._settle_own()
        gap, read_from = self._resume_from(log, offset)
        if read_from is None:
            return Chunk(gap=gap, records=[], next=None, at_end=True)
        end = self.offset if max_bytes is None else min(self.offset, read_from + max_bytes)
        lines = self._read_lines(read_from, end)
        if not lines and end < self.offset:
            lines = self._read_lines(read_from, self.offset)[:1]
        reached = lines[-1][1] if lines else read_from
        records = [r for r in (self._record(s, e, line) for s, e, line in lines) if r is not None]
        return Chunk(gap=gap, records=records, next=self.position(reached), at_end=reached >= self.offset)

    def take(self) -> Tuple[List[dict], Optional[Tuple[Position, Position]]]:
        """For the publisher (the daemon's broker, MIS-0002 R150 to R156 as
        amended): the records appended since the last call, as stream records, and the gap owed
        first when the log was replaced under them."""
        self._settle_own()
        lines, gap = self._follow()
        records = [r for r in (self._record(s, e, line) for s, e, line in lines) if r is not None]
        return records, gap

    def _resume_from(self, log: str, offset: int):
        """Where a resume reads from, and the gap it is owed first, if any."""
        asked = {"log": log, "offset": offset}
        if self.identity is None:
            return (asked, self.position(0), "rotated"), None    # no log yet: all of it is new
        if log != self.identity:
            read_from, reason = 0, "rotated"
        elif offset > self.offset or not self._on_boundary(offset):
            read_from = self._next_boundary(offset)
            reason = "not_a_line_boundary"
        else:
            read_from, reason = offset, ""
        if self.offset - read_from > MAX_CATCHUP_BYTES:
            read_from = self._next_boundary(self.offset - MAX_CATCHUP_BYTES)
            reason = reason or "backlog"
        gap = (asked, self.position(read_from), reason) if reason else None
        return gap, read_from

    def _on_boundary(self, offset: int) -> bool:
        if offset == 0:
            return True
        with open(self.log_path, "rb") as f:
            f.seek(offset - 1)
            return f.read(1) == b"\n"

    def _next_boundary(self, offset: int) -> int:
        """The first line boundary at or after ``offset``, no further than the stream has read."""
        offset = max(0, min(offset, self.offset))
        if self._on_boundary(offset):
            return offset
        with open(self.log_path, "rb") as f:
            f.seek(offset)
            chunk = f.read(self.offset - offset)
        nl = chunk.find(b"\n")
        return self.offset if nl < 0 else offset + nl + 1

def fold_rules(events: Iterable[dict], card: str) -> Rules:
    return Rules().fold(events, card)


__all__ = ["EVENT_STREAM_RULE", "EventStream", "Rules", "fold_rules", "log_identity"]
