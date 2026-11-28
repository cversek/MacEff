"""MIS-0004's box rows, read from what the broker actually writes.

- R13 (box_MUST_be_readable_only_by_its_agent): the box and its files are
  owned by the broker's account and readable by the recipient's group only.
- R36 (box_file_MUST-NOT_be_group_writable): no message file in a box is
  writable by its group, so the recipient can't rewrite what the broker vouched for.

One account runs the test, so "the broker's account" is the test's own uid and
"the recipient's group" is the box's group. The two-account form of these
checks ran in the container prototype (#850); R12's test is that run's successor.
"""
import os
import stat

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from conftest import _addressing

from macf.amail.broker import Broker, BrokerConfig
from macf.amail.models import Message

DOMAIN = "host.local"


@pytest.fixture
def broker(tmp_path):
    """One deployment; ira may write to sparrow."""
    addressing = tmp_path / "addressing.yaml"
    addressing.write_text(_addressing({"ira": [f"sparrow@{DOMAIN}"], "sparrow": [f"ira@{DOMAIN}"]},
                                      domain=DOMAIN))
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    for a in ("ira", "sparrow"):
        (handoff / a).mkdir(mode=0o2770)
        (tmp_path / "home" / a).mkdir(parents=True)
    return Broker(BrokerConfig(
        domain=DOMAIN,
        agent_homes={a: tmp_path / "home" / a for a in ("ira", "sparrow")},
        contacts_path=addressing,
        audit_path=tmp_path / "audit.jsonl",
        dispositions_dir=tmp_path / "dispositions",
        inbound_quarantine=tmp_path / "quarantine",
        inbound_handoff=handoff,
    ))


@pytest.fixture
def delivered(broker):
    """sparrow's box after one delivery from ira: the box, and every file in it."""
    r = broker.submit("ira", Message(sender=f"ira@{DOMAIN}", to=[f"sparrow@{DOMAIN}"],
                                     subject="box", body="box"))
    assert r["ok"], r
    return broker.config.inbound_handoff / "sparrow"


def test_box_permissions(delivered):
    box = os.stat(delivered)
    assert box.st_uid == os.geteuid(), "the broker's account owns the box"
    assert box.st_mode & stat.S_IRWXO == 0, "no other account may enter the box"
    files = [p for p in delivered.iterdir() if p.is_file()]
    assert {p.suffix for p in files} == {".amsg", ".json"}
    for p in files:
        st = os.stat(p)
        assert st.st_uid == os.geteuid(), p.name
        assert st.st_gid == box.st_gid, f"{p.name} carries the recipient's group"
        assert st.st_mode & stat.S_IRGRP, f"{p.name} is readable by the recipient's group"
        assert st.st_mode & stat.S_IRWXO == 0, f"{p.name} is closed to other accounts"


def test_box_files_not_group_writable(delivered):
    for p in delivered.iterdir():
        if p.is_file():
            assert os.stat(p).st_mode & stat.S_IWGRP == 0, p.name


def _sparrow_ingest(broker):
    from macf.amail.client import ingest
    return ingest(broker.config.agent_homes["sparrow"], broker.config.inbound_handoff / "sparrow",
                  broker.config.contacts_path, "sparrow")


def _held_ids(broker):
    from macf.amail import store
    return {m.message_id for m in store.read_all(broker.config.agent_homes["sparrow"])}


def _send(broker, body):
    r = broker.submit("ira", Message(sender=f"ira@{DOMAIN}", to=[f"sparrow@{DOMAIN}"],
                                     subject="r37", body=body))
    assert r["ok"], r
    return r["message_id"]


def test_receiver_checks_owner_and_links(broker, tmp_path, monkeypatch):
    """R37 (receiver_MUST_check_owner_and_link_count): the receiver ingests only a file the
    broker's account owns with one link, read on the descriptor it opened. A hard link made from
    outside the box and a pair the recipient's group created are each refused and set aside, and
    neither reaches the store; a genuine delivery in the same box still does."""
    from macf.amail import client

    box = broker.config.inbound_handoff / "sparrow"
    genuine = _send(broker, "genuine")
    linked = _send(broker, "hard-linked")
    [linked_amsg] = [p for p in box.glob("*.amsg") if linked in p.name]
    os.link(linked_amsg, tmp_path / "a-second-name-outside-the-box")

    results = {r.get("name", ""): r for r in _sparrow_ingest(broker)}
    assert genuine in _held_ids(broker), "the broker's own single-link file is ingested"
    assert linked not in _held_ids(broker), "a file with a second link is not ingested"
    refused = [r for r in results.values() if r.get("refused")]
    assert len(refused) == 1 and "2 links" in refused[0]["reason"]
    assert sorted(p.name for p in box.iterdir() if p.name.endswith(".refused")) == sorted(
        [linked_amsg.name + ".refused", linked_amsg.with_suffix(".json").name + ".refused"]), \
        "the hard-linked pair is set aside, not left to be refused again"

    # A pair the recipient's group created: same bytes a broker would write, but the box's owner
    # (the broker's account) is someone else. One account runs the test, so the box owner stands in.
    planted = _send(broker, "planted")
    [planted_amsg] = [p for p in box.glob("*.amsg") if planted in p.name]
    monkeypatch.setattr(client, "_box_owner", lambda fd: os.getuid() + 1)
    [r] = _sparrow_ingest(broker)
    assert r["refused"] and "not the broker's" in r["reason"]
    assert planted not in _held_ids(broker)
    assert (box / (planted_amsg.name + ".refused")).exists()
    assert (box / (planted_amsg.with_suffix(".json").name + ".refused")).exists()
