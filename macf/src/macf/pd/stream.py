"""The event stream: every event the layer records, published to the subscribers that chose it.

The primal daemon serves it on ``<agent>.events.sock`` (persistent_layer 11.4; MIS-0002 R150 to
R156). The event log stays the only store: the stream follows the log, as the core does, and
sends each new line to the subscribers whose sources it matches. Nothing new writes to it.

The wire, one JSON object per line each way:

- **hello**, the subscriber's one line, within ``HELLO_TIMEOUT_S`` of connecting:
  ``{"sources": ["pd_entry_*", ...], "position": {"log": ..., "offset": N}, "name": "tray"}``.
  ``position`` and ``name`` are optional. A position is the one the last record it saw carried.
- **welcome**: ``{"type": "welcome", "agent", "position", "sources", "granted"}``, where
  ``position`` is where the stream starts for it.
- **record**: ``{"type": "record", "position", "source", "agent", "time", "origin", "record"}``.
  ``position`` names the log (its inode and the digest of its first line) and the byte offset
  just past this record, which is a line boundary; a subscriber that reconnects with it is
  resumed from there. ``source`` is the record's event name, ``agent`` the daemon's own card and
  ``time`` the log's timestamp, never fields of the record's data. ``origin`` is ``daemon`` for a
  line this daemon's process appended (it learns the line as it writes it, and checks the bytes
  in the log are the very bytes it wrote) and ``log`` for every other line.
- **gap**: ``{"type": "gap", "agent", "time", "from", "to", "reason"}``: records between the two
  positions may be missing. ``reason`` is ``rotated`` (the log was replaced past the position),
  ``not_a_line_boundary`` (the position names no record of the log), ``backlog`` (a resume
  further back than the stream reads at once), or ``overflow`` (the subscriber fell behind and
  lost its queue).
- **refused**: ``{"type": "refused", "error"}``, then the connection closes.

Nothing here blocks the daemon's loop: every socket is non-blocking, each subscriber's queue is
bounded, and a subscriber that falls behind loses its own backlog (MIS-0002-R153).
"""
import collections
import fnmatch
import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from macf.pd.interface import (CHANNEL_SUBSCRIBER, EVENT_STREAM_RULE, STREAM_SUBSCRIBER_NAME, StreamGrant,
                               StreamRule)
from macf.utils.peercred import peer_credentials

#: How long a new connection has to send its hello.
HELLO_TIMEOUT_S = 3.0
#: The longest hello read; anything longer is refused, not buffered.
MAX_HELLO_BYTES = 16 * 1024
#: Records held for one subscriber before it loses them and is owed a gap.
QUEUE_MAX = 1000
#: Connections, a hello pending included, that one uid may hold.
MAX_PER_UID = 8
#: The most of the log a resume reads at once; a position further back gets a gap to here.
MAX_CATCHUP_BYTES = 8 * 1024 * 1024
#: How much of the log's first line names it, with its inode.
FINGERPRINT_BYTES = 4096
#: How many of the daemon's own appends are remembered, for their origin.
OWN_REMEMBERED = 10000

Position = Dict[str, object]


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


