"""The daemon's link to its own broker (PROTOTYPE, mission B phase B2).

At start the daemon renders the broker's configuration and access rules from the declaration's
``broker`` section into its runtime directory. The broker process is a declared unit running
mosquitto on that file, so the supervision engine starts, watches and restarts it like any unit.

On every pass of the daemon's loop the link publishes what the log gained and answers replay
requests. Nothing here blocks the loop (MIS-0002-R153):
- the publisher has its own log follower, so it never races the socket stream's offsets;
- a publish hands the message to the MQTT client's queue and returns, and a refusal (not
  connected, queue full) leaves the record pending for the next pass;
- replay requests arrive on the client's network thread and are only queued there, one slot
  per granted reader, then answered on the daemon's thread in bounded passes, where the log is
  read (``broker.ReplayResponder``).
"""
import collections
import errno
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

from macf import calling_card
from macf.pd import association as assoc
from macf.pd import broker as b
from macf.pd.interface import AssociationLink, BrokerSection
from macf.pd.stream import EventStream

#: Seconds between reconnect attempts, at most, while the broker is unreachable.
RECONNECT_MAX_S = 30


def resolve(path: str, placeholders: Dict[str, str]) -> str:
    """A declared path with the declaration's placeholders filled in."""
    return path.format_map(placeholders)


def port_clash(card: str, port: int, others) -> Optional[str]:
    """Why *card*'s broker port can't be used: another declaration names the same port. Every
    daemon's broker binds the one loopback address, so two daemons naming a port means the
    second broker can't bind, and its link would reach the first daemon's broker, which refuses
    its certificate: it would read as "unreachable" with nothing naming the cause. *others* is
    ``(card, where, port)`` for each other declaration read."""
    for other, where, other_port in others:
        if other_port == port and not calling_card.same(other, card):
            return (f"the broker port {port} is already named by {other}'s declaration ({where}); "
                    f"each daemon on a host needs its own broker port")
    return None


def declared_broker_ports(own_home: Path, homes: Optional[Sequence[Path]] = None):
    """``(card, where, port)`` for each other declaration on this host that names a broker and
    that this account can read: the deployment's declared daemons and the homes under /home. A
    declaration this account can't read is skipped; its daemon's own start makes the same check."""
    import json
    from macf.pd import shared_view
    from macf.pd.names import declaration_path
    if homes is None:
        candidates = [h for h in shared_view.declared_homes() if isinstance(h, Path)]
        try:
            candidates += sorted(p for p in shared_view.HOMES.iterdir())
        except OSError:
            pass  # noqa: MACEFF003 - no /home listing: only the declared daemons are checked
    else:
        candidates = list(homes)
    own = Path(own_home).resolve()
    out, seen = [], set()
    for home in candidates:
        try:
            if Path(home).resolve() == own:
                continue
            path = declaration_path(Path(home))
            if path in seen:
                continue
            seen.add(path)
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            continue  # noqa: MACEFF003 - unreadable or absent: that daemon's start checks for itself
        broker = doc.get("broker") if isinstance(doc, dict) else None
        if isinstance(broker, dict) and isinstance(broker.get("port"), int):
            out.append((str(doc.get("agent", "?")), str(path), broker["port"]))
    return out


def render_files(card: str, section: BrokerSection, runtime: Path, placeholders: Dict[str, str],
                 known_sources=(), members: Sequence[str] = ()) -> Path:
    """Write the broker's access rules and configuration under *runtime*; the configuration's
    path, which the broker unit's command names. With *members*, the broker is an association's:
    each member may write its own subtree, and only this daemon reads them."""
    Path(runtime).mkdir(mode=0o700, parents=True, exist_ok=True)    # never the umask's 0755
    d = Path(runtime) / f"{card}.broker"
    d.mkdir(mode=0o700, exist_ok=True)
    d.chmod(0o700)
    access_rules = d / "access_rules"
    access_rules.write_text(b.render_access_rules(card, readers=section.readers, known_sources=known_sources,
                                members=members, association=bool(members)))
    access_rules.chmod(0o600)          # mosquitto warns on a world-readable one, and will refuse it
    conf = d / "mosquitto.conf"
    conf.write_text(b.render_conf(port=section.port, listen="loopback",
                                  certificate_authority_file=resolve(section.certificate_authority_file, placeholders),
                                  certificate_file=resolve(section.server_certificate_file, placeholders),
                                  key_file=resolve(section.server_key_file, placeholders),
                                  access_rules_file=str(access_rules), association=bool(members)) + "persistence false\n")
    conf.chmod(0o600)
    return conf


