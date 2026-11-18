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
