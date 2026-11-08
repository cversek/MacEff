"""MIS-0004 placement: the receiver runs as its agent, under that agent's primal daemon (R04).

Before the receiver, mail left the broker's pickup box only when the agent ran `amail list`.
The receiver is a duty of the primal daemon's loop: it ingests the box each pass, as the
agent, into the agent's own store, taking its box from the agent's own amail settings.
"""
import hashlib
import json
import os
import time
from types import SimpleNamespace

import pytest
from pathlib import Path

from macf.amail import store
from macf.amail.models import Message
from macf.pd.receiver import Receiver, receiver_settings
from test_primal_daemon import base, make_home, run_daemon  # noqa: F401 - fixtures


def _put(box, stem, m):
    payload = m.serialize().encode()
    (box / f"{stem}.json").write_text(json.dumps({"kind": "bundle", "message_id": m.message_id,
                                                  "raw_sha256": hashlib.sha256(payload).hexdigest()}))
    (box / f"{stem}.amsg").write_bytes(payload)


def _settings(home, handoff, agent):
    (home / ".maceff").mkdir(parents=True, exist_ok=True)
    (home / ".maceff" / "amail.json").write_text(json.dumps({"handoff": str(handoff), "agent": agent}))


def _receiver(home, card="Tester_abc123"):
    s = receiver_settings(home)
    events, notices = [], []
    r = Receiver(card, home, s["box"], s["agent"], s["contacts"],
                 lambda e, d: events.append((e, d)), lambda src, nid: notices.append((src, nid)))
    return SimpleNamespace(receiver=r, events=events, notices=notices)


def _msg(subject="hello"):
    return Message(sender="b@proto.local", to=["a@proto.local"], subject=subject, body="b")


def test_receiver_runs_as_its_agent(tmp_path, base, run_daemon, monkeypatch):
    """The agent's own primal daemon ingests what the broker handed off, into the agent's
    store, owned by the agent's account, with no `amail list` run."""
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    home = make_home(tmp_path, [])
    box = tmp_path / "handoff" / "tester"
    box.mkdir(parents=True, mode=0o2770)
    _settings(home, tmp_path / "handoff", "tester")
    m = _msg()
    _put(box, "1-first", m)
    run_daemon(home, base)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not store.find(home, m.message_id):
        time.sleep(0.05)
    assert store.find(home, m.message_id) is not None, "the daemon never ingested the box"
    assert not list(box.glob("*.amsg")), "the pair left the box"
    [f] = list((store.maildir_for(home) / "new").iterdir())
    assert f.stat().st_uid == os.getuid()


def test_the_box_comes_from_the_settings_never_the_environment(tmp_path, monkeypatch):
    """On a shared login every daemon can reach every box; a variable naming another agent
    must not move this agent's receiver to it."""
    home = tmp_path / "home"
    _settings(home, tmp_path / "handoff", "a")
    monkeypatch.setenv("MACEFF_AGENT_NAME", "b")
    monkeypatch.setenv("MACF_AMAIL_HANDOFF", str(tmp_path / "elsewhere"))
    assert receiver_settings(home)["box"] == tmp_path / "handoff" / "a"
    # Settings that name only the agent: the handoff is the fixed default, never the variable.
    (home / ".maceff" / "amail.json").write_text(json.dumps({"agent": "a"}))
    assert receiver_settings(home)["box"] == Path("/var/lib/amail/handoff") / "a"


def test_no_agent_in_the_settings_means_no_receiver(tmp_path, monkeypatch):
    monkeypatch.setenv("MACEFF_AGENT_NAME", "someone")
    home = tmp_path / "home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "amail.json").write_text(json.dumps({"handoff": str(tmp_path / "h")}))
    assert receiver_settings(home) is None


def test_two_agents_on_one_login_each_ingest_only_their_own_box(tmp_path, monkeypatch):
    """One uid, two homes, two receivers: neither takes the other's mail."""
    monkeypatch.setenv("MACEFF_AGENT_NAME", "a")         # the shell names one of them
    homes = {}
    for agent in ("a", "b"):
        homes[agent] = tmp_path / agent
        _settings(homes[agent], tmp_path / "handoff", agent)
        (tmp_path / "handoff" / agent).mkdir(parents=True, mode=0o2770)
    ma, mb = _msg("for a"), _msg("for b")
    _put(tmp_path / "handoff" / "a", "1", ma)
    _put(tmp_path / "handoff" / "b", "1", mb)
    for agent in ("a", "b"):
        _receiver(homes[agent], card=f"{agent}@abc123").receiver.tick(0.0)
    assert [x.message_id for x in store.read_all(homes["a"])] == [ma.message_id]
    assert [x.message_id for x in store.read_all(homes["b"])] == [mb.message_id]


