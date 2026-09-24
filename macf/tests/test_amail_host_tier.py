"""The host tier (amail.md §1.3, §7.5): declarations, their refusals, and identity by claim.

The container tier must read exactly as before: a repeated uid is refused with the
same words, and a claim that disagrees with the kernel is refused. The host tier
adds one thing -- a uid several agents share, identified by the client's claim --
and the audit must say `claimed:` for it and never `so_peercred:`.
"""
import json
import os
import time

import pytest
import yaml
from pydantic import ValidationError

from macf.amail import Broker, BrokerConfig, Message, serve
from macf.amail import deploy_config as dc
from macf.amail.client import submit
from macf.amail.deploy_config import AddressingConfig, BrokerDeployConfig

DOMAIN = "host.test"


def addressing(tier=None, supervision=None, shared=(True, True), uids=(1002, 1002)):
    d = {"domain": DOMAIN, "agents": {
        "alpha": {"home": "/home/x", "uid": uids[0], "shared_uid": shared[0], "contacts": [f"beta@{DOMAIN}"]},
        "beta": {"home": "/home/x", "uid": uids[1], "shared_uid": shared[1], "contacts": [f"alpha@{DOMAIN}"]},
    }}
    if tier:
        d["tier"] = tier
    if supervision:
        d["supervision"] = supervision
    return d


# ---- declarations ---------------------------------------------------------------

def test_container_tier_still_refuses_a_repeated_uid_with_the_same_words():
    with pytest.raises(ValidationError, match="share uid.*authentication table"):
        AddressingConfig.model_validate(addressing(shared=(False, False)))
    # marking them shared does not help without the tier
    with pytest.raises(ValidationError, match="share uid"):
        AddressingConfig.model_validate(addressing(shared=(True, True)))


def test_host_tier_permits_a_shared_uid_only_when_every_agent_on_it_says_so():
    ok = AddressingConfig.model_validate(addressing("host", "operator-at-terminal"))
    assert ok.tier == "host" and ok.supervision == "operator-at-terminal"
    with pytest.raises(ValidationError, match="not both are marked shared_uid"):
        AddressingConfig.model_validate(addressing("host", "operator-at-terminal", shared=(True, False)))


def test_host_tier_requires_a_named_supervision():
    with pytest.raises(ValidationError, match="without a supervision"):
        AddressingConfig.model_validate(addressing("host"))
    with pytest.raises(ValidationError, match="without a supervision"):
        AddressingConfig.model_validate(addressing("host", "none"))


def test_a_host_tier_file_refuses_to_load_inside_a_container(tmp_path, monkeypatch):
    marker = tmp_path / "dockerenv"
    monkeypatch.setattr(dc, "CONTAINER_MARKER", marker)
    AddressingConfig.model_validate(addressing("host", "hypervisor"))       # no marker: fine
    marker.write_text("")
    with pytest.raises(ValidationError, match="inside a container"):
        AddressingConfig.model_validate(addressing("host", "hypervisor"))
    # the container tier is untouched by the marker
    AddressingConfig.model_validate(addressing(uids=(1002, 1003), shared=(False, False)))


def test_the_broker_config_carries_the_shared_table_the_tier_and_the_supervision(tmp_path):
    a = tmp_path / "addressing.yaml"
    a.write_text(yaml.safe_dump(addressing("host", "operator-at-terminal")))
    cfg = BrokerDeployConfig.model_validate({
        "addressing_path": str(a), "audit_path": str(tmp_path / "audit.jsonl"),
        "inbound_quarantine": str(tmp_path / "q"), "inbound_handoff": str(tmp_path / "h"),
    }).to_broker_config()
    assert cfg.tier == "host" and cfg.supervision == "operator-at-terminal"
    assert cfg.agent_uids == {} and cfg.shared_uid_agents == {1002: ("alpha", "beta")}


# ---- identity by claim, over the socket --------------------------------------------

