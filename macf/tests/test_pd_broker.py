"""A daemon's own broker: what its configuration and access rules allow, and the publisher that
puts its stream there (prototype, phase B2)."""
import json

import pytest

from macf.pd.broker import (BrokerRefused, GapTracker, cert_name, grant_filters, render_access_rules,
                             render_conf, source_topic)
from test_primal_daemon import base  # noqa: F401 - a fixture: the short runtime dir daemon tests share

SYS = "SystemDaemon_0a1b2c"
AGENT = "ExampleAgent_1a2b3c"
OTHER = "OtherAgent_4d5e6f"
READER = "ReaderAgent_7a8b9c"


def _users(acl):
    """{user: [topic lines]} from a rendered ACL."""
    out, user = {}, None
    for line in acl.splitlines():
        if line.startswith("user "):
            user = line.split()[1]
            out[user] = []
        elif line.startswith("topic "):
            out[user].append(line)
    return out


def test_only_named_certificates_get_rules_and_never_by_pattern():
    acl = render_access_rules(SYS, association=True, members=[AGENT, OTHER])
    assert "pattern" not in acl
    assert set(_users(acl)) == {cert_name(SYS), cert_name(AGENT), cert_name(OTHER)}


def test_a_member_writes_only_its_own_subtree_and_reads_nothing():
    users = _users(render_access_rules(SYS, association=True, members=[AGENT, OTHER]))
    assert users[cert_name(AGENT)] == [f"topic write members/{AGENT.lower()}/#"]
    assert users[cert_name(SYS)] == [f"topic readwrite {SYS.lower()}/#", "topic read members/#"]


def test_a_reader_reads_only_the_sources_granted():
    users = _users(render_access_rules(AGENT, readers={OTHER: ["pd_unit_state", "pd_unit_state"]}))
    assert users[cert_name(OTHER)] == [f"topic read {AGENT.lower()}/events/pd/unit/state",
                                       f"topic read {AGENT.lower()}/routed/{OTHER.lower()}/pd/unit/state",
                                       f"topic write {AGENT.lower()}/replay/{OTHER.lower()}/request",
                                       f"topic read {AGENT.lower()}/replay/{OTHER.lower()}/records"]
    with pytest.raises(BrokerRefused, match="not a source name"):
        render_access_rules(AGENT, readers={OTHER: ["#"]})


def test_a_glob_on_a_family_is_one_filter_and_any_other_is_expanded():
    known = ["pd_entry_due", "pd_entry_fired", "pd_unit_state", "zone_contact"]
    assert grant_filters(AGENT, "pd_entry_*", known) == [f"{AGENT.lower()}/events/pd/entry/#"]
    assert grant_filters(AGENT, "*_state", known) == [f"{AGENT.lower()}/events/pd/unit/state"]
    assert source_topic(AGENT, "zone_contact") == f"{AGENT.lower()}/events/zone/contact"


def test_a_gap_is_judged_per_source_not_by_global_position():
    g = GapTracker()
    assert not g.observe("pd_unit_state", "L:10", None)
    assert not g.observe("pd_unit_state", "L:25", "L:10")     # other sources at 11..24 are not a gap
    assert g.observe("pd_unit_state", "L:40", "L:31")         # a record of this source at 31 was missed


def test_only_an_association_admits_members_or_listens_on_the_lan():
    with pytest.raises(BrokerRefused, match="only an association admits members"):
        render_access_rules(AGENT, members=[OTHER])
    common = dict(port=18830, certificate_authority_file="/ca.crt", certificate_file="/b.crt", key_file="/b.key", access_rules_file="/acl")
    with pytest.raises(BrokerRefused, match="only an association listens on the LAN"):
        render_conf(listen="lan", lan_address="192.0.2.10", **common)
    assert "listener 18830 192.0.2.10" in render_conf(listen="lan", lan_address="192.0.2.10",
                                                      association=True, **common)


