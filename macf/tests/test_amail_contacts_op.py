"""`amail contacts`: an agent asks the broker which correspondents it checks for it (GH#695).

The broker answers over its socket rather than the file, scoped to the caller the way `status` is, and the
listing is identity and direction only.
"""
import argparse
import json
import os
import tempfile
import time

import pytest
import yaml

from macf.amail import Broker, BrokerConfig, serve

DOMAIN = "mailhost.example"


@pytest.fixture
def deployment(tmp_path):
    homes = {a: tmp_path / a for a in ("alpha", "beta")}
    for h in homes.values():
        h.mkdir()
    contacts = tmp_path / "addressing.yaml"
    contacts.write_text(yaml.safe_dump({"domain": DOMAIN, "tier": "host", "supervision": "operator-at-terminal", "agents": {
        "alpha": {"contacts": [{"address": f"beta@{DOMAIN}", "direction": "both"},
                               {"address": f"carol@{DOMAIN}", "direction": "outbound"},
                               {"address": f"dave@{DOMAIN}", "direction": "inbound"},
                               {"address": f"erin@{DOMAIN}", "direction": "neither"}]},
        "beta": {"contacts": [{"address": f"alpha@{DOMAIN}", "direction": "both"}]}}}))
    contacts.chmod(0o644)
    cred = tmp_path / "cred"
    cred.write_text("secret")
    cred.chmod(0o600)
    with tempfile.TemporaryDirectory(prefix="amc", dir="/tmp") as sock_dir:
        cfg = BrokerConfig(domain=DOMAIN, agent_homes=homes, contacts_path=contacts,
                           audit_path=tmp_path / "audit.jsonl", socket_path=__import__("pathlib").Path(sock_dir) / "c.sock",
                           credentials_path=cred, inbound_handoff=tmp_path / "handoff",
                           inbound_quarantine=tmp_path / "quarantine",
                           shared_uid_agents={os.getuid(): ("alpha", "beta")}, tier="host",
                           supervision="operator-at-terminal")
        broker = Broker(cfg)
        srv = serve(broker)
        time.sleep(0.15)
        yield {"cfg": cfg, "broker": broker, "audit": tmp_path / "audit.jsonl"}
        srv.shutdown()


def test_the_broker_lists_the_callers_correspondents_with_their_direction(deployment):
    from macf.amail.client import contacts
    reply = contacts(deployment["cfg"].socket_path, sender="alpha")
    assert reply["ok"] is True, reply
    assert reply["contact_list"] is True
    assert reply["contacts"] == [
        {"address": f"beta@{DOMAIN}", "direction": "both"},
        {"address": f"carol@{DOMAIN}", "direction": "outbound"},
        {"address": f"dave@{DOMAIN}", "direction": "inbound"},
        {"address": f"erin@{DOMAIN}", "direction": "neither"},     # withdrawn, shown as withdrawn
    ]


def test_the_listing_is_the_callers_own_and_a_claim_for_no_agent_is_refused(deployment):
    from macf.amail.client import contacts
    sock = deployment["cfg"].socket_path
    assert contacts(sock, sender="beta")["contacts"] == [{"address": f"alpha@{DOMAIN}", "direction": "both"}]
    refused = contacts(sock, sender="gamma")
    assert refused["ok"] is False and "bound to alpha, beta" in refused["error"]


def test_an_entry_carries_an_address_and_a_direction_and_nothing_else(deployment):
    from macf.amail.client import contacts
    for entry in contacts(deployment["cfg"].socket_path, sender="alpha")["contacts"]:
        assert set(entry) == {"address", "direction"}


def test_the_read_is_audited_with_its_count(deployment):
    from macf.amail.client import contacts
    contacts(deployment["cfg"].socket_path, sender="alpha")
    lines = [json.loads(l) for l in deployment["audit"].read_text().splitlines() if l.strip()]
    reads = [r for r in lines if r.get("operation") == "contacts"]
    assert reads and reads[-1]["count"] == 4, lines[-3:]


def test_a_broker_with_no_contact_list_says_so_instead_of_listing_nobody(deployment):
    broker = deployment["broker"]
    broker.contacts = None
    assert broker.contact_entries("alpha") == {"ok": True, "contacts": [], "contact_list": False}
    lines = [json.loads(l) for l in deployment["audit"].read_text().splitlines() if l.strip()]
    reads = [r for r in lines if r.get("operation") == "contacts"]
    assert reads and reads[-1]["count"] == 0, lines[-3:]


def _run(monkeypatch, capsys, deployment, **ns):
    import macf.cli as cli
    monkeypatch.setattr(cli, "_amail_config", lambda: {"socket": str(deployment["cfg"].socket_path), "agent": "alpha"})
    monkeypatch.setattr(cli, "_ensure_host_broker", lambda cfg: None)
    args = argparse.Namespace(filter=ns.get("filter"), json=ns.get("json", False))
    assert cli.cmd_amail_contacts(args) == 0
    return capsys.readouterr().out


def test_the_command_prints_each_correspondent_and_filters_by_text(monkeypatch, capsys, deployment):
    out = _run(monkeypatch, capsys, deployment)
    assert f"carol@{DOMAIN}" in out and f"erin@{DOMAIN}" in out and "withdrawn" in out
    only = _run(monkeypatch, capsys, deployment, filter="CAROL")
    assert f"carol@{DOMAIN}" in only and f"beta@{DOMAIN}" not in only
    as_json = json.loads(_run(monkeypatch, capsys, deployment, json=True))
    assert len(as_json["contacts"]) == 4 and as_json["contact_list"] is True


def test_an_agent_with_no_provisioned_mailbox_is_refused_by_the_broker(deployment):
    with pytest.raises(PermissionError, match="no provisioned mailbox"):
        deployment["broker"].contact_entries("gamma")


def test_the_command_against_a_broker_with_no_contact_list_says_so_in_text_and_json(monkeypatch, capsys, deployment):
    deployment["broker"].contacts = None
    text = _run(monkeypatch, capsys, deployment)
    assert "no contact list" in text and "alpha" not in text
    as_json = json.loads(_run(monkeypatch, capsys, deployment, json=True))
    assert as_json == {"contacts": [], "contact_list": False}


def _refused(monkeypatch, capsys, deployment, agent="alpha", **ns):
    import macf.cli as cli
    monkeypatch.setattr(cli, "_amail_config", lambda: {"socket": str(deployment["cfg"].socket_path), "agent": agent})
    monkeypatch.setattr(cli, "_ensure_host_broker", lambda cfg: None)
    rc = cli.cmd_amail_contacts(argparse.Namespace(filter=None, json=ns.get("json", False)))
    return rc, capsys.readouterr().out


def test_a_broker_that_predates_the_operation_is_reported_not_read_as_no_correspondents(monkeypatch, capsys, deployment):
    def older(agent):
        raise ValueError("unknown operation 'contacts'")
    monkeypatch.setattr(deployment["broker"], "contact_entries", older)
    rc, out = _refused(monkeypatch, capsys, deployment)
    assert rc == 1 and "refused" in out and "unknown operation" in out and "restart" in out
    assert "no correspondents" not in out
    rc, out = _refused(monkeypatch, capsys, deployment, json=True)
    as_json = json.loads(out)
    assert rc == 1 and as_json["ok"] is False and "unknown operation" in as_json["error"] and "contacts" not in as_json


def test_a_refusal_for_this_agent_is_shown_with_the_brokers_reason(monkeypatch, capsys, deployment):
    rc, out = _refused(monkeypatch, capsys, deployment, agent="gamma")
    assert rc == 1 and "claimed" in out and "gamma" in out and "restart" not in out
