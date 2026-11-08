"""A daemon's own broker: what its configuration and access rules allow (prototype, phase B2)."""
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
    assert not g.observe("pd_unit_state", 10, None)
    assert not g.observe("pd_unit_state", 25, 10)     # other sources at 11..24 are not a gap
    assert g.observe("pd_unit_state", 40, 31)         # a record of this source at 31 was missed


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
