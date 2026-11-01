"""MIS-0004 notices and the read cursor: R25, R27 and R30, with the receiver's ingest lock.

The read cursor is Maildir's own new/cur. A notice watches the store's `new`, so it names
only mail the reader's commands can already read; `amail read` moves what it printed to
`cur`; nothing else moves it, a restart included.
"""
import argparse
import hashlib
import json
import threading
import time

import pytest

from macf.amail import client, store
from macf.amail.models import Message
from macf.transcript_monitor.sources import agent_store_source


def _put(box, stem, m):
    payload = m.serialize().encode()
    (box / f"{stem}.json").write_text(json.dumps({"kind": "bundle", "message_id": m.message_id,
                                                  "raw_sha256": hashlib.sha256(payload).hexdigest()}))
    (box / f"{stem}.amsg").write_bytes(payload)


def _put_eml(box, stem, raw):
    (box / f"{stem}.json").write_text(json.dumps({"kind": "internet",
                                                  "raw_sha256": hashlib.sha256(raw).hexdigest()}))
    (box / f"{stem}.eml").write_bytes(raw)


def _msg(subject="hello"):
    return Message(sender="b@proto.local", to=["a@proto.local"], subject=subject, body="b")


@pytest.fixture
def box(tmp_path):
    b = tmp_path / "handoff" / "a"
    b.mkdir(parents=True, mode=0o2770)
    return b


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / ".maceff").mkdir(parents=True)
    (h / ".maceff" / "amail.json").write_text(json.dumps({"handoff": str(tmp_path / "handoff"),
                                                          "agent": "a"}))
    return h


def test_notice_follows_ingest(home, box):
    """R25: mail still in the box is not yet readable, so no notice names it; once ingested
    it is, and the notice follows."""
    source = agent_store_source(home)
    source.prime()
    m = _msg()
    _put(box, "1", m)
    assert source.poll() == [], "a notice named mail `amail read` can't find yet"
    assert store.find(home, m.message_id) is None
    client.ingest(home, box, agent="a")
    [detection] = source.poll()
    assert detection.data["count"] == 1
    assert store.find(home, m.message_id) is not None


def test_reading_moves_the_cursor_past_what_was_read(home, box):
    a, b = _msg("one"), _msg("two")
    _put(box, "1", a)
    _put(box, "2", b)
    client.ingest(home, box, agent="a")
    assert len(store.unread_names(home)) == 2
    assert store.mark_read(home, a.message_id, "Reader@abc123")
    assert [store.find(home, b.message_id).message_id] == \
        [x.message_id for x in store.read_all(home, include_seen=False)]
    assert store.mark_read(home, a.message_id, "Reader@abc123") is None, "read once"
    assert {x.message_id for x in store.read_all(home)} == {a.message_id, b.message_id}


def test_the_reader_is_recorded(home, box):
    """Who moved the cursor is kept, so a notice that cleared can be explained."""
    m = _msg()
    _put(box, "1", m)
    client.ingest(home, box, agent="a")
    name = store.mark_read(home, m.message_id, "Reader@abc123")
    meta = json.loads((store.bundle_sidecars_for(home) / f"{name}.json").read_text())
    assert meta["read"]["by"] == "Reader@abc123" and meta["read"]["at"]


def test_a_read_moves_only_its_own_stores_mail(tmp_path, home, box):
    """On a shared login a read resolved to another home must not clear this agent's mail."""
    m = _msg()
    _put(box, "1", m)
    client.ingest(home, box, agent="a")
    other = tmp_path / "other"
    store.ensure_maildir(other)
    assert store.mark_read(other, m.message_id, "Other@abc123") is None
    assert len(store.unread_names(home)) == 1


def test_internet_mail_is_read_by_name_or_sha(home, box):
    raw = b"From: x@example.com\r\nSubject: hi\r\n\r\nbody\r\n"
    _put_eml(box, "1", raw)
    client.ingest(home, box, agent="a")
    [name] = store.unread_names(home)
    sha = hashlib.sha256(raw).hexdigest()
    assert store.mark_read(home, sha[:12], "Reader@abc123") == name
    assert store.unread_names(home) == []


