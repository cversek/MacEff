"""A daemon's own broker: what its configuration and access rules allow (prototype, phase B2)."""
import pytest

from macf.pd.broker import BrokerRefused, cert_name, render_acl, render_conf

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
    assert users[cert_name(OTHER)] == [f"topic read {AGENT}/events/pd_unit_state"]
    with pytest.raises(BrokerRefused, match="one event name"):
        render_acl(AGENT, readers={OTHER: ["#"]})


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
