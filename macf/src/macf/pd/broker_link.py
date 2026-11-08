"""The daemon's link to its own broker (PROTOTYPE, mission B phase B2).

At start the daemon renders the broker's configuration and access rules from the declaration's
``broker`` section into its runtime directory. The broker process is a declared unit running
mosquitto on that file, so the supervision engine starts, watches and restarts it like any unit.

On every pass of the daemon's loop the link publishes what the log gained and answers replay
requests. Nothing here blocks the loop (MIS-0002-R153):
- the publisher has its own log follower, so it never races the socket stream's offsets;
- a publish hands the message to the MQTT client's queue and returns, and a refusal (not
  connected, queue full) leaves the record pending for the next pass;
- replay requests arrive on the client's network thread and are only queued there, then
  answered on the daemon's thread, where the log is read.
"""
import collections
import threading
import time
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

from macf.pd import association as assoc
from macf.pd import broker as b
from macf.pd.interface import AssociationLink, BrokerSection
from macf.pd.stream import EventStream

#: Seconds between reconnect attempts, at most, while the broker is unreachable.
RECONNECT_MAX_S = 30


def resolve(path: str, placeholders: Dict[str, str]) -> str:
    """A declared path with the declaration's placeholders filled in."""
    return path.format_map(placeholders)


def render_files(card: str, section: BrokerSection, runtime: Path, placeholders: Dict[str, str],
                 known_sources=(), members: Sequence[str] = ()) -> Path:
    """Write the broker's access rules and configuration under *runtime*; the configuration's
    path, which the broker unit's command names. With *members*, the broker is an association's:
    each member may write its own subtree, and only this daemon reads them."""
    d = Path(runtime) / f"{card}.broker"
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o700)
    acl = d / "acl"
    acl.write_text(b.render_acl(card, readers=section.readers, known_sources=known_sources,
                                members=members, association=bool(members)))
    conf = d / "mosquitto.conf"
    conf.write_text(b.render_conf(port=section.port, listen="loopback",
                                  cafile=resolve(section.cafile, placeholders),
                                  certfile=resolve(section.server_certfile, placeholders),
                                  keyfile=resolve(section.server_keyfile, placeholders),
                                  acl_file=str(acl), association=bool(members)) + "persistence false\n")
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
        publish = nowait_publish(self.client)
        self.publisher = b.Publisher(self.stream, publish)
        self.responder = b.ReplayResponder(self.stream, publish, section.readers)
        self.requests: Deque[Tuple[str, bytes]] = collections.deque(maxlen=100)
        self._lock = threading.Lock()
        self.client.on_message = self._on_message
        self.client.on_connect = self._on_connect
        self.last_error: Optional[str] = None

    @staticmethod
    def _client(section: BrokerSection, placeholders: Dict[str, str]):
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        c.tls_set(ca_certs=resolve(section.cafile, placeholders),
                  certfile=resolve(section.client_certfile, placeholders),
                  keyfile=resolve(section.client_keyfile, placeholders))
        c.reconnect_delay_set(1, RECONNECT_MAX_S)
        return c

    def _on_connect(self, client, _userdata, _flags, _reason, _props=None) -> None:
        client.subscribe(f"{self.card}/replay/+/request", qos=1)
        if self.view is not None:
            client.subscribe("members/#", qos=1)

    def _on_message(self, _client, _userdata, message) -> None:
        with self._lock:                       # the network thread only queues
            if message.topic.startswith("members/"):
                self.member_messages.append((message.topic, bytes(message.payload)))
            else:
                self.requests.append((message.topic, bytes(message.payload)))

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
        self.client.connect_async("localhost", self.section.port)
        self.client.loop_start()

    def tick(self) -> int:
        """One pass on the daemon's thread: answer queued replays, publish what the log gained.
        A failure is kept in ``last_error`` and the records stay pending; it never raises."""
        sent = 0
        with self._lock:
            requests, self.requests = list(self.requests), collections.deque(maxlen=100)
        try:
            for topic, payload in requests:
                sent += self.responder.handle(topic, payload)
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


class ExportLink:
    """A member daemon's link to its association's broker: its presence (retained ``online``,
    with ``offline`` as its will) and its exports, summaries only, through ``Exporter``."""

    def __init__(self, card: str, log_path: Path, link: AssociationLink, placeholders: Dict[str, str],
                 *, client=None):
        self.card, self.link = card, link
        self.client = client if client is not None else self._client(card, link, placeholders)
        self.exporter = assoc.Exporter(card, EventStream(card, log_path), nowait_publish(self.client),
                                       link.exports)
        self.client.on_connect = self._on_connect
        self.last_error: Optional[str] = None

    @staticmethod
    def _client(card: str, link: AssociationLink, placeholders: Dict[str, str]):
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        c.tls_set(ca_certs=resolve(link.cafile, placeholders),
                  certfile=resolve(link.client_certfile, placeholders),
                  keyfile=resolve(link.client_keyfile, placeholders))
        c.will_set(assoc.presence_topic(card), b"offline", qos=1, retain=True)
        c.reconnect_delay_set(1, RECONNECT_MAX_S)
        return c

    def _on_connect(self, client, _userdata, _flags, _reason, _props=None) -> None:
        client.publish(assoc.presence_topic(self.card), b"online", qos=1, retain=True)

    def start(self) -> None:
        self.client.connect_async(self.link.host, self.link.port)
        self.client.loop_start()

    def tick(self) -> int:
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
