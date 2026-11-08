"""A daemon's own broker: what its configuration and access rules allow, and the publisher that
puts its stream there (prototype, phase B2)."""
import json

import pytest

from macf.pd.broker import (BrokerRefused, GapTracker, cert_name, grant_filters, render_acl,
                             render_conf, source_topic)

SYS = "SystemDaemon_0a1b2c"
AGENT = "ExampleAgent_1a2b3c"
OTHER = "OtherAgent_4d5e6f"


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
    acl = render_acl(SYS, association=True, members=[AGENT, OTHER])
    assert "pattern" not in acl
    assert set(_users(acl)) == {cert_name(SYS), cert_name(AGENT), cert_name(OTHER)}


def test_a_member_writes_only_its_own_subtree_and_reads_nothing():
    users = _users(render_acl(SYS, association=True, members=[AGENT, OTHER]))
    assert users[cert_name(AGENT)] == [f"topic write members/{AGENT}/#"]
    assert users[cert_name(SYS)] == [f"topic readwrite {SYS}/#", "topic read members/#"]


def test_a_reader_reads_only_the_sources_granted():
    users = _users(render_acl(AGENT, readers={OTHER: ["pd_unit_state", "pd_unit_state"]}))
    assert users[cert_name(OTHER)] == [f"topic read {AGENT}/events/pd/unit/state"]
    with pytest.raises(BrokerRefused, match="not a source name"):
        render_acl(AGENT, readers={OTHER: ["#"]})


def test_a_glob_on_a_family_is_one_filter_and_any_other_is_expanded():
    known = ["pd_entry_due", "pd_entry_fired", "pd_unit_state", "zone_contact"]
    assert grant_filters(AGENT, "pd_entry_*", known) == [f"{AGENT}/events/pd/entry/#"]
    assert grant_filters(AGENT, "*_state", known) == [f"{AGENT}/events/pd/unit/state"]
    assert source_topic(AGENT, "zone_contact") == f"{AGENT}/events/zone/contact"


def test_a_gap_is_judged_per_source_not_by_global_position():
    g = GapTracker()
    assert not g.observe("pd_unit_state", "L:10", None)
    assert not g.observe("pd_unit_state", "L:25", "L:10")     # other sources at 11..24 are not a gap
    assert g.observe("pd_unit_state", "L:40", "L:31")         # a record of this source at 31 was missed


def test_only_an_association_admits_members_or_listens_on_the_lan():
    with pytest.raises(BrokerRefused, match="only an association admits members"):
        render_acl(AGENT, members=[OTHER])
    common = dict(port=18830, cafile="/ca.crt", certfile="/b.crt", keyfile="/b.key", acl_file="/acl")
    with pytest.raises(BrokerRefused, match="only an association listens on the LAN"):
        render_conf(listen="lan", lan_address="192.0.2.10", **common)
    assert "listener 18830 192.0.2.10" in render_conf(listen="lan", lan_address="192.0.2.10",
                                                      association=True, **common)


def test_the_broker_requires_a_certificate_and_names_users_by_it():
    conf = render_conf(port=18830, listen="loopback", cafile="/ca.crt", certfile="/b.crt",
                       keyfile="/b.key", acl_file="/acl")
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
    assert m.topic == f"{AGENT}/events/pd/unit/state"
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