@pytest.fixture
def host_deployment(tmp_path, sock_dir):
    homes = {a: tmp_path / a for a in ("alpha", "beta")}
    for h in homes.values():
        h.mkdir()
    contacts = tmp_path / "addressing.yaml"
    contacts.write_text(yaml.safe_dump({"domain": DOMAIN, "tier": "host", "supervision": "operator-at-terminal", "agents": {
        "alpha": {"contacts": [{"address": f"beta@{DOMAIN}", "direction": "both"}]},
        "beta": {"contacts": [{"address": f"alpha@{DOMAIN}", "direction": "both"}]}}}))
    contacts.chmod(0o644)
    cred = tmp_path / "cred"; cred.write_text("secret"); cred.chmod(0o600)
    cfg = BrokerConfig(domain=DOMAIN, agent_homes=homes, contacts_path=contacts,
                       audit_path=tmp_path / "audit.jsonl", socket_path=sock_dir / "h.sock",
                       credentials_path=cred, inbound_handoff=tmp_path / "handoff",
                       inbound_quarantine=tmp_path / "quarantine",
                       # THE test process's one uid names two agents: identity comes from the claim
                       shared_uid_agents={os.getuid(): ("alpha", "beta")}, tier="host",
                       supervision="operator-at-terminal")
    srv = serve(Broker(cfg))
    time.sleep(0.15)
    yield {"cfg": cfg, "audit": tmp_path / "audit.jsonl"}
    srv.shutdown()


def _records(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def test_a_claim_bound_to_the_shared_uid_is_accepted_and_audited_as_a_claim(host_deployment):
    r = submit("beta", Message(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"], subject="s", body="b"),
               host_deployment["cfg"].socket_path)
    assert r["ok"] is True, r
    allowed = [x for x in _records(host_deployment["audit"]) if x.get("decision") == "allowed"]
    assert allowed and allowed[-1]["authorship"] == "claimed:beta" and allowed[-1]["tier"] == "host"
    assert not any(x.get("authorship", "").startswith("so_peercred") for x in allowed)


def test_a_claim_outside_the_uids_names_is_refused_and_recorded(host_deployment):
    r = submit("gamma", Message(sender=f"gamma@{DOMAIN}", to=[f"alpha@{DOMAIN}"], subject="s", body="b"),
               host_deployment["cfg"].socket_path)
    assert r["ok"] is False and "PermissionError" in r["error"] and "bound to alpha, beta" in r["error"]
    refused = [x for x in _records(host_deployment["audit"]) if x.get("decision") == "refused"]
    assert refused and "not bound to shared uid" in refused[-1]["reason"] and refused[-1]["tier"] == "host"


def test_a_shared_uid_without_a_claim_cannot_be_identified(host_deployment):
    from macf.amail.client import _roundtrip
    r = _roundtrip({"message": Message(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"], subject="s", body="b").to_dict()},
                   host_deployment["cfg"].socket_path, 5.0, "")
    assert r["ok"] is False and "carries no sender claim" in r["error"]


def test_on_an_unshared_uid_a_disagreeing_claim_is_still_refused(tmp_path, sock_dir):
    """The container tier's rule, unchanged: the kernel names the uid and a claim
    to be someone else is refused, not 'settled'."""
    homes = {a: tmp_path / a for a in ("alpha", "beta")}
    for h in homes.values():
        h.mkdir()
    contacts = tmp_path / "addressing.yaml"
    contacts.write_text(yaml.safe_dump({"domain": DOMAIN, "agents": {
        "alpha": {"contacts": [{"address": f"beta@{DOMAIN}", "direction": "both"}]},
        "beta": {"contacts": [{"address": f"alpha@{DOMAIN}", "direction": "both"}]}}}))
    contacts.chmod(0o644)
    cred = tmp_path / "cred"; cred.write_text("secret"); cred.chmod(0o600)
    cfg = BrokerConfig(domain=DOMAIN, agent_homes=homes, contacts_path=contacts, audit_path=tmp_path / "a.jsonl",
                       socket_path=sock_dir / "c.sock", credentials_path=cred, inbound_handoff=tmp_path / "handoff",
                       inbound_quarantine=tmp_path / "q", agent_uids={os.getuid(): "alpha"})
    srv = serve(Broker(cfg)); time.sleep(0.15)
    try:
        r = submit("beta", Message(sender=f"beta@{DOMAIN}", to=[f"alpha@{DOMAIN}"], subject="s", body="b"), cfg.socket_path)
        assert r["ok"] is False and "connecting process is 'alpha'" in r["error"]
        ok = submit("alpha", Message(sender=f"alpha@{DOMAIN}", to=[f"beta@{DOMAIN}"], subject="s", body="b"), cfg.socket_path)
        assert ok["ok"] is True, ok
        allowed = [x for x in _records(tmp_path / "a.jsonl") if x.get("decision") == "allowed"]
        assert allowed[-1]["authorship"] == "so_peercred:alpha" and allowed[-1]["tier"] == "container"
    finally:
        srv.shutdown()