def test_the_broker_requires_a_certificate_and_names_users_by_it():
    conf = render_conf(port=18830, listen="loopback", certificate_authority_file="/ca.crt", certificate_file="/b.crt",
                       key_file="/b.key", access_rules_file="/acl")
    for line in ("allow_anonymous false", "listener 18830 127.0.0.1", "require_certificate true",
                 "use_identity_as_username true", "acl_file /acl"):
        assert line in conf.splitlines()


def test_a_certificate_is_named_by_the_card_lowercased_and_a_non_card_is_refused():
    assert cert_name(AGENT) == "exampleagent_1a2b3c"
    with pytest.raises(ValueError):
        cert_name("maceff_system")


def test_a_record_publishes_on_its_source_topic_with_its_previous():
    from macf.pd.broker import to_message
    rec = {"type": "record", "position": {"log": "L", "offset": 42}, "source": "pd_unit_state",
           "agent": AGENT, "time": 1.0, "origin": "log", "record": {"event": "pd_unit_state"}}
    m = to_message(AGENT, rec, "L:17")
    assert m.topic == f"{AGENT.lower()}/events/pd/unit/state"
    assert m.properties == {"previous": "L:17"}
    assert json.loads(m.payload) == rec
    assert to_message(AGENT, rec, None).properties == {}


# --- the publisher, on a real log -----------------------------------------------------------


class Client:
    """Stands in for the MQTT client: records each message, or raises while ``down``."""

    def __init__(self):
        self.sent, self.down = [], False

    def __call__(self, message):
        if self.down:
            raise ConnectionError("broker unreachable")
        self.sent.append(message)


def append(log, event, **data):
    with open(log, "a") as f:
        f.write(json.dumps({"event": event, "timestamp": 1.0, "data": data}) + "\n")


def publisher(log, client, **kw):
    from macf.pd.broker import Publisher
    from macf.pd.stream import EventStream
    return Publisher(EventStream(AGENT, log), client, wall=lambda: 9.0, **kw)


def records(client):
    return [(m.topic.split("/events/")[1], json.loads(m.payload), m.properties.get("previous"))
            for m in client.sent]


def test_each_new_record_publishes_in_order_naming_its_own_sources_previous(tmp_path):
    log, client = tmp_path / "events.jsonl", Client()
    log.write_text("")
    pub = publisher(log, client)
    append(log, "pd_unit_state", unit="a")
    append(log, "zone_contact", n=1)
    append(log, "pd_unit_state", unit="b")
    assert pub.pump() == 3
    (t1, r1, p1), (t2, r2, p2), (t3, r3, p3) = records(client)
    assert (t1, t2, t3) == ("pd/unit/state", "zone/contact", "pd/unit/state")
    assert r3["record"]["data"] == {"unit": "b"} and r3["agent"] == AGENT
    assert (p1, p2) == (None, None)
    assert p3 == f"{r1['position']['log']}:{r1['position']['offset']}"
    assert pub.pump() == 0


def test_a_daemon_restart_is_not_a_gap_and_records_written_while_it_was_down_are(tmp_path):
    from macf.pd.broker import GapTracker, position_key
    log = tmp_path / "events.jsonl"
    log.write_text("")
    first = Client()
    pub = publisher(log, first)
    append(log, "pd_unit_state", unit="a")
    pub.pump()
    seen = GapTracker()
    (_, rec, prev), = records(first)
    seen.observe("pd_unit_state", position_key(rec["position"]), prev)

    again = Client()
    pub = publisher(log, again)               # the daemon restarts: the log is unchanged
    append(log, "pd_unit_state", unit="b")
    pub.pump()
    (_, rec, prev), = records(again)
    assert not seen.observe("pd_unit_state", position_key(rec["position"]), prev)

    append(log, "pd_unit_state", unit="c")    # written while the daemon is down
    later = Client()
    pub = publisher(log, later)
    append(log, "pd_unit_state", unit="d")
    pub.pump()
    (_, rec, prev), = records(later)
    assert seen.observe("pd_unit_state", position_key(rec["position"]), prev)


