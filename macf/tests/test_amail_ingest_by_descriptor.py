"""MIS-0004 R37: the receiver ingests only a box file the broker owns, with one link, checked on
the descriptor it opened.

The recipient's group may remove files from its box, so it may also create them there. A container
experiment (2026-10-30) planted a pair the recipient owned and a symlinked pair, and both entered
the store as mail from another agent.
"""
import hashlib
import json
import os

import pytest

from macf.amail import client, store
from macf.amail.models import Message


def _pair(box, stem, subject="hello"):
    m = Message(sender="b@proto.local", to=["a@proto.local"], subject=subject, body="body")
    payload = m.serialize().encode()
    (box / f"{stem}.json").write_text(json.dumps({"kind": "bundle", "message_id": m.message_id,
                                                  "raw_sha256": hashlib.sha256(payload).hexdigest(),
                                                  "broker_trust": "verified"}))
    (box / f"{stem}.amsg").write_bytes(payload)
    return m


@pytest.fixture
def box(tmp_path):
    b = tmp_path / "box"
    b.mkdir(mode=0o2770)
    return b


def _ids(home):
    return [m.message_id for m in store.read_all(home)]


def test_a_genuine_pair_is_ingested(tmp_path, box):
    m = _pair(box, "1-genuine")
    [r] = client.ingest(tmp_path / "home", box, agent="a")
    assert r["ingested"] and m.message_id in _ids(tmp_path / "home") and not list(box.iterdir())


def test_a_symlinked_pair_is_refused_and_set_aside(tmp_path, box):
    elsewhere = tmp_path / "planted"
    elsewhere.mkdir()
    m = _pair(elsewhere, "s")
    for ext in ("json", "amsg"):
        os.symlink(elsewhere / f"s.{ext}", box / f"2-link.{ext}")
    [r] = client.ingest(tmp_path / "home", box, agent="a")
    assert r["refused"] and "symbolic link" in r["reason"]
    assert m.message_id not in _ids(tmp_path / "home")
    assert sorted(p.name for p in box.iterdir()) == ["2-link.amsg.refused", "2-link.json.refused"]
    assert client.ingest(tmp_path / "home", box, agent="a") == []  # reported once, not every pass


def test_a_hard_linked_message_is_refused(tmp_path, box):
    m = _pair(box, "3-pair")
    os.link(box / "3-pair.amsg", tmp_path / "second-name")
    [r] = client.ingest(tmp_path / "home", box, agent="a")
    assert r["refused"] and "2 links" in r["reason"] and m.message_id not in _ids(tmp_path / "home")


def test_a_fifo_is_refused_without_blocking(tmp_path, box):
    _pair(box, "4-pair")
    (box / "4-pair.amsg").unlink()
    os.mkfifo(box / "4-pair.amsg")
    [r] = client.ingest(tmp_path / "home", box, agent="a")
    assert r["refused"] and "not a regular file" in r["reason"]


def test_a_file_the_broker_does_not_own_is_refused(box):
    _pair(box, "5-pair")
    fd = os.open(box, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(client.BoxEntryRefused, match="not the broker's"):
            client._read_box_file(fd, "5-pair.amsg", os.getuid() + 1)
        assert client._read_box_file(fd, "5-pair.amsg", os.getuid())  # the owner reads it
    finally:
        os.close(fd)