def nowait_publish(client):
    """``Publisher``'s ``publish`` that never waits on the network: the message joins the
    client's queue at QoS 1, and a refusal raises so the record stays pending."""
    from paho.mqtt.packettypes import PacketTypes
    from paho.mqtt.properties import Properties

    def publish(message: b.Message) -> None:
        props = Properties(PacketTypes.PUBLISH)
        props.UserProperty = list(message.properties.items())
        info = client.publish(message.topic, message.payload, qos=1, properties=props)
        if info.rc != 0:
            raise ConnectionError(f"the MQTT client refused {message.topic}: rc {info.rc}")
    return publish


class BrokerLink:
    """One daemon's publisher and replay responder, over one MQTT client. For an association,
    also its view of its members: each change in what differs from the declaration is handed to
    ``on_findings`` once, for the daemon to record."""

    def __init__(self, card: str, log_path: Path, section: BrokerSection, placeholders: Dict[str, str],
                 *, client=None, members: Sequence[str] = (),
                 on_findings: Optional[Callable[[List[str]], None]] = None):
        self.card = card
        self.section = section
        self.view = assoc.MembershipView(expected=list(members)) if members else None
        self.on_findings = on_findings
        self.reported: Optional[List[str]] = None
        self.member_messages: Deque[Tuple[str, bytes]] = collections.deque(maxlen=1000)
        self.client = client if client is not None else self._client(section, placeholders)
        self.stream = EventStream(card, log_path)
        self.stream.start_at_end()      # readers catch up by replay; the past isn't re-published
        publish = nowait_publish(self.client)
        self.publisher = b.Publisher(self.stream, publish)
        self.responder = b.ReplayResponder(self.stream, publish, section.readers)
        #: The newest request of each granted reader not yet taken; a newer one replaces it.
        self.requests: Dict[str, bytes] = {}
        self._lock = threading.Lock()
        self.client.on_message = self._on_message
        self.client.on_connect = self._on_connect
        self.last_error: Optional[str] = None

    @staticmethod
    def _client(section: BrokerSection, placeholders: Dict[str, str]):
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        c.tls_set(ca_certs=resolve(section.certificate_authority_file, placeholders),
                  certfile=resolve(section.client_certificate_file, placeholders),
                  keyfile=resolve(section.client_key_file, placeholders))
        c.reconnect_delay_set(1, RECONNECT_MAX_S)
        return c

    def _on_connect(self, client, _userdata, _flags, _reason, _props=None) -> None:
        client.subscribe(f"{b.topic_name(self.card)}/replay/+/request", qos=1)
        if self.view is not None:
            client.subscribe("members/#", qos=1)

    def _on_message(self, _client, _userdata, message) -> None:
        with self._lock:                       # the network thread only queues
            if message.topic.startswith("members/"):
                self.member_messages.append((message.topic, bytes(message.payload)))
                return
            reader = self.responder.reader_of(message.topic)
            if reader is not None:
                self.requests[reader] = bytes(message.payload)

    def _members_tick(self, now: float) -> None:
        with self._lock:
            messages, self.member_messages = list(self.member_messages), collections.deque(maxlen=1000)
        for topic, payload in messages:
            self.view.observe(topic, payload, now)
        findings = self.view.findings(now)
        if findings != self.reported:
            self.reported = findings
            if self.on_findings is not None:
                self.on_findings(findings)

    def start(self) -> None:
        self.client.connect_async(b.LOOPBACK, self.section.port)
        self.client.loop_start()

    def tick(self) -> int:
        """One pass on the daemon's thread: take queued replay requests, answer each replay in
        flight for one bounded chunk, publish what the log gained. A failure is kept in
        ``last_error`` and the records stay pending; it never raises."""
        sent = 0
        with self._lock:
            requests, self.requests = self.requests, {}
        try:
            for reader, payload in requests.items():
                sent += self.responder.request(reader, payload)
            sent += self.responder.pump()
            sent += self.publisher.pump()
            self.last_error = None
        except (ConnectionError, OSError) as e:
            self.last_error = str(e)
        if self.view is not None:
            self._members_tick(time.time())
        return sent

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


