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
"""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from macf import calling_card

LISTEN = {"loopback": "127.0.0.1"}


class BrokerRefused(ValueError):
    """A broker declaration that can't be rendered, with the reason."""


def cert_name(card: str) -> str:
    """The Common Name a daemon's certificate carries: its card lowercased."""
    calling_card.split(card)          # refuses anything that isn't a card
    return calling_card.lowercase(card)


def source_topic(card: str, source: str) -> str:
    """The topic a source's events publish on: its name split on ``_`` into levels, so a family
    of sources is one filter (``pd_entry_due`` -> ``<card>/events/pd/entry/due``)."""
    if not source or any(c in source for c in "#+/") or source.startswith("_") or "__" in source:
        raise BrokerRefused(f"not a source name: {source!r}")
    return f"{card}/events/" + source.replace("_", "/")


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


def to_message(card: str, stream_record: dict, previous_of_source: Optional[str]) -> Message:
    """The message one stream record publishes as (R150, R154, R155 as amended): its source's
    topic, the stream record as JSON (its position, source, agent, time and origin travel inside
    it, set by the layer), and one user property, the position of the previous record of the
    same source. Only the daemon may publish under its own root, so no publisher can claim them."""
    import json
    source = stream_record.get("source")
    if not isinstance(source, str):
        raise BrokerRefused("a record without a source has no topic")
    props = {} if previous_of_source is None else {"previous": previous_of_source}
    return Message(topic=source_topic(card, source),
                   payload=json.dumps(stream_record, separators=(",", ":")).encode(), properties=props)


def gap_message(card: str, gap_from: dict, gap_to: dict, reason: str, time: float) -> Message:
    """A daemon-side gap (``rotated``, ``overflow``) as every subscriber sees it, on
    ``<card>/events/_gap``: records between the two positions may be missing."""
    import json
    body = {"type": "gap", "agent": card, "time": time, "from": gap_from, "to": gap_to, "reason": reason}
    return Message(topic=f"{card}/events/{GAP_LEVEL}",
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
    return {"request": f"{card}/replay/{reader}/request", "records": f"{card}/replay/{reader}/records"}


def replay_messages(stream, reader: str, request: dict, granted: Optional[Sequence[str]]) -> List[Message]:
    """The answer to one reader's replay request (R154 as amended): the records since the
    position it names, of the sources it asks for and was granted, on its own records topic,
    after a gap when some are gone, and ending with ``done`` at the position the live stream
    continues from. ``granted`` None is the daemon's own reader, granted everything. A request
    that can't be read gets a ``refused`` marker, so the reader is never left waiting."""
    import fnmatch
    import json
    card = stream.card
    topic = replay_topics(card, reader)["records"]

    def marker(body: dict) -> Message:
        return Message(topic=topic, payload=json.dumps(body, separators=(",", ":")).encode(), properties={})

    at = request.get("position") if isinstance(request, dict) else None
    sources = request.get("sources") if isinstance(request, dict) else None
    if (not isinstance(at, dict) or not isinstance(at.get("log"), str) or not isinstance(at.get("offset"), int)
            or isinstance(at.get("offset"), bool) or at["offset"] < 0
            or not isinstance(sources, list) or not sources or not all(isinstance(s, str) for s in sources)):
        return [marker({"type": "refused", "error": "a replay request names a position {log, offset} "
                                                    "and a non-empty list of sources"})]

    def wanted(source: str) -> bool:
        return (any(fnmatch.fnmatchcase(source, s) for s in sources)
                and (granted is None or any(fnmatch.fnmatchcase(source, g) for g in granted)))

    gap, records = stream.since(at["log"], at["offset"])
    out: List[Message] = []
    if gap is not None:
        out.append(marker({"type": "gap", "agent": card, "from": gap[0], "to": gap[1], "reason": gap[2]}))
    out += [Message(topic=topic, payload=json.dumps(r, separators=(",", ":")).encode(), properties={})
            for r in records if wanted(r["source"])]
    out.append(marker({"type": "done", "agent": card, "position": stream.position()}))
    return out


class ReplayResponder:
    """The daemon's side of replay: each request a granted reader writes on its own request
    topic is answered from the log on its own records topic. ``grants`` maps a reader's card to
    the sources it was granted; a request from a card with no grant gets nothing, and the broker
    would not have let it write there in the first place."""

    def __init__(self, stream, publish, grants: Dict[str, Sequence[str]]):
        self.stream, self.publish, self.grants = stream, publish, dict(grants)

    def handle(self, topic: str, payload: bytes) -> int:
        """Answer one request message; the number of messages published."""
        import json
        prefix, suffix = f"{self.stream.card}/replay/", "/request"
        if not (topic.startswith(prefix) and topic.endswith(suffix)):
            return 0
        reader = topic[len(prefix):-len(suffix)]
        if reader not in self.grants:
            return 0
        try:
            request = json.loads(payload)
        except ValueError:
            request = None
        out = replay_messages(self.stream, reader, request, self.grants[reader])
        for message in out:
            self.publish(message)
        return len(out)


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

    def __init__(self, stream, publish, *, wall=None, max_seed_bytes: int = 8 * 1024 * 1024):
        import time as _time
        self.stream = stream
        self.publish = publish
        self._wall = wall or _time.time
        self.previous = seed_previous(stream.log_path, stream.identity, stream.offset, max_seed_bytes)
        self.pending: List[object] = []     # stream records, or ready Messages (gaps)

    def pump(self) -> int:
        """One pass: take what the log gained, publish what is pending; the count published."""
        records, gap = self.stream.take()
        if gap is not None:
            self.pending.append(gap_message(self.stream.card, gap[0], gap[1], "rotated", self._wall()))
        self.pending.extend(records)
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
                self.publish(to_message(self.stream.card, item, self.previous.get(source)))
                self.previous[source] = position_key(item["position"])
            self.pending.pop(0)
            sent += 1
        return sent


def render_acl(card: str, *, members: Sequence[str] = (), association: bool = False,
               readers: Optional[Dict[str, Iterable[str]]] = None,
               known_sources: Iterable[str] = ()) -> str:
    """The broker's access rules: one ``user`` block per certificate the declaration names."""
    if members and not association:
        raise BrokerRefused("only an association admits members")
    blocks: List[str] = [f"user {cert_name(card)}\ntopic readwrite {card}/#"]
    if association:
        blocks[0] += "\ntopic read members/#"
    for member in members:
        blocks.append(f"user {cert_name(member)}\ntopic write members/{member}/#")
    for reader, sources in sorted((readers or {}).items()):
        lines = [f"user {cert_name(reader)}"]
        filters = sorted({f for s in sources for f in grant_filters(card, s, known_sources)})
        lines += [f"topic read {f}" for f in filters]
        replay = replay_topics(card, reader)       # its own replay, and no other reader's
        lines += [f"topic write {replay['request']}", f"topic read {replay['records']}"]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def render_conf(*, port: int, listen: str, cafile: str, certfile: str, keyfile: str,
                acl_file: str, association: bool = False, crlfile: Optional[str] = None,
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
        f"cafile {cafile}",
        f"certfile {certfile}",
        f"keyfile {keyfile}",
        "require_certificate true",
        "use_identity_as_username true",
        f"acl_file {acl_file}",
    ]
    if crlfile:
        lines.append(f"crlfile {crlfile}")
    return "\n".join(lines) + "\n"