def test_the_seed_names_each_sources_last_record_and_skips_a_cut_first_line(tmp_path):
    from macf.pd.broker import seed_previous
    log = tmp_path / "events.jsonl"
    for event in ("zone_contact", "pd_unit_state", "zone_contact"):
        append(log, event)
    data = log.read_bytes()
    ends = [i + 1 for i, b in enumerate(data) if b == ord("\n")]
    assert seed_previous(log, "L", len(data), 1 << 20) == {"pd_unit_state": f"L:{ends[1]}",
                                                           "zone_contact": f"L:{ends[2]}"}
    # Read back from the middle of the first line: it is no record, and the rest still counts.
    assert seed_previous(log, "L", len(data), len(data) - 5) == {"pd_unit_state": f"L:{ends[1]}",
                                                                 "zone_contact": f"L:{ends[2]}"}
    assert seed_previous(log, "L", len(data), len(data) - ends[0] - 3) == {"zone_contact": f"L:{ends[2]}"}


def test_a_publish_that_fails_keeps_its_record_and_the_order(tmp_path):
    log, client = tmp_path / "events.jsonl", Client()
    log.write_text("")
    pub = publisher(log, client)
    append(log, "pd_unit_state", unit="a")
    client.down = True
    with pytest.raises(ConnectionError):
        pub.pump()
    append(log, "pd_unit_state", unit="b")
    client.down = False
    assert pub.pump() == 2
    assert [r["record"]["data"]["unit"] for _, r, _ in records(client)] == ["a", "b"]
    (_, r1, _), (_, _, p2) = records(client)
    assert p2 == f"{r1['position']['log']}:{r1['position']['offset']}"


def test_a_backlog_past_its_bound_becomes_one_gap(tmp_path, monkeypatch):
    from macf.pd import broker
    monkeypatch.setattr(broker, "PENDING_MAX", 3)
    log, client = tmp_path / "events.jsonl", Client()
    log.write_text("")
    pub = publisher(log, client)
    client.down = True
    for i in range(5):
        append(log, "pd_unit_state", unit=str(i))
        with pytest.raises(ConnectionError):
            pub.pump()
    client.down = False
    pub.pump()
    (topic, body, _), (after, rec, _) = records(client)    # the 4th record overflowed the bound
    assert topic == "_gap" and body["reason"] == "overflow"
    assert body["from"]["offset"] < body["to"]["offset"] <= rec["position"]["offset"]
    assert after == "pd/unit/state" and rec["record"]["data"]["unit"] == "4"


def test_a_rotated_log_publishes_a_gap(tmp_path):
    log, client = tmp_path / "events.jsonl", Client()
    append(log, "pd_unit_state", unit="a")
    pub = publisher(log, client)
    log.unlink()
    append(log, "zone_contact", n=2)           # a new log, with another first line
    pub.pump()
    topics = [t for t, _, _ in records(client)]
    assert topics == ["_gap", "zone/contact"]
    assert records(client)[0][1]["reason"] == "rotated"


# --- replay from the log ----------------------------------------------------------------------


def stream_over(log):
    from macf.pd.stream import EventStream
    return EventStream(AGENT, log)


def replayed(messages):
    return [json.loads(m.payload) for m in messages]


def test_a_replay_sends_the_granted_records_since_the_position_then_done(tmp_path):
    from macf.pd.broker import replay_messages, replay_topics
    log = tmp_path / "events.jsonl"
    append(log, "pd_unit_state", unit="seen")
    seen_at = {"log": stream_over(log).identity, "offset": log.stat().st_size}
    append(log, "pd_unit_state", unit="missed")
    append(log, "zone_contact", n=1)              # asked for, not granted
    append(log, "pd_entry_due", id="x")           # granted, not asked for
    stream = stream_over(log)
    out = replay_messages(stream, OTHER, {"position": seen_at, "sources": ["pd_unit_*", "zone_*"]},
                          granted=["pd_unit_state", "pd_entry_due"])
    assert {m.topic for m in out} == {replay_topics(AGENT, OTHER)["records"]}
    bodies = replayed(out)
    assert [b["record"]["data"] for b in bodies[:-1]] == [{"unit": "missed"}]
    assert bodies[-1] == {"type": "done", "agent": AGENT, "position": stream.position()}


