"""Associations: members export summaries, never content; the association compares members
declared with members present (prototype, phase B3)."""
import json

from macf.pd.association import (MembershipView, export_message, presence_topic, summarize)

M1, M2 = "MemberOne_1a2b3c", "MemberTwo_4d5e6f"


def record(source, **data):
    return {"type": "record", "position": {"log": "L", "offset": 9}, "source": source, "agent": M1,
            "time": 1.0, "origin": "daemon", "record": {"event": source, "data": data}}


def test_an_export_carries_no_content_even_when_the_record_does():
    """B3's planted-content check: a unit state whose record also holds notice text and mail
    exports its unit and state, and nothing else."""
    r = record("pd_unit_state", unit="session", state="failed", notice="the operator's private note",
               mail="secret body", argv=["--token", "x"])
    out = summarize(r)
    assert out == {"source": "pd_unit_state", "agent": M1, "time": 1.0,
                   "position": {"log": "L", "offset": 9}, "data": {"unit": "session", "state": "failed"}}
    blob = json.dumps(out)
    for leaked in ("private note", "secret body", "--token"):
        assert leaked not in blob


def test_only_declared_sources_are_exported_on_the_members_own_subtree():
    assert export_message(M1, record("zone_contact", address="example"), ["pd_unit_*"]) is None
    m = export_message(M1, record("pd_unit_state", unit="s", state="running"), ["pd_unit_*"])
    assert m.topic == f"members/{M1.lower()}/events/pd/unit/state"


def test_the_association_reports_each_difference_between_declared_and_present():
    v = MembershipView(expected=[M1, M2], silent_after_s=60)
    v.observe(presence_topic(M1), b"online", now=0)
    v.observe(f"members/{M1.lower()}/events/pd/unit/state", b"{}", now=0)
    v.observe(presence_topic("Stray_000000"), b"online", now=0)
    assert v.findings(now=10) == [f"{M2}: declared, never present", "stray_000000: present but not declared"]
    assert f"{M1}: present but silent for 100 s" in v.findings(now=100)
    v.observe(presence_topic(M1), b"offline", now=101)
    assert f"{M1}: offline" in v.findings(now=101)


def test_a_member_declared_in_another_case_is_the_same_member():
    """R164: two spellings of a card are one card. The member publishes under its own spelling,
    the association declares another, and the broker's rule and the view still agree."""
    from macf.pd.broker import render_access_rules
    declared = M1.split("_")[0].upper() + "_" + M1.split("_")[1]
    v = MembershipView(expected=[declared])
    v.observe(presence_topic(M1), b"online", now=0)
    assert v.findings(now=1) == []
    rule = f"topic write {presence_topic(M1).rsplit('/', 1)[0]}/#"
    assert rule in render_access_rules("SystemDaemon_0a1b2c", association=True, members=[declared])


def test_only_a_system_or_fleet_daemon_with_a_broker_admits_members():
    import pytest
    from pydantic import ValidationError
    from macf.pd.interface import Declaration
    broker = {"port": 18830, "certificate_authority_file": "a", "server_certificate_file": "b", "server_key_file": "c",
              "client_certificate_file": "d", "client_key_file": "e"}
    with pytest.raises(ValidationError, match="admits no members"):
        Declaration.model_validate({"version": 1, "agent": M1, "members": [M2], "broker": broker})
    with pytest.raises(ValidationError, match="declare broker"):
        Declaration.model_validate({"version": 1, "agent": M1, "kind": "system", "members": [M2]})
    d = Declaration.model_validate({"version": 1, "agent": M1, "kind": "system", "members": [M2], "broker": broker,
                                    "association": {"port": 18831, "certificate_authority_file": "a", "client_certificate_file": "d",
                                                    "client_key_file": "e"}})
    assert d.association.exports == ["pd_unit_state", "pd_carried"]


def test_a_system_daemons_member_findings_chain_up_as_a_summary():
    """B4: what a system daemon exports to its fleet is its members' summary, the same Exporter."""
    r = record("pd_member_findings", findings=[f"{M2}: offline"], members=[M1, M2], secret="x")
    out = summarize(r)
    assert out["data"] == {"findings": [f"{M2}: offline"]}
    assert "secret" not in json.dumps(out)


