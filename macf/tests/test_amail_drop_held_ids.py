"""MIS-0004 R16: the receiver drops a message id it already holds, and records the drop.

A container experiment (2026-10-30) handed the same pair off twice, as a broker restarted between
writing the box and clearing its intake would, and the recipient's store kept two copies of one id.
"""
import hashlib
import json

import pytest

from macf.amail import client, store
from macf.amail.models import Message


def _put(box, stem, m):
    payload = m.serialize().encode()
    (box / f"{stem}.json").write_text(json.dumps({"kind": "bundle", "message_id": m.message_id,
                                                  "raw_sha256": hashlib.sha256(payload).hexdigest()}))
    (box / f"{stem}.amsg").write_bytes(payload)


@pytest.fixture
def box(tmp_path):
    b = tmp_path / "box"
    b.mkdir(mode=0o2770)
    return b


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"


@pytest.fixture
def m():
    return Message(sender="b@proto.local", to=["a@proto.local"], subject="once", body="b")


def _held_copies(home, mid):
    return [m for m in store.read_all(home) if m.message_id == mid]


def test_a_copy_of_a_message_already_held_is_dropped_and_recorded(box, home, m):
    _put(box, "1-first", m)
    [first] = client.ingest(home, box, agent="a")
    assert first["ingested"]
    _put(box, "2-again", m)                       # the repeated hand-off
    [again] = client.ingest(home, box, agent="a")
    assert again["duplicate"] and not again["ingested"]
    assert len(_held_copies(home, m.message_id)) == 1
    assert not list(box.iterdir())                # the copy left the box
    [sidecar] = store.bundle_sidecars_for(home).glob("*.json")
    assert json.loads(sidecar.read_text())["duplicates_dropped"][0]["entry"] == "2-again.amsg"


def test_two_copies_in_one_pass_keep_one(box, home, m):
    _put(box, "1-first", m)
    _put(box, "2-again", m)
    results = client.ingest(home, box, agent="a")
    assert [r.get("ingested") for r in results] == [True, False] and results[1]["duplicate"]
    assert len(_held_copies(home, m.message_id)) == 1


def test_different_ids_are_both_kept(box, home, m):
    other = Message(sender="b@proto.local", to=["a@proto.local"], subject="twice", body="b")
    _put(box, "1-one", m)
    _put(box, "2-two", other)
    assert all(r["ingested"] for r in client.ingest(home, box, agent="a"))
    assert {x.message_id for x in store.read_all(home)} == {m.message_id, other.message_id}