def test_a_replay_from_a_rotated_log_starts_with_a_gap(tmp_path):
    from macf.pd.broker import replay_messages
    log = tmp_path / "events.jsonl"
    append(log, "pd_unit_state", unit="a")
    out = replayed(replay_messages(stream_over(log), OTHER,
                                   {"position": {"log": "999-0000", "offset": 10}, "sources": ["*"]},
                                   granted=None))
    assert out[0]["type"] == "gap" and out[0]["reason"] == "rotated"
    assert out[1]["record"]["data"] == {"unit": "a"} and out[-1]["type"] == "done"


@pytest.mark.parametrize("request_", [{}, {"position": {"log": "L", "offset": -1}, "sources": ["*"]},
                                      {"position": {"log": "L", "offset": 0}, "sources": []},
                                      {"position": {"log": "L", "offset": True}, "sources": ["*"]},
                                      "not a request"])
def test_a_request_that_cant_be_read_is_refused_not_left_waiting(tmp_path, request_):
    from macf.pd.broker import replay_messages
    log = tmp_path / "events.jsonl"
    append(log, "pd_unit_state")
    (only,) = replayed(replay_messages(stream_over(log), OTHER, request_, granted=None))
    assert only["type"] == "refused"


# --- a reader that reconnects catches up, once each, in order --------------------------------


def rec(offset, log="L"):
    return json.dumps({"type": "record", "position": {"log": log, "offset": offset},
                       "source": "pd_unit_state", "record": {"n": offset}}).encode()


def test_a_reader_that_reconnects_gets_each_record_once_in_log_order():
    from macf.pd.broker import CatchUp
    got = []
    c = CatchUp(lambda r: got.append(r["position"]["offset"]))
    assert c.request(["*"]) is None, "a reader with no history takes the stream from now"
    c.live(rec(10))
    c.live(rec(20))
    req = c.request(["pd_unit_*"])            # it reconnects; 30 and 40 were written meanwhile
    assert req == {"position": {"log": "L", "offset": 20}, "sources": ["pd_unit_*"]}
    c.live(rec(50))                           # a live record overtakes the replay: held
    for off in (20, 30, 40):                  # 20 again: the replay may repeat the boundary
        c.replayed(rec(off))
    assert c.replayed(json.dumps({"type": "done"}).encode())
    c.live(rec(50))                           # and the live stream repeats it once more
    assert got == [10, 20, 30, 40, 50]


def test_the_responder_answers_only_granted_readers_on_their_own_topic(tmp_path):
    from macf.pd.broker import ReplayResponder, replay_topics
    log = tmp_path / "events.jsonl"
    append(log, "pd_unit_state", unit="a")
    stream = stream_over(log)
    sent = []
    r = ReplayResponder(stream, sent.append, grants={READER: ["pd_unit_state"]})
    body = json.dumps({"position": {"log": stream.identity, "offset": 0}, "sources": ["*"]}).encode()
    assert r.handle(replay_topics(AGENT, OTHER)["request"], body) == 0, "no grant, no answer"
    assert r.handle(replay_topics(AGENT, READER)["request"], body) == 2     # the record, then done
    assert {m.topic for m in sent} == {replay_topics(AGENT, READER)["records"]}


def test_a_long_replay_is_answered_in_bounded_passes_and_ends_once(tmp_path):
    from macf.pd.broker import ReplayResponder
    log = tmp_path / "events.jsonl"
    for n in range(40):
        append(log, "pd_unit_state", unit=f"u{n:02d}")
    stream = stream_over(log)
    sent = []
    r = ReplayResponder(stream, sent.append, grants={READER: ["*"]})
    body = json.dumps({"position": {"log": stream.identity, "offset": 0}, "sources": ["*"]}).encode()
    assert r.request(READER, body) == 0
    line = len((log.read_text().splitlines()[0] + "\n").encode())
    passes = 0
    while r.in_flight:
        before = len(sent)
        r.pump(max_bytes=5 * line)
        passes += 1
        assert len(sent) - before <= 6, "a pass reads at most its chunk: five records, and done at the end"
    bodies = replayed(sent)
    assert passes == 8
    assert [b["record"]["data"]["unit"] for b in bodies[:-1]] == [f"u{n:02d}" for n in range(40)]
    assert [b["type"] for b in bodies].count("done") == 1 and bodies[-1]["type"] == "done"


