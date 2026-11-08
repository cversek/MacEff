"""Each daemon's own MQTT broker: its configuration and access rules, rendered from the declaration.

PROTOTYPE (mission B, phase B2). Every daemon runs its own broker as a unit, and its stream lives
there. This module renders what that broker runs with; it starts nothing.

WHY EXPLICIT USER LINES. mosquitto's ``pattern`` rules "apply to all users", so a pattern would
admit any certificate the CA ever issued. Each certificate the declaration names gets its own
``user`` block instead, and a certificate it doesn't name can connect but reads and writes nothing.

WHY THE CERTIFICATE'S NAME IS THE CARD LOWERCASED. With ``use_identity_as_username`` the
certificate's Common Name is the user the rules name. Several system daemons share the account
``maceff_system``, so the account can't identify a daemon; the card can, and a certificate name
takes it lowercased (MIS-0002-R161).

WHAT EACH CERTIFICATE MAY DO.
- The daemon itself: ``readwrite <card>/#``, its own stream and status.
- An association daemon: ``read members/#``.
- Each declared member: ``write members/<member card>/#`` and nothing else, so it can't write as
  a sibling or read one.
- Each granted reader: ``read <card>/events/<source>`` for each source granted.

WHY TOPICS ARE LOWERCASE. MQTT topics are case-sensitive, but two spellings of one card are the
same card (MIS-0002-R164). Every topic level that names a card takes it lowercased, as the
certificate's name does, so a member or reader declared in another case still matches.

WHY ONE LOOPBACK ADDRESS. The broker binds ``LOOPBACK`` and every local link dials the same
address. ``localhost`` resolves to ``::1`` first on some systems (macOS among them), where the
first attempt then fails; the server certificate carries ``LOOPBACK`` as an IP name.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from macf import calling_card

#: The one address a daemon's own broker binds and its local links dial.
LOOPBACK = "127.0.0.1"
LISTEN = {"loopback": LOOPBACK}


class BrokerRefused(ValueError):
    """A broker declaration that can't be rendered, with the reason."""


def cert_name(card: str) -> str:
    """The Common Name a daemon's certificate carries: its card lowercased."""
    calling_card.split(card)          # refuses anything that isn't a card
    return calling_card.lowercase(card)


def topic_name(card: str) -> str:
    """How a card appears in a topic: lowercased, like its certificate's name (R164)."""
    return cert_name(card)


def source_topic(card: str, source: str) -> str:
    """The topic a source's events publish on: its name split on ``_`` into levels, so a family
    of sources is one filter (``pd_entry_due`` -> ``<card>/events/pd/entry/due``)."""
    if not source or any(c in source for c in "#+/") or source.startswith("_") or "__" in source:
        raise BrokerRefused(f"not a source name: {source!r}")
    return f"{topic_name(card)}/events/" + source.replace("_", "/")


def grant_filters(card: str, grant: str, known: Iterable[str]) -> List[str]:
    """The topic filters a granted source or glob becomes. A glob ending ``_*`` on a level boundary
    is one ``#`` filter; any other glob is expanded against the sources the code defines, since
    MQTT filters match whole levels only."""
    import fnmatch
    if not any(c in grant for c in "*?["):
        return [source_topic(card, grant)]
    prefix = grant[:-2]
    if grant.endswith("_*") and prefix and not any(c in prefix for c in "*?["):
        return [source_topic(card, prefix) + "/#"]
    return sorted(source_topic(card, s) for s in set(known) if fnmatch.fnmatchcase(s, grant))


def routed_topic(card: str, reader: str, source: str) -> str:
    """Where a source the operator routed to *reader* publishes instead of its own topic
    (MIS-0002-R152): under the reader's own subtree, ``<card>/routed/<reader>/...``, which no
    wildcard grant on ``<card>/events/`` matches, so the other readers stop receiving it without a
    rule that denies (mosquitto's access rules only allow)."""
    return f"{topic_name(card)}/routed/{topic_name(reader)}/" + source_topic(card, source).split("/events/", 1)[1]