class Hello(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class At(BaseModel):
        model_config = ConfigDict(extra="forbid")
        log: str = Field(min_length=1, max_length=200)
        offset: int = Field(ge=0)

    sources: List[str] = Field(min_length=1, max_length=64)
    position: Optional[At] = None
    name: Optional[str] = Field(default=None, pattern=STREAM_SUBSCRIBER_NAME)

    @field_validator("name")
    @classmethod
    def _not_the_session(cls, name: Optional[str]) -> Optional[str]:
        if name == CHANNEL_SUBSCRIBER:
            raise ValueError(f"{CHANNEL_SUBSCRIBER!r} names the agent's own session in the rules "
                             f"(@{CHANNEL_SUBSCRIBER}), not a subscriber of the stream")
        return name


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
            if rule.agent == card:
                self.apply(rule.act, rule.target, rule.subscriber)
        return self

    def delivers(self, source: str, name: Optional[str]) -> bool:
        if name is not None and f"@{name}" in self.silenced:
            return False
        if matches(source, (p for p in self.silenced if not p.startswith("@"))):
            return False
        routed = [n for p, n in self.routes.items() if fnmatch.fnmatchcase(source, p)]
        return not routed or name in routed

    def as_dict(self) -> dict:
        return {"silenced": list(self.silenced), "routes": dict(self.routes)}


class Subscriber:
    def __init__(self, conn: socket.socket, uid: int, granted: Optional[List[str]], deadline: float):
        self.conn = conn
        self.uid = uid
        self.granted = granted          # None: every source (the agent's own uid)
        self.deadline = deadline
        self.hello = b""
        self.live = False
        self.name: Optional[str] = None
        self.sources: List[str] = []
        self.queue: Deque[Tuple[bytes, Optional[Position]]] = collections.deque()
        self.out = b""
        self.kept: Optional[Position] = None   # just past the last record it holds or was sent
        self.gap_from: Optional[Position] = None
        self.gap_reason = ""

    def wants(self, source: str) -> bool:
        return matches(source, self.sources) and (self.granted is None or matches(source, self.granted))


class EventStream:
    """One agent's event stream. ``bind``, then drive it from the daemon's loop: ``accept`` and
    ``readable`` when the selector says so, and ``pump`` on every pass."""

    def __init__(self, card: str, log_path: Path, grants: Iterable[StreamGrant] = (),
                 rules: Optional[Rules] = None, *, clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time, own_uid: Optional[int] = None):
        self.card = card
        self.log_path = Path(log_path)
        self.grants = {g.uid: list(g.sources) for g in grants}
        self.rules = rules or Rules()
        self._clock, self._wall = clock, wall
        self._own_uid = os.getuid() if own_uid is None else own_uid
        self.listener: Optional[socket.socket] = None
        self.subscribers: List[Subscriber] = []
        #: Called with each connection to watch for reading, and to stop watching.
        self.on_register: Optional[Callable[[socket.socket], None]] = None
        self.on_unregister: Optional[Callable[[socket.socket], None]] = None
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

    def _render(self, start: int, end: int, line: bytes) -> Optional[Tuple[str, bytes]]:
        """A log line as the stream's record: the layer's stamp, never the line's claims."""
        try:
            record = json.loads(line)
        except ValueError:
            return None  # noqa: MACEFF003 - a line that isn't JSON is no record; the caller skips it by design
        if not isinstance(record, dict) or not isinstance(record.get("event"), str):
            return None
        source = record["event"]
        stamp = record.get("timestamp")
        # The daemon's own line only where the log holds, at that offset, the very bytes it wrote.
        origin = "daemon" if self._own.get(start) == line else "log"
        out = {"type": "record", "position": self.position(end), "source": source, "agent": self.card,
               "time": stamp if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) else self._wall(),
               "origin": origin, "record": record}
        return source, json.dumps(out).encode() + b"\n"

    # ------------------------------------------------------------------ the socket

    def bind(self, path: Path) -> socket.socket:
        path.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        os.chmod(path, 0o600)
        listener.listen(16)
        listener.setblocking(False)
        self.listener = listener
        return listener

    def accept(self) -> None:
        try:
            conn, _ = self.listener.accept()
        except BlockingIOError:
            return  # noqa: MACEFF003 - nothing was pending: a spurious wakeup, not a failure
        conn.setblocking(False)
        try:
            # The one peer-credential helper: SO_PEERCRED on Linux, LOCAL_PEERCRED on macOS.
            uid = peer_credentials(conn).uid
        except OSError as e:
            self._refuse(conn, f"the subscriber cannot be identified: {e}")
            return
        if uid == self._own_uid:
            granted = None
        elif uid in self.grants:
            granted = self.grants[uid]
        else:
            self._refuse(conn, f"uid {uid} has no grant to {self.card}'s event stream; the operator "
                               f"grants one in the declaration's stream_grants")
            return
        if sum(s.uid == uid for s in self.subscribers) >= MAX_PER_UID:
            self._refuse(conn, f"uid {uid} already holds {MAX_PER_UID} connections to this stream")
            return
        sub = Subscriber(conn, uid, granted, self._clock() + HELLO_TIMEOUT_S)
        self.subscribers.append(sub)
        if self.on_register:
            self.on_register(conn)

    def _refuse(self, conn: socket.socket, why: str) -> None:
        print(f"⚠️ MACF: pd: refused an event-stream subscriber: {why}", file=sys.stderr)
        try:
            conn.send(json.dumps({"type": "refused", "error": why}).encode() + b"\n")
        except OSError:
            pass  # noqa: MACEFF003 - the refusal is said on stderr; the peer may be gone
        conn.close()

    def _drop(self, sub: Subscriber, why: str = "") -> None:
        if sub in self.subscribers:
            self.subscribers.remove(sub)
        if self.on_unregister:
            try:
                self.on_unregister(sub.conn)
            except (KeyError, ValueError):
                pass  # noqa: MACEFF003 - it was never watched
        if why:
            self._refuse(sub.conn, why)
        else:
            sub.conn.close()

    def readable(self, conn: socket.socket) -> None:
        sub = next((s for s in self.subscribers if s.conn is conn), None)
        if sub is None:
            return
        try:
            data = conn.recv(4096)
        except BlockingIOError:
            return  # noqa: MACEFF003 - a spurious wakeup, not a failure
        except OSError:
            data = b""
        if not data:
            self._drop(sub)
            return
        if sub.live:
            self._drop(sub, "a subscriber sends one line, its hello, and nothing after it")
            return
        sub.hello += data
        if b"\n" not in sub.hello:
            if len(sub.hello) > MAX_HELLO_BYTES:
                self._drop(sub, f"the hello is longer than {MAX_HELLO_BYTES} bytes")
            return
        line, rest = sub.hello.split(b"\n", 1)
        if rest:
            self._drop(sub, "a subscriber sends one line, its hello, and nothing after it")
            return
        try:
            hello = Hello.model_validate_json(line)
        except ValidationError as e:
            self._drop(sub, f"the hello was refused: {e.errors()[0]['msg']}")
            return
        self._welcome(sub, hello)

    def _welcome(self, sub: Subscriber, hello: Hello) -> None:
        """Take the hello: a subscriber with no position takes what is recorded from now; one
        with a position reads back to it, after a gap where it can't (MIS-0002-R154)."""
        sub.live, sub.name, sub.sources, sub.hello = True, hello.name, list(hello.sources), b""
        gap, read_from = None, None
        if hello.position is not None:
            gap, read_from = self._resume_from(hello.position.log, hello.position.offset)
        start = self.position(read_from)
        welcome = {"type": "welcome", "agent": self.card, "position": start, "sources": sub.sources,
                   "granted": sub.granted if sub.granted is not None else ["*"]}
        sub.queue.append((json.dumps(welcome).encode() + b"\n", None))
        sub.kept = start if hello.position is None else {"log": hello.position.log,
                                                         "offset": hello.position.offset}
        if gap is not None:
            sub.gap_from, sub.gap_reason = gap[0], gap[2]
            self._emit_gap(sub, gap[1])
            sub.kept = gap[1]
        if read_from is None:
            return
        for start_at, end, line in self._read_lines(read_from, self.offset):
            rendered = self._render(start_at, end, line)
            if rendered is not None and self._for(sub, rendered[0]):
                self._enqueue(sub, rendered[1], self.position(start_at), self.position(end))

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

    # ------------------------------------------------------------------ delivery

    def _for(self, sub: Subscriber, source: str) -> bool:
        return sub.wants(source) and self.rules.delivers(source, sub.name)

    def _emit_gap(self, sub: Subscriber, to: Position) -> None:
        gap = {"type": "gap", "agent": self.card, "time": self._wall(), "from": sub.gap_from, "to": to,
               "reason": sub.gap_reason}
        sub.queue.append((json.dumps(gap).encode() + b"\n", None))
        sub.gap_from, sub.gap_reason = None, ""

    def _enqueue(self, sub: Subscriber, payload: bytes, start: Position, end: Position) -> None:
        if sub.gap_from is None and len(sub.queue) >= QUEUE_MAX:
            # It fell behind: it loses its own backlog, and its next record is a gap from the
            # last record it still holds (MIS-0002-R153).
            sub.queue.clear()
            sub.gap_from, sub.gap_reason = sub.kept, "overflow"
        if sub.gap_from is not None:
            self._emit_gap(sub, start)
        sub.queue.append((payload, end))

    def _flush(self, sub: Subscriber) -> None:
        while True:
            if not sub.out:
                if not sub.queue:
                    return
                sub.out, end = sub.queue.popleft()
                if end is not None:
                    sub.kept = end
            try:
                sent = sub.conn.send(sub.out)
            except BlockingIOError:
                return  # noqa: MACEFF003 - the socket is full: keep the record and try next pass (R153)
            except OSError:
                self._drop(sub)
                return
            sub.out = sub.out[sent:]

    def pump(self) -> None:
        """One pass: close hellos that are late, publish what was appended, send what is queued."""
        now = self._clock()
        for sub in [s for s in self.subscribers if not s.live and now > s.deadline]:
            self._drop(sub, f"no hello within {HELLO_TIMEOUT_S:g} s")
        self._settle_own()
        lines, gap = self._follow()
        live = [s for s in self.subscribers if s.live]
        if gap is not None:
            for sub in live:
                sub.gap_from, sub.gap_reason = sub.gap_from or gap[0], "rotated"
        for start, end, line in lines:
            rendered = self._render(start, end, line)
            if rendered is None:
                continue
            source, payload = rendered
            for sub in live:
                if self._for(sub, source):
                    self._enqueue(sub, payload, self.position(start), self.position(end))
        for sub in list(self.subscribers):
            if sub.live:
                self._flush(sub)

    def close(self) -> None:
        for sub in list(self.subscribers):
            self._drop(sub)
        if self.listener is not None:
            self.listener.close()
            self.listener = None


def fold_rules(events: Iterable[dict], card: str) -> Rules:
    return Rules().fold(events, card)


def subscribe(path: Path, sources: List[str], *, position: Optional[Position] = None,
              name: Optional[str] = None, timeout: Optional[float] = None) -> socket.socket:
    """Connect to an event stream and send the hello; the caller reads lines from the socket."""
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    conn.connect(str(path))
    hello: dict = {"sources": sources}
    if position is not None:
        hello["position"] = position
    if name is not None:
        hello["name"] = name
    conn.sendall(json.dumps(hello).encode() + b"\n")
    return conn


__all__ = ["EVENT_STREAM_RULE", "EventStream", "Rules", "fold_rules", "log_identity", "subscribe"]