def test_a_readers_newer_request_replaces_its_older_one_and_a_bad_one_is_refused(tmp_path):
    from macf.pd.broker import ReplayResponder
    log = tmp_path / "events.jsonl"
    for n in range(10):
        append(log, "pd_unit_state", unit=f"u{n}")
    stream = stream_over(log)
    sent = []
    r = ReplayResponder(stream, sent.append, grants={READER: ["*"]})
    old = json.dumps({"position": {"log": stream.identity, "offset": 0}, "sources": ["*"]}).encode()
    r.request(READER, old)
    r.pump(max_bytes=1)                             # one record of the old replay goes out
    newer = json.dumps({"position": stream.position(), "sources": ["*"]}).encode()
    r.request(READER, newer)
    assert len(r.in_flight) == 1, "one replay in flight per reader"
    while r.in_flight:
        r.pump()
    assert [b["type"] for b in replayed(sent)] == ["record", "done"], "the newer request is the one answered"
    sent.clear()
    assert r.request(READER, b"not json") == 1
    assert replayed(sent)[0]["type"] == "refused" and not r.in_flight


def test_a_reader_declared_in_another_case_gets_the_same_topics(tmp_path):
    from macf.pd.broker import ReplayResponder, replay_topics, topic_name
    assert replay_topics(AGENT, READER) == replay_topics(AGENT.split("_")[0].upper() + "_1a2b3c", READER.lower())
    assert source_topic(AGENT, "pd_unit_state") == source_topic(AGENT.lower(), "pd_unit_state")
    log = tmp_path / "events.jsonl"
    append(log, "pd_unit_state")
    r = ReplayResponder(stream_over(log), lambda m: None, grants={READER.split("_")[0].upper() + "_7a8b9c": ["*"]})
    assert r.reader_of(f"{topic_name(AGENT)}/replay/{READER.lower()}/request") == READER.lower()


def test_the_daemon_and_its_link_use_one_loopback_address(tmp_path):
    from macf.pd import broker_link
    from macf.pd.broker import LISTEN, LOOPBACK
    from macf.pd.interface import AssociationLink
    assert LISTEN["loopback"] == LOOPBACK == "127.0.0.1"
    assert AssociationLink(port=18831, certificate_authority_file="a", client_certificate_file="b",
                           client_key_file="c").host == LOOPBACK
    dialed = []

    class Client:
        def connect_async(self, host, port):
            dialed.append(host)

        def loop_start(self):
            pass
    log = tmp_path / "events.jsonl"
    log.write_text("")
    section = broker_link.BrokerSection(port=18830, certificate_authority_file="a", server_certificate_file="b",
                                        server_key_file="c", client_certificate_file="d", client_key_file="e")
    broker_link.BrokerLink(AGENT, log, section, {}, client=Client()).start()
    assert dialed == [LOOPBACK]


def test_a_broker_port_another_declaration_names_is_refused_naming_it(tmp_path):
    from macf.pd.broker_link import declared_broker_ports, port_clash
    mine, theirs, quiet = tmp_path / "mine", tmp_path / "theirs", tmp_path / "quiet"
    for home, doc in ((mine, {"agent": AGENT, "broker": {"port": 18830}}),
                      (theirs, {"agent": OTHER, "broker": {"port": 18830}}),
                      (quiet, {"agent": READER})):
        (home / ".maceff" / "pd").mkdir(parents=True)
        (home / ".maceff" / "pd" / "declaration.json").write_text(json.dumps(doc))
    others = declared_broker_ports(mine, homes=[mine, theirs, quiet, tmp_path / "absent"])
    assert [(c, p) for c, _w, p in others] == [(OTHER, 18830)]
    why = port_clash(AGENT, 18830, others)
    assert OTHER in why and "18830" in why and str(theirs) in why
    assert port_clash(AGENT, 18831, others) is None
    assert port_clash(OTHER.lower(), 18830, others) is None, "its own declaration, in another case, is no clash"