def test_restart_keeps_cursor(tmp_path, home, box):
    """R27: a restart of any unit does not advance the read cursor. A fresh receiver and a
    fresh notice source, as a restarted daemon builds, leave unread mail unread."""
    from macf.pd.receiver import Receiver, receiver_settings
    a, b = _msg("one"), _msg("two")
    _put(box, "1", a)
    _put(box, "2", b)
    client.ingest(home, box, agent="a")
    store.mark_read(home, a.message_id, "Reader@abc123")
    before = (sorted(store.unread_names(home)),
              sorted(p.name for p in (store.maildir_for(home) / "cur").iterdir()))
    for _ in range(2):                                   # two restarts
        s = receiver_settings(home)
        Receiver("a@abc123", home, s["box"], s["agent"], s["contacts"],
                 lambda e, d: None, lambda src, nid: None).tick(0.0)
        agent_store_source(home).start()
    after = (sorted(store.unread_names(home)),
             sorted(p.name for p in (store.maildir_for(home) / "cur").iterdir()))
    assert after == before


def _list(home, monkeypatch, capsys, every=False):
    from macf import cli
    monkeypatch.setattr(cli, "_amail_config", lambda: {"home": str(home), "handoff": "", "agent": ""})
    cli.cmd_amail_list(argparse.Namespace(thread=None, json=False, all=every))
    return capsys.readouterr().out


def test_listing_new_since_last_read(home, box, monkeypatch, capsys):
    """R30: woken by a notice, the listing shows only mail new since the last read, with a
    count of the rest; --all shows everything."""
    a, b = _msg("first subject"), _msg("second subject")
    _put(box, "1", a)
    _put(box, "2", b)
    client.ingest(home, box, agent="a")
    store.mark_read(home, a.message_id, "Reader@abc123")
    out = _list(home, monkeypatch, capsys)
    assert "second subject" in out and "first subject" not in out
    assert "and 1 read, not shown" in out
    out = _list(home, monkeypatch, capsys, every=True)
    assert "second subject" in out and "first subject" in out


def test_two_ingests_at_once_store_each_message_once(home, box, monkeypatch):
    """The daemon's receiver and `amail list` share a box. Unlocked, the slower one opened
    pairs the faster had removed and an internet message read by both before either removed
    it was stored twice (the container-management maintainer, #552). The store's lock lets
    one ingest at a time."""
    bundles = [_msg(f"m{i}") for i in range(12)]
    for i, m in enumerate(bundles):
        _put(box, f"{i:02d}", m)
    raws = [f"From: x@example.com\r\nSubject: {i}\r\n\r\nb\r\n".encode() for i in range(12)]
    for i, raw in enumerate(raws):
        _put_eml(box, f"e{i:02d}", raw)
    real = client._read_box_file

    def slow(*a, **kw):                     # widen the window between listing and removal
        time.sleep(0.003)
        return real(*a, **kw)

    monkeypatch.setattr(client, "_read_box_file", slow)
    results = []
    threads = [threading.Thread(target=lambda: results.extend(client.ingest(home, box, agent="a")))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(m.message_id for m in store.read_all(home)) == sorted(m.message_id for m in bundles)
    assert len(store.read_internet(home)) == len(raws)
    assert not [r for r in results if "unreadable pair" in (r.get("reason") or "")]


def test_a_daemon_pass_skips_while_a_listing_holds_the_lock(home, box):
    _put(box, "1", _msg())
    lock = client._ingest_lock(home, wait=True)
    try:
        with pytest.raises(client.IngestBusy):
            client.ingest(home, box, agent="a", wait=False)
    finally:
        import os
        os.close(lock)
    assert client.ingest(home, box, agent="a", wait=False)[0]["ingested"]


def test_a_pair_gone_before_its_open_is_taken_not_damaged(home, box, monkeypatch):
    """A name listed and then removed by another ingest is in a store, not damaged."""
    m = _msg()
    _put(box, "1", m)
    real = client._read_box_file

    def gone(box_fd, name, uid):
        import os
        os.unlink(name, dir_fd=box_fd)
        return real(box_fd, name, uid)

    monkeypatch.setattr(client, "_read_box_file", gone)
    [r] = client.ingest(home, box, agent="a")
    assert r.get("taken") and not r["ingested"] and "unreadable" not in r["reason"]


def test_amail_read_moves_what_it_printed(home, box, monkeypatch, capsys):
    """The command, not only the store call: printing a received message is reading it."""
    from macf import cli
    a, b = _msg("one"), _msg("two")
    _put(box, "1", a)
    _put(box, "2", b)
    client.ingest(home, box, agent="a")
    monkeypatch.setattr(cli, "_amail_config", lambda: {"home": str(home), "handoff": "", "agent": ""})
    monkeypatch.setattr(cli, "_reader_card", lambda h: "Reader@abc123")
    assert cli.cmd_amail_read(argparse.Namespace(message_id=a.message_id, json=False)) == 0
    assert "one" in capsys.readouterr().out
    assert [x.message_id for x in store.read_all(home, include_seen=False)] == [b.message_id]