def reader_filters(card: str, reader: str, grants: Iterable[str], known: Iterable[str]) -> List[str]:
    """Every topic filter *reader* may read for its *grants*: each source's own topic, and the
    same source routed to it. A route chooses who of the granted receives a source; it never
    widens a grant."""
    events_root, routed_root = f"{topic_name(card)}/events/", f"{topic_name(card)}/routed/{topic_name(reader)}/"
    out = set()
    for grant in grants:
        for f in grant_filters(card, grant, known):
            out.add(f)
            out.add(routed_root + f[len(events_root):])
    return sorted(out)


@dataclass(frozen=True, kw_only=True)
class Message:
    """One record as published: where, what, and the positions a subscriber checks."""
    topic: str
    payload: bytes
    properties: Dict[str, str]


#: The topic level a daemon-side gap publishes on, under ``<card>/events/``. No source can take
#: it: ``source_topic`` refuses a name beginning with ``_``.
GAP_LEVEL = "_gap"


def position_key(position: dict) -> str:
    """A stream position as one string, ``<log>:<offset>``: the log's identity and the byte
    offset just past the record. A rotated log has another identity, so its positions never
    equal the old log's."""
    return f"{position['log']}:{position['offset']}"


def to_message(card: str, stream_record: dict, previous_of_source: Optional[str],
               topic: Optional[str] = None) -> Message:
    """The message one stream record publishes as (R150, R154, R155 as amended): its source's
    topic, the stream record as JSON (its position, source, agent, time and origin travel inside
    it, set by the layer), and one user property, the position of the previous record of the
    same source. Only the daemon may publish under its own root, so no publisher can claim them."""
    import json
    source = stream_record.get("source")
    if not isinstance(source, str):
        raise BrokerRefused("a record without a source has no topic")
    props = {} if previous_of_source is None else {"previous": previous_of_source}
    return Message(topic=topic or source_topic(card, source),
                   payload=json.dumps(stream_record, separators=(",", ":")).encode(), properties=props)


def gap_message(card: str, gap_from: dict, gap_to: dict, reason: str, time: float) -> Message:
    """A daemon-side gap (``rotated``, ``overflow``) as every subscriber sees it, on
    ``<card>/events/_gap``: records between the two positions may be missing."""
    import json
    body = {"type": "gap", "agent": card, "time": time, "from": gap_from, "to": gap_to, "reason": reason}
    return Message(topic=f"{topic_name(card)}/events/{GAP_LEVEL}",
                   payload=json.dumps(body, separators=(",", ":")).encode(), properties={})


class GapTracker:
    """A subscriber's view of gaps (R154). Each message carries the position of the previous
    record of the same source; a subscriber that filters by source sees global positions skip by
    design, so it compares per source."""

    def __init__(self) -> None:
        self.last: Dict[str, str] = {}

    def observe(self, source: str, position: str, previous: Optional[str]) -> bool:
        """Record a message; True when records of this source were missed before it."""
        seen = self.last.get(source)
        self.last[source] = position
        return seen is not None and previous != seen


def replay_topics(card: str, reader: str) -> Dict[str, str]:
    """The two topics of one reader's replay: the request it writes and the records only it reads."""
    root = f"{topic_name(card)}/replay/{topic_name(reader)}"
    return {"request": f"{root}/request", "records": f"{root}/records"}


#: The most log bytes one replay reads in one pass of the daemon's loop. A replay from an old
#: position takes several passes, so no reader's request holds up the loop (R153).
REPLAY_CHUNK_BYTES = 64 * 1024

_REQUEST_SHAPE = "a replay request names a position {log, offset} and a non-empty list of sources"


def _marker(topic: str, body: dict) -> Message:
    import json
    return Message(topic=topic, payload=json.dumps(body, separators=(",", ":")).encode(), properties={})