#: What a person must grant when macOS blocks a process from the local network.
MACOS_LOCAL_NETWORK_GRANT = ("macOS Local Network privacy blocks this process from the LAN: a person "
                             "must grant it at the console, under System Settings > Privacy & Security > "
                             "Local Network. A LaunchAgent can't answer that prompt, so it waits until then")


def unreachable_reason(host: str, port: int, error: OSError, platform: str = sys.platform) -> str:
    """Why a connection to an association's broker failed, in words that name the cause. On
    macOS, EHOSTUNREACH to a LAN address is the Local Network privacy block, not an outage, and
    retrying won't clear it."""
    if platform == "darwin" and error.errno == errno.EHOSTUNREACH:
        return f"cannot reach {host}:{port}: {MACOS_LOCAL_NETWORK_GRANT}"
    return f"cannot reach {host}:{port}: {error.strerror or error}"


def probe(host: str, port: int, timeout: float = 2.0) -> Optional[OSError]:
    """The error a plain TCP connection to *host*:*port* meets, or None when it connects."""
    try:
        socket.create_connection((host, port), timeout=timeout).close()
    except OSError as e:
        return e
    return None


class ExportLink:
    """A member daemon's link to its association's broker: its presence (retained ``online``,
    with ``offline`` as its will) and its exports, summaries only, through ``Exporter``.

    When the connection fails, the client's network thread probes once to learn why and keeps
    the reason; the next pass on the daemon's thread hands each change of reason (or its clearing,
    as None) to ``on_unreachable`` once, so the daemon records the cause instead of a silence the
    association would read as "never present"."""

    def __init__(self, card: str, log_path: Path, link: AssociationLink, placeholders: Dict[str, str],
                 *, client=None, on_unreachable: Optional[Callable[[Optional[str]], None]] = None,
                 prober: Callable[[str, int], Optional[OSError]] = probe):
        self.card, self.link = card, link
        self.client = client if client is not None else self._client(card, link, placeholders)
        stream = EventStream(card, log_path)
        stream.start_at_end()           # exports what happens from now; the past stays home
        self.exporter = assoc.Exporter(card, stream, nowait_publish(self.client), link.exports)
        self.client.on_connect = self._on_connect
        self.client.on_connect_fail = self._on_connect_fail
        self.on_unreachable = on_unreachable
        self.prober = prober
        self.reason: Optional[str] = None           # written on the network thread
        self.reported: Optional[str] = None
        self.last_error: Optional[str] = None

    def _on_connect_fail(self, _client, _userdata) -> None:
        error = self.prober(self.link.host, self.link.port)
        self.reason = (unreachable_reason(self.link.host, self.link.port, error) if error is not None
                       else f"cannot connect to {self.link.host}:{self.link.port}: the broker refused the session")

    @staticmethod
    def _client(card: str, link: AssociationLink, placeholders: Dict[str, str]):
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        c.tls_set(ca_certs=resolve(link.certificate_authority_file, placeholders),
                  certfile=resolve(link.client_certificate_file, placeholders),
                  keyfile=resolve(link.client_key_file, placeholders))
        c.will_set(assoc.presence_topic(card), b"offline", qos=1, retain=True)
        c.reconnect_delay_set(1, RECONNECT_MAX_S)
        return c

    def _on_connect(self, client, _userdata, _flags, _reason, _props=None) -> None:
        self.reason = None
        client.publish(assoc.presence_topic(self.card), b"online", qos=1, retain=True)

    def start(self) -> None:
        self.client.connect_async(self.link.host, self.link.port)
        self.client.loop_start()

    def tick(self) -> int:
        reason = self.reason
        if reason != self.reported:
            self.reported = reason
            if self.on_unreachable is not None:
                self.on_unreachable(reason)
        try:
            sent = self.exporter.pump()
            self.last_error = None
            return sent
        except (ConnectionError, OSError) as e:
            self.last_error = str(e)
            return 0

    def stop(self) -> None:
        """A clean stop says offline itself: a will fires only on an unclean disconnect."""
        try:
            self.client.publish(assoc.presence_topic(self.card), b"offline", qos=1, retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError):
            pass  # noqa: MACEFF003 - not connected: the will or the association's silence covers it
        self.client.loop_stop()
        self.client.disconnect()