def test_macos_local_network_block_is_named_not_read_as_an_outage():
    import errno
    from macf.pd.broker_link import unreachable_reason
    blocked = OSError(errno.EHOSTUNREACH, "No route to host")
    assert "Local Network" in unreachable_reason("192.0.2.1", 18831, blocked, platform="darwin")
    assert "Local Network" not in unreachable_reason("192.0.2.1", 18831, blocked, platform="linux")
    refused = OSError(errno.ECONNREFUSED, "Connection refused")
    assert unreachable_reason("192.0.2.1", 18831, refused, platform="darwin").endswith("Connection refused")


def test_the_export_link_records_each_change_of_reason_once(tmp_path):
    import errno
    from macf.pd.broker_link import ExportLink
    from macf.pd.interface import AssociationLink

    class Client:
        def publish(self, *a, **k):
            raise AssertionError("nothing is exported while unreachable")
    link = AssociationLink(host="192.0.2.1", port=18831, certificate_authority_file="a",
                           client_certificate_file="b", client_key_file="c", exports=["zone_*"])
    seen = []
    log = tmp_path / "events.jsonl"
    log.write_text("")
    e = ExportLink(AGENT, log, link, {}, client=Client(), on_unreachable=seen.append,
                   prober=lambda h, p: OSError(errno.EHOSTUNREACH, "No route to host"))
    e._on_connect_fail(None, None)
    e.tick()
    e.tick()
    e._on_connect_fail(None, None)
    e.tick()
    assert len(seen) == 1 and "192.0.2.1:18831" in seen[0]
    e.reason = None                                # what a later connect does
    e.tick()
    assert seen[-1] is None and len(seen) == 2


def test_a_declaration_names_its_broker_and_the_daemon_renders_it(tmp_path):
    from macf.pd.broker_link import render_files
    from macf.pd.interface import Declaration
    d = Declaration.model_validate({"version": 1, "agent": AGENT, "broker": {
        "port": 18830, "certificate_authority_file": "{agent_home}/ca.crt", "server_certificate_file": "{agent_home}/s.crt",
        "server_key_file": "{agent_home}/s.key", "client_certificate_file": "{agent_home}/c.crt",
        "client_key_file": "{agent_home}/c.key", "readers": {OTHER: ["pd_unit_state"]}}})
    conf = render_files(AGENT, d.broker, tmp_path, {"agent_home": "/h"})
    text = conf.read_text()
    assert "listener 18830 127.0.0.1" in text and "cafile /h/ca.crt" in text
    assert "require_certificate true" in text and "persistence false" in text
    acl = (conf.parent / "access_rules").read_text()
    assert f"user {cert_name(OTHER)}" in acl and "pattern" not in acl
    assert conf.parent.stat().st_mode & 0o777 == 0o700


def test_a_broker_section_with_a_low_port_or_a_bad_source_is_refused():
    from pydantic import ValidationError
    from macf.pd.interface import BrokerSection
    base = dict(certificate_authority_file="a", server_certificate_file="b", server_key_file="c", client_certificate_file="d", client_key_file="e")
    with pytest.raises(ValidationError):
        BrokerSection(port=80, **base)
    with pytest.raises(ValidationError):
        BrokerSection(port=18830, readers={OTHER: ["#"]}, **base)


def test_subscribe_over_the_broker_names_what_it_is_missing(capsys, monkeypatch):
    import argparse
    from macf.pd import cli
    monkeypatch.setattr(cli, "_this_agent", lambda: (None, AGENT))
    args = argparse.Namespace(position=None, broker_port=18830, ca="ca.crt", cert=None, key=None,
                              reader=None, source=None, name=None)
    assert cli.cmd_pd_stream_subscribe(args) == 1
    assert "--cert, --key, --reader" in capsys.readouterr().err


# --- the broker unit's wrapper: liveness only while the broker listens ---------------------------


