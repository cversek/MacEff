"""Tests for the broker's declarative deployment config.

Known-answer first: a valid config must produce exactly the BrokerConfig a
deployment expects, before any test celebrates a refusal — a validator that
refuses everything passes a refusal-only suite perfectly.
"""
import pytest
from pathlib import Path

from pydantic import ValidationError

from macf.amail.deploy_config import AgentBinding, BrokerDeployConfig

VALID = {
    "domain": "example.test",
    "agents": {"alpha": {"home": "/home/alpha_unix", "uid": 1002}},
    "contacts_path": "/etc/amail/contacts.json",
    "audit_path": "/var/lib/amail_broker/audit.jsonl",
    "inbound_quarantine": "/var/lib/amail_broker/quarantine",
    "inbound_handoff": "/var/lib/amail/handoff",
}


def test_valid_config_produces_the_expected_broker_config():
    cfg = BrokerDeployConfig.model_validate(VALID).to_broker_config()
    assert cfg.domain == "example.test"
    # The agent NAME is the address local-part; the unix account name differs
    # and must not leak into the mapping.
    assert cfg.agent_homes == {"alpha": Path("/home/alpha_unix")}
    assert cfg.agent_uids == {1002: "alpha"}
    assert cfg.inbound_handoff == Path("/var/lib/amail/handoff")
    assert cfg.credentials_path is None  # outbound leg absent, honestly


def test_socket_path_defaults_without_being_named():
    cfg = BrokerDeployConfig.model_validate(VALID).to_broker_config()
    assert cfg.socket_path == Path("/run/amail/broker.sock")


def test_unknown_key_refuses_to_parse():
    # An ignored misspelling would silently change what the broker enforces.
    bad = dict(VALID, credentails_path="/etc/amail/cred")
    with pytest.raises(ValidationError, match="credentails_path"):
        BrokerDeployConfig.model_validate(bad)


def test_unknown_key_inside_an_agent_binding_refuses_too():
    bad = dict(VALID, agents={"alpha": {"home": "/h", "uid": 1, "iud": 2}})
    with pytest.raises(ValidationError, match="iud"):
        BrokerDeployConfig.model_validate(bad)


def test_empty_agent_table_refuses():
    with pytest.raises(ValidationError, match="empty table"):
        BrokerDeployConfig.model_validate(dict(VALID, agents={}))


def test_duplicate_uid_refuses():
    # One uid cannot be two identities: the kernel would authenticate a
    # submitter as whichever name won the dict race.
    two = {"alpha": {"home": "/a", "uid": 1002},
           "beta": {"home": "/b", "uid": 1002}}
    with pytest.raises(ValidationError, match="share uid"):
        BrokerDeployConfig.model_validate(dict(VALID, agents=two))


def test_non_integer_uid_refuses():
    with pytest.raises(ValidationError):
        BrokerDeployConfig.model_validate(
            dict(VALID, agents={"alpha": {"home": "/a", "uid": "1002x"}}))


# --------------------------------------------------------------- the transport
#
# These exist because the transport class was complete, unit-tested and
# unreachable for an entire phase: nothing in the on-disk contract could name
# an endpoint, so every deployment ran with no transport regardless of what its
# credential said. The credential check passed, the broker started, and the
# outbound leg did not exist.


def test_declared_endpoint_produces_a_transport_that_carries_it():
    """spec O5b.5b "broker-to-transport-hop" — the KNOWN-ANSWER GREEN.

    Asserts the endpoint SURVIVES the translation rather than that a transport
    merely exists: a builder returning a transport pointed somewhere else would
    pass an is-not-None check and submit our mail to the wrong host.
    """
    cfg = BrokerDeployConfig.model_validate(
        dict(VALID, transport_endpoint="https://submit.example.test/submit",
             transport_timeout=7.5)).to_broker_config()
    assert cfg.transport is not None
    assert cfg.transport.endpoint == "https://submit.example.test/submit"
    assert cfg.transport.timeout == 7.5


def test_absent_endpoint_yields_no_transport_rather_than_a_silent_one():
    """The paired negative. A deployment with no endpoint must REFUSE to send.

    None is the value the broker's rung-3 path already refuses on, naming the
    recipient. What must never happen is a transport-shaped object that accepts
    a message and does nothing with it.
    """
    cfg = BrokerDeployConfig.model_validate(VALID).to_broker_config()
    assert cfg.transport is None


def test_every_broker_config_field_is_either_fed_or_declared_derived():
    """The guard that would have caught this, aimed at the axis that was blind.

    The existing declared-vs-consumed test walks the ON-DISK fields and asserts
    each is consumed. That finds a DROPPED field and is structurally incapable
    of finding a BrokerConfig field that no on-disk field FEEDS — which is how
    `transport` stayed unreachable while every test was green.

    So this walks the other direction: every field of BrokerConfig must either
    be passed by to_broker_config() or appear in DERIVED below. Adding a field
    to BrokerConfig then forces a deliberate answer instead of defaulting to
    silence.
    """
    import ast
    import inspect
    import dataclasses

    from macf.amail.broker import BrokerConfig

    #: Fields a deployment does NOT set. Each needs a reason, because an
    #: unexplained entry here is the exemption that hides the next gap.
    DERIVED = {
        "agent_homes",   # built from the agents table
        "agent_uids",    # inverted from the same table
        "rate_limiter",  # constructed from the rate_limit_* fields
        "opsec_scan",    # bound to a callable, not named on disk
        "transport",     # constructed from transport_endpoint
    }

    tree = ast.parse(inspect.getsource(BrokerDeployConfig))
    passed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "BrokerConfig":
            passed = {kw.arg for kw in node.keywords if kw.arg}
    assert passed, "could not find the BrokerConfig(...) call to inspect"

    declared = {f.name for f in dataclasses.fields(BrokerConfig)}
    unfed = declared - passed - DERIVED
    assert not unfed, (
        f"BrokerConfig fields no deployment can set and not declared derived: "
        f"{sorted(unfed)}. A field the broker reads and the on-disk contract "
        f"cannot reach is inert in every real deployment while every unit test "
        f"stays green.")
