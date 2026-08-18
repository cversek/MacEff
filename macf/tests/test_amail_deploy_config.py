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