def _read_request(request) -> Optional[Tuple[dict, List[str]]]:
    """The position and sources a replay request names; None when it can't be read."""
    at = request.get("position") if isinstance(request, dict) else None
    sources = request.get("sources") if isinstance(request, dict) else None
    if (not isinstance(at, dict) or not isinstance(at.get("log"), str) or not isinstance(at.get("offset"), int)
            or isinstance(at.get("offset"), bool) or at["offset"] < 0
            or not isinstance(sources, list) or not sources or not all(isinstance(s, str) for s in sources)):
        return None
    return at, sources


@dataclass
class Replay:
    """One reader's replay in flight: where it has read to, what it asked for, what it may have."""
    reader: str
    sources: List[str]
    granted: Optional[Sequence[str]]
    log: str
    offset: int
    #: Whether the operator's rules deliver a source to this reader now (MIS-0002-R152), read live.
    delivers: Optional[Callable[[str], bool]] = None

    def wanted(self, source: str) -> bool:
        import fnmatch
        return (any(fnmatch.fnmatchcase(source, s) for s in self.sources)
                and (self.granted is None or any(fnmatch.fnmatchcase(source, g) for g in self.granted))
                and (self.delivers is None or self.delivers(source)))

    def step(self, stream, max_bytes: Optional[int]) -> Tuple[List[Message], bool]:
        """One pass: the messages for at most *max_bytes* of log, and whether the replay is done.
        A pass carries a gap when records are gone (from the start, or because the log moved on
        past the catch-up bound meanwhile); the last ends with ``done`` at the position the live
        stream continues from."""
        import json
        topic = replay_topics(stream.card, self.reader)["records"]
        chunk = stream.since_chunk(self.log, self.offset, max_bytes)
        out: List[Message] = []
        if chunk.gap is not None:
            gap_from, gap_to, reason = chunk.gap
            out.append(_marker(topic, {"type": "gap", "agent": stream.card, "from": gap_from, "to": gap_to,
                                       "reason": reason}))
        out += [Message(topic=topic, payload=json.dumps(r, separators=(",", ":")).encode(), properties={})
                for r in chunk.records if self.wanted(r["source"])]
        if chunk.next is not None:
            self.log, self.offset = chunk.next["log"], chunk.next["offset"]
        if chunk.at_end:
            out.append(_marker(topic, {"type": "done", "agent": stream.card, "position": stream.position()}))
        return out, chunk.at_end


def replay_messages(stream, reader: str, request: dict, granted: Optional[Sequence[str]]) -> List[Message]:
    """The whole answer to one reader's replay request at once (R154 as amended): the records
    since the position it names, of the sources it asks for and was granted, on its own records
    topic, after a gap when some are gone, and ending with ``done`` at the position the live
    stream continues from. ``granted`` None is the daemon's own reader, granted everything. A
    request that can't be read gets a ``refused`` marker, so the reader is never left waiting.
    The daemon answers in bounded passes through ``ReplayResponder``; this is the same answer."""
    read = _read_request(request)
    if read is None:
        return [_marker(replay_topics(stream.card, reader)["records"], {"type": "refused", "error": _REQUEST_SHAPE})]
    at, sources = read
    replay = Replay(reader=reader, sources=sources, granted=granted, log=at["log"], offset=at["offset"])
    out: List[Message] = []
    done = False
    while not done:
        messages, done = replay.step(stream, None)
        out += messages
    return out


