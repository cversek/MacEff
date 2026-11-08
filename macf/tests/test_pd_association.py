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
    assert m.topic == f"members/{M1}/events/pd/unit/state"


def test_the_association_reports_each_difference_between_declared_and_present():
    v = MembershipView(expected=[M1, M2], silent_after_s=60)
    v.observe(presence_topic(M1), b"online", now=0)
    v.observe(f"members/{M1}/events/pd/unit/state", b"{}", now=0)
    v.observe(presence_topic("Stray_000000"), b"online", now=0)
    assert v.findings(now=10) == [f"{M2}: declared, never present", "Stray_000000: present but not declared"]
    assert f"{M1}: present but silent for 100 s" in v.findings(now=100)
    v.observe(presence_topic(M1), b"offline", now=101)
    assert f"{M1}: offline" in v.findings(now=101)


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