def test_the_wrapper_finds_the_port_the_daemon_rendered(tmp_path):
    from macf.pd.broker_unit import listener_port
    conf = tmp_path / "mosquitto.conf"
    conf.write_text(render_conf(port=18830, listen="loopback", certificate_authority_file="a", certificate_file="b",
                                key_file="c", access_rules_file="d"))
    assert listener_port(conf) == 18830
    conf.write_text("allow_anonymous false\n")
    with pytest.raises(ValueError, match="no listener"):
        listener_port(conf)


def test_the_wrapper_beats_only_while_the_broker_listens_and_ends_with_its_status():
    import sys
    from macf.pd.broker_unit import run
    ticks = []
    child = [sys.executable, "-c", "import time, sys; time.sleep(0.3); sys.exit(3)"]
    assert run(child, 1, lambda: ticks.append(1), poll_s=0.05, probe=lambda port: True) == 3
    assert ticks, "it listens, so it beats"
    ticks.clear()
    assert run(child, 1, lambda: ticks.append(1), poll_s=0.05, probe=lambda port: False) == 3
    assert ticks == [], "a broker process that doesn't listen earns no liveness"
    probes = []
    run(child, 1, lambda: None, poll_s=0.05, probe_every_s=10, probe=lambda port: probes.append(1) or True)
    assert probes == [1], "one probe per interval, however often the wrapper polls"


def test_a_rendered_broker_configuration_is_private(tmp_path):
    from macf.pd.broker_link import render_files
    from macf.pd.interface import BrokerSection
    s = BrokerSection(port=18830, certificate_authority_file="a", server_certificate_file="b", server_key_file="c",
                      client_certificate_file="d", client_key_file="e")
    conf = render_files(AGENT, s, tmp_path, {})
    assert conf.stat().st_mode & 0o777 == 0o600
    assert (conf.parent / "access_rules").stat().st_mode & 0o777 == 0o600


def test_rendering_into_a_missing_runtime_directory_makes_it_private(tmp_path):
    """The system daemon's first start: its runtime directory didn't exist yet, rendering made
    it with the umask's 0755, and the daemon's own check then refused it (Nov 8)."""
    import os
    from macf.pd.broker_link import render_files
    from macf.pd.interface import BrokerSection
    s = BrokerSection(port=18830, certificate_authority_file="a", server_certificate_file="b", server_key_file="c",
                      client_certificate_file="d", client_key_file="e")
    runtime = tmp_path / "run" / "maceff_pd"
    old = os.umask(0o022)
    try:
        render_files(AGENT, s, runtime, {})
    finally:
        os.umask(old)
    assert runtime.stat().st_mode & 0o777 == 0o700
    assert (runtime / f"{AGENT}.broker").stat().st_mode & 0o777 == 0o700


def test_the_wrapper_passes_a_stop_on_to_the_broker():
    import sys
    import time
    from macf.pd.broker_unit import run
    asked_at = time.monotonic() + 0.2
    child = [sys.executable, "-c", "import time; time.sleep(30)"]
    started = time.monotonic()
    code = run(child, 1, lambda: None, poll_s=0.05, probe=lambda port: True,
               stopping=lambda: time.monotonic() > asked_at)
    assert code != 0 and time.monotonic() - started < 5


# --- the clean break: every daemon's stream is its own broker (MIS-0002 R150, R151, R169) ------


def test_every_daemon_runs_its_own_broker(tmp_path):
    """A declaration that names no broker gets the daemon's own: a section with its own
    authority and certificate, made with no root step, and a broker unit. One that names its
    broker in full keeps it."""
    import subprocess
    from macf.pd.broker_defaults import with_own_broker
    from macf.pd.interface import BrokerSection, Declaration
    bare = Declaration(version=1, agent=AGENT)
    d = with_own_broker(bare, tmp_path, AGENT)
    assert d.broker is not None and [u.name for u in d.units] == ["broker"]
    pki = tmp_path / ".maceff" / "pd" / "broker"
    assert pki.stat().st_mode & 0o777 == 0o700
    for f in ("authority.key", "own.key", "authority.crt", "own.crt"):
        assert (pki / f).stat().st_mode & 0o777 == 0o600, f
    verify = subprocess.run(["openssl", "verify", "-CAfile", str(pki / "authority.crt"), str(pki / "own.crt")],
                            capture_output=True, text=True)
    assert verify.returncode == 0, verify.stdout + verify.stderr
    subject = subprocess.run(["openssl", "x509", "-in", str(pki / "own.crt"), "-noout", "-subject", "-ext",
                              "subjectAltName"], capture_output=True, text=True).stdout
    assert cert_name(AGENT) in subject and "127.0.0.1" in subject
    again = with_own_broker(bare, tmp_path, AGENT)
    assert (pki / "own.crt").read_bytes() == (tmp_path / ".maceff/pd/broker/own.crt").read_bytes()
    assert again.broker.certificate_authority_file == d.broker.certificate_authority_file
    named = BrokerSection(port=18830, certificate_authority_file="a", server_certificate_file="b",
                          server_key_file="c", client_certificate_file="d", client_key_file="e")
    kept = with_own_broker(Declaration(version=1, agent=AGENT, broker=named), tmp_path, AGENT)
    assert kept.broker == named