@dataclass
class ReplayResponder:
    """The daemon's side of replay: each request a granted reader writes on its own request
    topic is answered from the log on its own records topic. ``grants`` maps a reader's card to
    the sources it was granted; a request from a card with no grant gets nothing, and the broker
    would not have let it write there in the first place.

    At most one replay per reader is in flight. A reader's newer request replaces its older one,
    whose records already sent are harmless (a reader drops duplicates), so every request is
    either answered to ``done`` or replaced by a later one of the same reader, and none is
    dropped unanswered. Each pass reads at most ``REPLAY_CHUNK_BYTES`` per reader (R153)."""
    stream: object
    publish: object
    grants: Dict[str, Sequence[str]]
    in_flight: Dict[str, Replay] = field(default_factory=dict)
    #: ``delivers(source, reader)``: the operator's rules, read live (MIS-0002-R152). None delivers all.
    delivers: Optional[Callable[[str, str], bool]] = None

    def __post_init__(self) -> None:
        self.grants = {topic_name(r): g for r, g in self.grants.items()}

    def reader_of(self, topic: str) -> Optional[str]:
        """The granted reader whose request topic this is; None for any other topic."""
        prefix, suffix = f"{topic_name(self.stream.card)}/replay/", "/request"
        if not (topic.startswith(prefix) and topic.endswith(suffix)):
            return None
        reader = topic[len(prefix):-len(suffix)]
        return reader if reader in self.grants else None

    def request(self, reader: str, payload: bytes) -> int:
        """Take one reader's request: a refusal is published at once (the count), a readable one
        starts or replaces that reader's replay."""
        import json
        reader = topic_name(reader)
        try:
            read = _read_request(json.loads(payload))
        except ValueError:
            read = None
        if read is None:
            self.in_flight.pop(reader, None)
            self.publish(_marker(replay_topics(self.stream.card, reader)["records"],
                                 {"type": "refused", "error": _REQUEST_SHAPE}))
            return 1
        at, sources = read
        rules = self.delivers
        self.in_flight[reader] = Replay(reader=reader, sources=sources, granted=self.grants[reader],
                                        log=at["log"], offset=at["offset"],
                                        delivers=None if rules is None else (lambda s, r=reader: rules(s, r)))
        return 0

    def pump(self, max_bytes: int = REPLAY_CHUNK_BYTES) -> int:
        """One pass over the replays in flight, each reading at most *max_bytes*; the number of
        messages published. A replay whose publish fails stays in flight and repeats its pass."""
        sent = 0
        for reader, replay in list(self.in_flight.items()):
            saved = (replay.log, replay.offset)
            messages, done = replay.step(self.stream, max_bytes)
            try:
                for message in messages:
                    self.publish(message)
                    sent += 1
            except (ConnectionError, OSError):
                replay.log, replay.offset = saved
                raise
            if done:
                del self.in_flight[reader]
        return sent

    def handle(self, topic: str, payload: bytes) -> int:
        """Take one request message and answer it to the end at once; the number published.
        For a reader driven outside the daemon loop (a test, a tool); the daemon uses
        ``request`` and ``pump``."""
        reader = self.reader_of(topic)
        if reader is None:
            return 0
        sent = self.request(reader, payload)
        while reader in self.in_flight:
            sent += self.pump()
        return sent


class CatchUp:
    """A reader's view of one daemon's stream: live messages and replayed ones, in log order,
    each delivered once. It remembers the last position it delivered; after a reconnect it asks
    for a replay from there, delivers the replayed records it hasn't seen, and drops the live
    messages that the replay already covered (R154 as amended)."""

    def __init__(self, deliver):
        self.deliver = deliver
        self.seen: Optional[dict] = None      # position just past the last record delivered
        self.gaps: List[dict] = []
        self.replaying = False
        self.held: List[dict] = []            # live records that arrived during a replay

    def _take(self, record: dict) -> None:
        pos = record["position"]
        if self.seen is not None and pos["log"] == self.seen["log"] and pos["offset"] <= self.seen["offset"]:
            return                            # a duplicate: the replay or the live stream already gave it
        self.seen = pos
        self.deliver(record)

    def request(self, sources: Sequence[str]) -> Optional[dict]:
        """The replay request to send after (re)connecting, from the last position delivered;
        None for a reader that has delivered nothing, which takes the stream from now. Live
        records are held from here until the replay is done, so none overtakes an older one."""
        if self.seen is None:
            return None
        self.replaying = True
        return {"position": self.seen, "sources": list(sources)}

    def live(self, payload: bytes) -> None:
        import json
        body = json.loads(payload)
        if body.get("type") == "record":
            if self.replaying:
                self.held.append(body)
            else:
                self._take(body)
        elif body.get("type") == "gap":
            self.gaps.append(body)

    def replayed(self, payload: bytes) -> bool:
        """One message on the reader's records topic; True once the replay is done, when the
        live records held meanwhile are delivered after it."""
        import json
        body = json.loads(payload)
        kind = body.get("type")
        if kind == "record":
            self._take(body)
        elif kind == "gap":
            self.gaps.append(body)
        if kind in ("done", "refused"):
            self.replaying = False
            held, self.held = self.held, []
            for record in held:
                self._take(record)
            return True
        return False