def test_a_box_the_daemon_cant_list_raises_a_notice_not_an_empty_box(tmp_path):
    """On macOS the daemon's privacy grants differ from the terminal's; in a container a
    daemon with its groups cleared loses a box it reached through one. Either way the first
    pass says so (MIS-0002-R65), and never reads as no mail."""
    if os.geteuid() == 0:
        pytest.skip("root lists any directory")
    home = tmp_path / "home"
    box = tmp_path / "handoff" / "a"
    box.mkdir(parents=True)
    _settings(home, tmp_path / "handoff", "a")
    _put(box, "1", _msg())
    box.chmod(0o000)
    try:
        rig = _receiver(home)
        rig.receiver.tick(0.0)
        assert rig.receiver.refused and "can't be listed" in rig.receiver.refused
        assert [n[0] for n in rig.notices] == ["pd_grant_denied"]
        rig.receiver.tick(10.0)
        assert len(rig.notices) == 1, "said once, not every pass"
    finally:
        box.chmod(0o770)


def test_one_pass_records_what_it_moved(tmp_path):
    home = tmp_path / "home"
    box = tmp_path / "handoff" / "a"
    box.mkdir(parents=True, mode=0o2770)
    _settings(home, tmp_path / "handoff", "a")
    _put(box, "1", _msg())
    rig = _receiver(home)
    rig.receiver.tick(0.0)
    assert [(e, d["ingested"]) for e, d in rig.events] == [("pd_mail_ingested", 1)]
    rig.receiver.tick(10.0)
    assert len(rig.events) == 1, "a pass that moved nothing writes nothing"


def test_a_box_made_later_is_still_checked(tmp_path):
    """The check waits for the box: one the broker makes after the daemon started, with a
    group this daemon can't use, is said when it appears (the host-side maintainer, #871)."""
    if os.geteuid() == 0:
        pytest.skip("root lists any directory")
    home = tmp_path / "home"
    _settings(home, tmp_path / "handoff", "a")
    rig = _receiver(home)
    rig.receiver.tick(0.0)
    assert rig.notices == [] and not rig.receiver.refused, "no box yet is nothing to refuse"
    box = tmp_path / "handoff" / "a"
    box.mkdir(parents=True)
    box.chmod(0o000)
    try:
        rig.receiver.tick(10.0)
        assert [n[0] for n in rig.notices] == ["pd_grant_denied"]
    finally:
        box.chmod(0o770)


# --- MIS-0004 R05: an Internet-reachable agent runs under a login no other agent shares ---------

import yaml as _yaml

from macf.amail.deploy_config import BrokerDeployConfig, ConfigError


def _r05_start(tmp_path, agents, zone=True, host=False):
    a = tmp_path / "addressing.yaml"
    body = {"domain": "box.local", "agents": agents}
    if zone:
        body["zone"] = "agents.example.org"
    if host:
        body.update({"tier": "host", "supervision": "operator-at-terminal"})
    a.write_text(_yaml.safe_dump(body))
    return BrokerDeployConfig.model_validate({
        "addressing_path": str(a), "audit_path": str(tmp_path / "a.jsonl"),
        "inbound_quarantine": str(tmp_path / "q"), "inbound_handoff": str(tmp_path / "h"),
    }).to_broker_config()


def _r05_agent(tmp_path, name, uid, card, token):
    return {"home": str(tmp_path / name), "uid": uid, "contacts": [], "card": card, "zone_token": token}


def test_reachable_agent_has_own_login(tmp_path):
    ok = {"wren": _r05_agent(tmp_path, "wren", 1002, "WrenTuba_3c9d1e", "0123456789ab"),
          "ira": _r05_agent(tmp_path, "ira", 1003, "IraTest_a1a1a1", "fedcba987654")}
    assert _r05_start(tmp_path, ok)
    shared = {"wren": {**_r05_agent(tmp_path, "wren", 1002, "WrenTuba_3c9d1e", "0123456789ab"), "shared_uid": True},
              "ira": {**_r05_agent(tmp_path, "ira", 1002, "IraTest_a1a1a1", "fedcba987654"), "shared_uid": True}}
    with pytest.raises(ConfigError, match="R05"):
        _r05_start(tmp_path, shared, host=True)
    # Without a zone, no agent is reachable from the Internet, and a shared host login stays allowed.
    assert _r05_start(tmp_path, shared, zone=False, host=True)
