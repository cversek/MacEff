"""A daemon's own broker, live: mosquitto running the rendered configuration, with certificates
from a scratch CA (prototype, phase B2). Skipped where mosquitto, paho-mqtt or openssl is absent,
so it runs where the broker is installed and nowhere else. Every case here is a refusal shown
first, then the one path that is allowed."""
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

paho = pytest.importorskip("paho.mqtt.client")

from macf.pd.broker import Publisher, cert_name, paho_publish, render_acl, render_conf, replay_topics  # noqa: E402
from macf.pd.stream import EventStream  # noqa: E402

MOSQUITTO = shutil.which("mosquitto") or next(
    (str(p) for p in (Path(os.environ.get("CONDA_PREFIX", "/nonexistent")) / "sbin" / "mosquitto",)
     if p.exists()), None)
pytestmark = pytest.mark.skipif(not MOSQUITTO or not shutil.which("openssl"),
                                reason="mosquitto and openssl are needed for the live broker")

AGENT = "ExampleAgent_1a2b3c"
READER = "OtherAgent_4d5e6f"
SECOND = "SecondReader_7a8b9c"
STRANGER = "Stranger_0f0f0f"


def openssl(*args, cwd):
    subprocess.run(["openssl", *args], cwd=cwd, check=True, capture_output=True)


def issue(ca: Path, name: str) -> tuple:
    key, csr, crt = ca / f"{name}.key", ca / f"{name}.csr", ca / f"{name}.crt"
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", key.name, "-out", csr.name,
            "-subj", f"/CN={name}", cwd=ca)
    openssl("x509", "-req", "-in", csr.name, "-CA", "ca.crt", "-CAkey", "ca.key", "-CAcreateserial",
            "-days", "1", "-out", crt.name, cwd=ca)
    return str(crt), str(key)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def broker(tmp_path_factory):
    d = tmp_path_factory.mktemp("broker")
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.crt",
            "-days", "1", "-subj", "/CN=scratch-ca", cwd=d)
    certs = {n: issue(d, cert_name(n)) for n in (AGENT, READER, SECOND, STRANGER)}
    certs["server"] = issue(d, "localhost")
    (d / "acl").write_text(render_acl(AGENT, readers={READER: ["pd_unit_state"], SECOND: ["pd_unit_state"]}))
    port = free_port()
    conf = render_conf(port=port, listen="loopback", cafile=str(d / "ca.crt"), certfile=certs["server"][0],
                       keyfile=certs["server"][1], acl_file=str(d / "acl"))
    (d / "mosquitto.conf").write_text(conf + "persistence false\nlog_dest file %s\n" % (d / "log"))
    proc = subprocess.Popen([MOSQUITTO, "-c", str(d / "mosquitto.conf")])
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield {"port": port, "dir": d, "certs": certs}
    proc.terminate()
    proc.wait(5)


def client(broker, who=None):
    c = paho.Client(paho.CallbackAPIVersion.VERSION2, protocol=paho.MQTTv5)
    certfile, keyfile = broker["certs"][who] if who else (None, None)
    c.tls_set(ca_certs=str(broker["dir"] / "ca.crt"), certfile=certfile, keyfile=keyfile)
    c.tls_insecure_set(False)
    return c


def connected(broker, who):
    c = client(broker, who)
    got = []
    c.on_message = lambda _c, _u, m: got.append(m)
    c.connect("localhost", broker["port"])
    c.loop_start()
    return c, got


def settle(seconds=0.5):
    time.sleep(seconds)


def test_a_client_with_no_certificate_is_refused(broker):
    c = client(broker)
    with pytest.raises(Exception):
        c.connect("localhost", broker["port"])
        c.loop_start()
        settle()
        assert c.is_connected(), "connected without a certificate"
    c.loop_stop()


def test_the_daemon_publishes_and_only_a_granted_reader_receives(broker, tmp_path):
    reader, got = connected(broker, READER)
    stranger, strange = connected(broker, STRANGER)
    for c in (reader, stranger):
        c.subscribe(f"{AGENT}/events/#", qos=1)
    settle()
    log = tmp_path / "events.jsonl"
    log.write_text("")
    daemon, _ = connected(broker, AGENT)
    pub = Publisher(EventStream(AGENT, log), paho_publish(daemon))
    with open(log, "a") as f:
        f.write(json.dumps({"event": "pd_unit_state", "timestamp": 1.0, "data": {"unit": "s"}}) + "\n")
        f.write(json.dumps({"event": "zone_contact", "timestamp": 1.0, "data": {}}) + "\n")
    assert pub.pump() == 2
    settle()
    assert [m.topic for m in got] == [f"{AGENT}/events/pd/unit/state"], "only the granted source"
    assert strange == [], "a certificate the declaration doesn't name reads nothing"
    for c in (reader, stranger, daemon):
        c.loop_stop()
        c.disconnect()


def test_a_reader_cannot_read_or_answer_another_readers_replay(broker):
    second, theirs = connected(broker, SECOND)
    second.subscribe(replay_topics(AGENT, READER)["records"], qos=1)
    reader, mine = connected(broker, READER)
    reader.subscribe(replay_topics(AGENT, READER)["records"], qos=1)
    settle()
    daemon, _ = connected(broker, AGENT)
    daemon.publish(replay_topics(AGENT, READER)["records"], b'{"type":"done"}', qos=1).wait_for_publish(5)
    second.publish(replay_topics(AGENT, READER)["records"], b'{"type":"forged"}', qos=1)
    settle()
    assert [json.loads(m.payload)["type"] for m in mine] == ["done"], "nothing forged, nothing lost"
    assert theirs == [], "another reader's replay is not readable"
    for c in (second, reader, daemon):
        c.loop_stop()
        c.disconnect()
