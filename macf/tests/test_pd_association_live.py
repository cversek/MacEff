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
from macf.pd.broker import cert_name, render_access_rules, render_conf  # noqa: E402

sys.path.insert(0, __import__("os").path.dirname(__file__))
from test_pd_broker_live import MOSQUITTO, free_port, issue, openssl, settle  # noqa: E402

import shutil  # noqa: E402

pytestmark = pytest.mark.skipif(not MOSQUITTO or not shutil.which("openssl"),
                                reason="mosquitto and openssl are needed for the live broker")

SYS, M1, M2 = "SystemDaemon_0a1b2c", "MemberOne_1a2b3c", "MemberTwo_4d5e6f"
FLEET, SYS2 = "HarborFleet_9e8d7c", "SystemTwo_5b4a3c"
#: The recursion (B4): the same association, one level up. A system daemon is a member of its
#: fleet exactly as an agent's daemon is a member of its system.
LEVELS = {"system": (SYS, M1, M2), "fleet": (FLEET, SYS, SYS2)}


@pytest.fixture(scope="module")
def assoc(tmp_path_factory):
    return make_broker(tmp_path_factory, SYS, [M1, M2])


@pytest.fixture(scope="module", params=sorted(LEVELS))
def level(request, tmp_path_factory):
    head, a, b = LEVELS[request.param]
    yield (make_broker(tmp_path_factory, head, [a, b]), head, a, b)


def make_broker(tmp_path_factory, head, members):
    d = tmp_path_factory.mktemp("assoc")
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.crt",
            "-days", "1", "-subj", "/CN=scratch-ca", cwd=d)
    certs = {n: issue(d, cert_name(n)) for n in [head] + list(members)}
    certs["server"] = issue(d, "localhost")
    (d / "access_rules").write_text(render_access_rules(head, association=True, members=list(members)))
    port = free_port()
    conf = render_conf(port=port, listen="loopback", certificate_authority_file=str(d / "ca.crt"), certificate_file=certs["server"][0],
                       key_file=certs["server"][1], access_rules_file=str(d / "access_rules"), association=True)
    (d / "mosquitto.conf").write_text(conf + "persistence false\n")
    proc = subprocess.Popen([MOSQUITTO, "-c", str(d / "mosquitto.conf")], stderr=subprocess.DEVNULL)
    import socket
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    import atexit
    atexit.register(lambda: (proc.terminate(), proc.wait(5)))
    return {"port": port, "dir": d, "certs": certs}


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


def test_the_daemons_links_export_and_report_membership_from_their_own_loops(level, tmp_path):
    """What the daemons run: a member's ExportLink and the association's BrokerLink, each driven
    by tick() alone. The association records each change in what differs from its declaration."""
    from macf.pd.broker_link import BrokerLink, ExportLink
    from macf.pd.interface import AssociationLink, BrokerSection
    assoc, SYS, M1, M2 = level                      # the same test at each level (B4)

    def unconnected(who, will=None):
        c = paho.Client(paho.CallbackAPIVersion.VERSION2, protocol=paho.MQTTv5)
        c.tls_set(ca_certs=str(assoc["dir"] / "ca.crt"), certfile=assoc["certs"][who][0],
                  keyfile=assoc["certs"][who][1])
        if will:
            c.will_set(will, b"offline", qos=1, retain=True)
        return c
    findings = []
    section = BrokerSection(port=assoc["port"], certificate_authority_file="x", server_certificate_file="x", server_key_file="x",
                            client_certificate_file="x", client_key_file="x")
    sys_log = tmp_path / "sys.jsonl"
    sys_log.write_text("")
    sysd = BrokerLink(SYS, sys_log, section, {}, client=unconnected(SYS), members=[M1, M2],
                      on_findings=findings.append)
    m_log = tmp_path / "m1.jsonl"
    m_log.write_text("")
    link = AssociationLink(port=assoc["port"], certificate_authority_file="x", client_certificate_file="x", client_key_file="x")
    member = ExportLink(M1, m_log, link, {}, client=unconnected(M1, will=presence_topic(M1)))
    sysd.start()
    settle()
    member.start()

    def run(seconds):
        for _ in range(int(seconds / 0.1)):
            sysd.tick()
            member.tick()
            time.sleep(0.1)
    run(1.5)
    with open(m_log, "a") as f:
        f.write(json.dumps({"event": "pd_unit_state", "timestamp": 1.0,
                            "data": {"unit": "session", "state": "running", "notice": "private"}}) + "\n")
    run(1.5)
    # Before M1 connects it is absent, or offline by the retained presence an earlier member left:
    # retained presence is how an association learns what happened before it connected.
    assert findings[0][0] in (f"{M1}: declared, never present", f"{M1}: offline")
    assert findings[0][1:] == [f"{M2}: declared, never present"]
    assert findings[-1] == [f"{M2}: declared, never present"], "M1 is present and exporting"
    assert sysd.view.members[M1].last_export is not None
    member.stop()                                  # a clean stop says offline itself
    run(1.5)
    assert findings[-1] == [f"{M1}: offline", f"{M2}: declared, never present"]
    sysd.stop()