def paho_publish(client, *, timeout: float = 5.0):
    """``Publisher``'s ``publish`` over a connected paho-mqtt client: QoS 1, MQTT 5 user
    properties, and an exception unless the broker acknowledged the message within *timeout*,
    so the record stays pending (the prototype waits per message; batching is later work)."""
    from paho.mqtt.packettypes import PacketTypes
    from paho.mqtt.properties import Properties

    def publish(message: Message) -> None:
        props = Properties(PacketTypes.PUBLISH)
        props.UserProperty = list(message.properties.items())
        info = client.publish(message.topic, message.payload, qos=1, properties=props)
        info.wait_for_publish(timeout)
        if not info.is_published():
            raise ConnectionError(f"the broker didn't acknowledge {message.topic} within {timeout:g} s")
    return publish


#: The most records held for a publish that keeps failing before they are dropped for a gap.
PENDING_MAX = 1000


def seed_previous(log_path, identity: Optional[str], offset: int, max_bytes: int) -> Dict[str, str]:
    """The position of the last record of each source before *offset*, read back at most
    *max_bytes*: what the publisher's first message of each source names as its previous, so a
    subscriber that saw records before a daemon restart doesn't read the restart as a gap, and one
    that missed records written while the daemon was down does."""
    import json
    if identity is None or offset == 0:
        return {}
    start = max(0, offset - max_bytes)
    with open(log_path, "rb") as f:
        f.seek(start)
        chunk = f.read(offset - start)
    if start > 0:
        cut = chunk.find(b"\n")         # a partial first line names no record
        if cut < 0:
            return {}
        chunk, start = chunk[cut + 1:], start + cut + 1
    seen: Dict[str, str] = {}
    end = start
    for line in chunk.split(b"\n")[:-1]:    # the part after the last newline is no full line
        end += len(line) + 1
        try:
            event = json.loads(line).get("event")
        except (ValueError, AttributeError):
            event = None    # noqa: MACEFF003 - a line that isn't a record names no source
        if isinstance(event, str):
            seen[event] = f"{identity}:{end}"
    return seen


