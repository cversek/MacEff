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
from pathlib import Path
from typing import Deque, Dict, Optional, Tuple

from macf.pd import broker as b
from macf.pd.interface import BrokerSection
from macf.pd.stream import EventStream

#: Seconds between reconnect attempts, at most, while the broker is unreachable.
RECONNECT_MAX_S = 30


def resolve(path: str, placeholders: Dict[str, str]) -> str:
    """A declared path with the declaration's placeholders filled in."""
    return path.format_map(placeholders)


def render_files(card: str, section: BrokerSection, runtime: Path, placeholders: Dict[str, str],
                 known_sources=()) -> Path:
    """Write the broker's access rules and configuration under *runtime*; the configuration's
    path, which the broker unit's command names."""
    d = Path(runtime) / f"{card}.broker"
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o700)
    acl = d / "acl"
    acl.write_text(b.render_acl(card, readers=section.readers, known_sources=known_sources))
    conf = d / "mosquitto.conf"
    conf.write_text(b.render_conf(port=section.port, listen="loopback",
                                  cafile=resolve(section.cafile, placeholders),
                                  certfile=resolve(section.server_certfile, placeholders),
                                  keyfile=resolve(section.server_keyfile, placeholders),
                                  acl_file=str(acl)) + "persistence false\n")
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
    """One daemon's publisher and replay responder, over one MQTT client."""

    def __init__(self, card: str, log_path: Path, section: BrokerSection, placeholders: Dict[str, str],
                 *, client=None):
        self.card = card
        self.section = section
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

    def _on_message(self, _client, _userdata, message) -> None:
        with self._lock:                       # the network thread only queues
            self.requests.append((message.topic, bytes(message.payload)))

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
        return sent

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