def test_a_subscriber_receives_only_the_sources_it_subscribed():
    """A subscriber's filters, made from the sources it chose, match those sources' topics and no
    others (R151): the broker delivers only what a subscription's filters match."""
    from paho.mqtt.client import topic_matches_sub
    chosen = ["pd_unit_state", "zone_*"]
    filters = sorted({f for s in chosen for f in grant_filters(AGENT, s, ["zone_contact", "zone_edge_check"])})
    def receives(source):
        return any(topic_matches_sub(f, source_topic(AGENT, source)) for f in filters)
    assert receives("pd_unit_state") and receives("zone_contact") and receives("zone_edge_check")
    assert not receives("pd_entry_due") and not receives("tool_call_completed")


def test_a_silenced_source_is_not_published(tmp_path):
    """MIS-0002 R152 on the broker: the operator's silence acts before publishing."""
    from macf.pd.broker import Publisher
    from macf.pd.stream import EventStream, Rules
    log = tmp_path / "events.jsonl"
    log.write_text("")
    rules = Rules()
    rules.apply("silence", "tool_*")
    from macf.pd.stream import matches
    sent = []
    p = Publisher(EventStream(AGENT, log), sent.append,
                  silenced=lambda s: matches(s, [x for x in rules.silenced if not x.startswith("@")]))
    append(log, "tool_call_completed", tool="Bash")
    append(log, "pd_unit_state", unit="a")
    p.pump()
    assert [m.topic for m in sent] == [source_topic(AGENT, "pd_unit_state")]


def test_a_daemon_whose_interpreter_lacks_the_brokers_dependencies_is_refused_naming_the_fix(tmp_path, base, monkeypatch):
    """An editable install made before paho-mqtt and cryptography were core dependencies doesn't
    gain them when its checkout updates. Such a daemon is refused at start with the command that
    installs them into its own interpreter, rather than dying on an import inside its start."""
    import macf.pd.broker_defaults as bd
    from macf.pd.core import DeclarationRefused
    from macf.pd.daemon import Daemon
    from test_primal_daemon import make_home
    assert bd.missing_dependencies(lambda module: None) == ["paho-mqtt", "cryptography"]
    assert bd.missing_dependencies(lambda module: None if module == "cryptography" else object()) == ["cryptography"]
    assert bd.missing_dependencies() == []
    monkeypatch.setattr(bd, "missing_dependencies", lambda: ["paho-mqtt"])
    with pytest.raises(DeclarationRefused) as refused:
        Daemon(make_home(tmp_path, []), base=base)      # a short runtime dir: macOS caps a socket path at 103 bytes
    import sys
    assert "paho-mqtt" in str(refused.value) and f"{sys.executable} -m pip install" in str(refused.value)


def test_the_wrapper_names_the_remedy_when_mosquitto_is_missing(tmp_path, capsys):
    from macf.pd.broker_unit import main
    conf = tmp_path / "mosquitto.conf"
    conf.write_text("listener 18830 127.0.0.1\n")
    assert main([str(conf), "--mosquitto", "no-such-mosquitto-here"]) == 127
    err = capsys.readouterr().err
    assert "install mosquitto" in err.lower() and "brew services start" in err