def test_links_start_at_the_end_of_a_log_that_has_history(tmp_path):
    """A member with months of log exported every old unit state at its first connect and
    flooded its association (seen live, Nov 8); its own publisher read the whole log in one
    pass. Both now follow from the log's end: only what is appended after start goes out."""
    from macf.pd.broker_link import BrokerLink, ExportLink
    from macf.pd.interface import AssociationLink, BrokerSection

    class Client:
        def __init__(self):
            self.sent = []

        def publish(self, topic, payload, qos=0, properties=None, retain=False):
            self.sent.append(topic)
            return type("Info", (), {"rc": 0})()

    log = tmp_path / "events.jsonl"
    with open(log, "w") as f:
        for n in range(50):
            f.write(json.dumps({"event": "pd_unit_state", "timestamp": 1.0, "data": {"unit": f"old{n}"}}) + "\n")
    section = BrokerSection(port=18830, certificate_authority_file="a", server_certificate_file="b",
                            server_key_file="c", client_certificate_file="d", client_key_file="e")
    link = AssociationLink(port=18831, certificate_authority_file="a", client_certificate_file="d",
                           client_key_file="e")
    own, up = Client(), Client()
    broker = BrokerLink(M1, log, section, {}, client=own)
    export = ExportLink(M1, log, link, {}, client=up)
    broker.tick()
    export.tick()
    assert own.sent == [] and up.sent == [], "nothing old goes out"
    with open(log, "a") as f:
        f.write(json.dumps({"event": "pd_unit_state", "timestamp": 2.0, "data": {"unit": "new"}}) + "\n")
    broker.tick()
    export.tick()
    assert len(own.sent) == 1 and len(up.sent) == 1, "what is appended after start does"


def test_a_link_starts_with_each_units_current_state(tmp_path):
    """MIS-0002 R182: a link starts at the log's end, so after a restart the association would
    keep the member's unit states from before it until something changed. At each connect the
    link sends one summary of every unit's current state, then follows the log; a declaration that
    doesn't export unit states sends none."""
    from macf.pd.broker_link import ExportLink
    from macf.pd.interface import AssociationLink

    class Client:
        def __init__(self):
            self.sent = []

        def publish(self, topic, payload, qos=0, properties=None, retain=False):
            self.sent.append((topic, json.loads(payload) if payload not in (b"online", b"offline") else payload))
            return type("Info", (), {"rc": 0})()

    log = tmp_path / "events.jsonl"
    log.write_text("")
    link = AssociationLink(port=18831, certificate_authority_file="a", client_certificate_file="d",
                           client_key_file="e")
    up = Client()
    states = [("broker", "running"), ("worker", "failed")]
    export = ExportLink(M1, log, link, {}, client=up, snapshot=lambda: list(states))
    export.tick()
    assert up.sent == [], "nothing before the link connects"
    export._on_connect(up, None, None, None)
    export.tick()
    sent = [body for topic, body in up.sent if topic.endswith("/events/pd/unit/state")]
    assert [(b["data"]["unit"], b["data"]["state"], b["snapshot"]) for b in sent] == [
        ("broker", "running", True), ("worker", "failed", True)]
    assert all(b["agent"] == M1 and set(b) == {"source", "agent", "time", "snapshot", "data"} for b in sent)
    export.tick()
    assert len([1 for topic, _ in up.sent if topic.endswith("/events/pd/unit/state")]) == 2, "once per connect"
    states[1] = ("worker", "running")
    export._on_connect(up, None, None, None)             # a reconnect sends the current states again
    export.tick()
    assert [b["data"]["state"] for t, b in up.sent if t.endswith("/events/pd/unit/state")][-2:] == ["running", "running"]

    quiet = Client()
    no_units = ExportLink(M1, log, link.model_copy(update={"exports": ["pd_carried"]}), {}, client=quiet,
                          snapshot=lambda: list(states))
    no_units._on_connect(quiet, None, None, None)
    no_units.tick()
    assert [t for t, _ in quiet.sent if "/events/" in t] == []
