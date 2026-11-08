"""An association's broker, live: members admitted by certificate, each writing only its own
subtree, none reading a sibling's, and a member that dies marked offline by its will (prototype,
phase B3). Skipped where mosquitto, paho-mqtt or openssl is absent."""
import json
import subprocess
import sys
import time

import pytest

paho = pytest.importorskip("paho.mqtt.client")

from macf.pd.association import MembershipView, presence_topic  # noqa: E402
from macf.pd.broker import cert_name, render_acl, render_conf  # noqa: E402

sys.path.insert(0, __import__("os").path.dirname(__file__))
from test_pd_broker_live import MOSQUITTO, free_port, issue, openssl, settle  # noqa: E402

import shutil  # noqa: E402

pytestmark = pytest.mark.skipif(not MOSQUITTO or not shutil.which("openssl"),
                                reason="mosquitto and openssl are needed for the live broker")

SYS, M1, M2 = "SystemDaemon_0a1b2c", "MemberOne_1a2b3c", "MemberTwo_4d5e6f"


@pytest.fixture(scope="module")
def assoc(tmp_path_factory):
    d = tmp_path_factory.mktemp("assoc")
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.crt",
            "-days", "1", "-subj", "/CN=scratch-ca", cwd=d)
    certs = {n: issue(d, cert_name(n)) for n in (SYS, M1, M2)}
    certs["server"] = issue(d, "localhost")
    (d / "acl").write_text(render_acl(SYS, association=True, members=[M1, M2]))
    port = free_port()
    conf = render_conf(port=port, listen="loopback", cafile=str(d / "ca.crt"), certfile=certs["server"][0],
                       keyfile=certs["server"][1], acl_file=str(d / "acl"), association=True)
    (d / "mosquitto.conf").write_text(conf + "persistence false\n")
    proc = subprocess.Popen([MOSQUITTO, "-c", str(d / "mosquitto.conf")], stderr=subprocess.DEVNULL)
    import socket
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield {"port": port, "dir": d, "certs": certs}
    proc.terminate()
    proc.wait(5)


def client(a, who, will=None):
    c = paho.Client(paho.CallbackAPIVersion.VERSION2, protocol=paho.MQTTv5)
    c.tls_set(ca_certs=str(a["dir"] / "ca.crt"), certfile=a["certs"][who][0], keyfile=a["certs"][who][1])
    if will:
        c.will_set(*will, qos=1, retain=True)
    got = []
    c.on_message = lambda _c, _u, m: got.append(m)
    c.connect("localhost", a["port"])
    c.loop_start()
    return c, got


def test_a_member_writes_only_its_own_subtree_and_reads_no_sibling(assoc):
    sysd, seen = client(assoc, SYS)
    sysd.subscribe("members/#", qos=1)
    m2, m2_got = client(assoc, M2)
    m2.subscribe(f"members/{M1}/#", qos=1)       # a sibling's subtree: refused by the rules
    settle()
    m1, _ = client(assoc, M1)
    m1.publish(f"members/{M1}/events/pd/unit/state", b'{"ok":1}', qos=1).wait_for_publish(5)
    m1.publish(f"members/{M2}/presence", b"offline", qos=1, retain=True)   # forging a sibling
    settle()
    topics = [m.topic for m in seen]
    assert topics == [f"members/{M1}/events/pd/unit/state"], "only its own subtree arrives"
    assert m2_got == [], "a member reads no sibling"
    for c in (sysd, m2, m1):
        c.loop_stop()
        c.disconnect()


MEMBER = """
import sys, time, paho.mqtt.client as m
c = m.Client(m.CallbackAPIVersion.VERSION2, protocol=m.MQTTv5)
c.tls_set(ca_certs=sys.argv[1], certfile=sys.argv[2], keyfile=sys.argv[3])
c.will_set(sys.argv[5], b"offline", qos=1, retain=True)
c.connect("localhost", int(sys.argv[4]), keepalive=5)
c.loop_start()
c.publish(sys.argv[5], b"online", qos=1, retain=True).wait_for_publish(5)
time.sleep(60)
"""


def test_a_member_that_dies_is_marked_offline_by_its_will_and_reported(assoc, tmp_path):
    script = tmp_path / "member.py"
    script.write_text(MEMBER)
    view = MembershipView(expected=[M1])
    sysd, seen = client(assoc, SYS)
    sysd.subscribe("members/#", qos=1)
    settle()
    proc = subprocess.Popen([sys.executable, str(script), str(assoc["dir"] / "ca.crt"),
                             assoc["certs"][M1][0], assoc["certs"][M1][1], str(assoc["port"]),
                             presence_topic(M1)])
    for _ in range(50):
        if any(m.payload == b"online" for m in seen):
            break
        time.sleep(0.1)
    for m in list(seen):
        view.observe(m.topic, m.payload, now=time.time())
    assert view.findings(now=time.time()) == []
    proc.terminate()                              # dies without a DISCONNECT
    proc.wait(5)
    for _ in range(100):
        if seen and seen[-1].payload == b"offline":
            break
        time.sleep(0.1)
    for m in list(seen):
        view.observe(m.topic, m.payload, now=time.time())
    assert view.findings(now=time.time()) == [f"{M1}: offline"]
    sysd.loop_stop()
    sysd.disconnect()