class Publisher:
    """Puts a daemon's stream on its own broker: every record the log gains, in order, at QoS 1,
    each naming the previous position of its own source. ``publish`` hands one message to the
    MQTT client and raises when it can't; the record then stays pending and is retried first on
    the next pump, so a broken connection delays records and loses none until ``PENDING_MAX``,
    where the backlog is dropped and a gap published in its place (R153)."""

    def __init__(self, stream, publish, *, wall=None, max_seed_bytes: int = 8 * 1024 * 1024,
                 silenced: Optional[Callable[[str], bool]] = None,
                 routed: Optional[Callable[[str], Optional[List[str]]]] = None):
        import time as _time
        self.stream = stream
        self.publish = publish
        #: Whether the operator has silenced a source (MIS-0002-R152): its records aren't published.
        self.silenced = silenced or (lambda source: False)
        #: The readers the operator routed a source to (R152), or None where it isn't routed: a
        #: routed record publishes on each one's routed subtree instead of its source's topic.
        self.routed = routed or (lambda source: None)
        self._wall = wall or _time.time
        self.previous = seed_previous(stream.log_path, stream.identity, stream.offset, max_seed_bytes)
        self.pending: List[object] = []     # stream records, or ready Messages (gaps)

    def pump(self) -> int:
        """One pass: take what the log gained, publish what is pending; the count published."""
        records, gap = self.stream.take()
        if gap is not None:
            self.pending.append(gap_message(self.stream.card, gap[0], gap[1], "rotated", self._wall()))
        self.pending.extend(r for r in records if not self.silenced(r["source"]))
        if len(self.pending) > PENDING_MAX:
            first = next((r["position"] for r in self.pending if isinstance(r, dict)), None)
            last = next((r["position"] for r in reversed(self.pending) if isinstance(r, dict)), None)
            self.pending = [gap_message(self.stream.card, first, last, "overflow", self._wall())]
        sent = 0
        while self.pending:
            item = self.pending[0]
            if isinstance(item, Message):
                self.publish(item)
            else:
                source = item["source"]
                readers = self.routed(source)
                topics = [None] if readers is None else [routed_topic(self.stream.card, r, source) for r in readers]
                for topic in topics:
                    self.publish(to_message(self.stream.card, item, self.previous.get(source), topic))
                self.previous[source] = position_key(item["position"])
            self.pending.pop(0)
            sent += 1
        return sent


def render_access_rules(card: str, *, members: Sequence[str] = (), association: bool = False,
               readers: Optional[Dict[str, Iterable[str]]] = None,
               known_sources: Iterable[str] = (), silenced_readers: Iterable[str] = ()) -> str:
    """The broker's access rules: one ``user`` block per certificate the declaration names. A
    reader the operator silenced (``@<card>``, MIS-0002-R152) keeps its named block with no
    topics, so it reads nothing, live or replayed, until the rule is lifted."""
    if members and not association:
        raise BrokerRefused("only an association admits members")
    silent = {topic_name(r) for r in silenced_readers}
    blocks: List[str] = [f"user {cert_name(card)}\ntopic readwrite {topic_name(card)}/#"]
    if association:
        blocks[0] += "\ntopic read members/#"
    for member in members:
        blocks.append(f"user {cert_name(member)}\ntopic write members/{topic_name(member)}/#")
    for reader, sources in sorted((readers or {}).items()):
        lines = [f"user {cert_name(reader)}"]
        if topic_name(reader) in silent:
            blocks.append("\n".join(lines))
            continue
        lines += [f"topic read {f}" for f in reader_filters(card, reader, sources, known_sources)]
        replay = replay_topics(card, reader)       # its own replay, and no other reader's
        lines += [f"topic write {replay['request']}", f"topic read {replay['records']}"]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def render_conf(*, port: int, listen: str, certificate_authority_file: str, certificate_file: str, key_file: str,
                access_rules_file: str, association: bool = False, crlfile: Optional[str] = None,
                lan_address: Optional[str] = None) -> str:
    """mosquitto.conf for one daemon's broker: one TLS listener, certificates required, the
    certificate's name as the user, and the rendered access rules."""
    if not 1024 <= port <= 65535:
        raise BrokerRefused(f"the broker's port must be 1024 to 65535, not {port}")
    if listen == "lan":
        if not association:
            raise BrokerRefused("only an association listens on the LAN; a daemon's own broker "
                                "listens on loopback")
        if not lan_address:
            raise BrokerRefused("a LAN listener names the address it binds")
        bind = lan_address
    elif listen in LISTEN:
        bind = LISTEN[listen]
    else:
        raise BrokerRefused(f"listen is loopback or lan, not {listen!r}")
    lines = [
        "per_listener_settings false",
        "allow_anonymous false",
        f"listener {port} {bind}",
        f"cafile {certificate_authority_file}",
        f"certfile {certificate_file}",
        f"keyfile {key_file}",
        "require_certificate true",
        "use_identity_as_username true",
        f"acl_file {access_rules_file}",
    ]
    if crlfile:
        lines.append(f"crlfile {crlfile}")
    return "\n".join(lines) + "\n"
