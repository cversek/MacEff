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
    assert store.mark_read(home, a.message_id, "Reader_abc123")
    assert [store.find(home, b.message_id).message_id] == \
        [x.message_id for x in store.read_all(home, include_seen=False)]
    assert store.mark_read(home, a.message_id, "Reader_abc123") is None, "read once"
    assert {x.message_id for x in store.read_all(home)} == {a.message_id, b.message_id}


def test_the_reader_is_recorded(home, box):
    """Who moved the cursor is kept, so a notice that cleared can be explained."""
    m = _msg()
    _put(box, "1", m)
    client.ingest(home, box, agent="a")
    name = store.mark_read(home, m.message_id, "Reader_abc123")
    meta = json.loads((store.bundle_sidecars_for(home) / f"{name}.json").read_text())
    assert meta["read"]["by"] == "Reader_abc123" and meta["read"]["at"]


def test_a_read_moves_only_its_own_stores_mail(tmp_path, home, box):
    """On a shared login a read resolved to another home must not clear this agent's mail."""
    m = _msg()
    _put(box, "1", m)
    client.ingest(home, box, agent="a")
    other = tmp_path / "other"
    store.ensure_maildir(other)
    assert store.mark_read(other, m.message_id, "Other_abc123") is None
    assert len(store.unread_names(home)) == 1


def test_internet_mail_is_read_by_name_or_sha(home, box):
    raw = b"From: x@example.com\r\nSubject: hi\r\n\r\nbody\r\n"
    _put_eml(box, "1", raw)
    client.ingest(home, box, agent="a")
    [name] = store.unread_names(home)
    sha = hashlib.sha256(raw).hexdigest()
    assert store.mark_read(home, sha[:12], "Reader_abc123") == name
    assert store.unread_names(home) == []


def test_restart_keeps_cursor(tmp_path, home, box):
    """R27: a restart of any unit does not advance the read cursor. A fresh receiver and a
    fresh notice source, as a restarted daemon builds, leave unread mail unread."""
    from macf.pd.receiver import Receiver, receiver_settings
    a, b = _msg("one"), _msg("two")
    _put(box, "1", a)
    _put(box, "2", b)
    client.ingest(home, box, agent="a")
    store.mark_read(home, a.message_id, "Reader_abc123")
    before = (sorted(store.unread_names(home)),
              sorted(p.name for p in (store.maildir_for(home) / "cur").iterdir()))
    for _ in range(2):                                   # two restarts
        s = receiver_settings(home)
        Receiver("a_abc123", home, s["box"], s["agent"], s["contacts"],
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
    store.mark_read(home, a.message_id, "Reader_abc123")
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
    monkeypatch.setattr(cli, "_reader_card", lambda h: "Reader_abc123")
    assert cli.cmd_amail_read(argparse.Namespace(message_id=a.message_id, json=False)) == 0
    assert "one" in capsys.readouterr().out
    assert [x.message_id for x in store.read_all(home, include_seen=False)] == [b.message_id]


def test_the_wake_names_unread_ids_from_a_real_ingest(home, box):
    """The keystroke wake (MIS-0002-R105) names what waits. A Maildir's names carry no id, so
    the ids come from the sidecars ingest writes; read mail drops out."""
    a, b = _msg("one"), _msg("two")
    _put(box, "1", a)
    client.ingest(home, box, agent="a")
    time.sleep(1.05)                                    # Maildir names are second-granular
    _put(box, "2", b)
    client.ingest(home, box, agent="a")
    assert store.unread_message_ids(home) == [a.message_id, b.message_id]
    store.mark_read(home, a.message_id, "Reader_abc123")
    assert store.unread_message_ids(home) == [b.message_id]


@pytest.mark.parametrize("kind", ["bundle", "internet"])
def test_a_message_without_its_sidecar_is_damage_not_taken(home, box, kind):
    """Only a missing message is another ingest's work. The broker writes the sidecar first,
    so a message whose sidecar is gone is damage or tampering, and is said as such, every
    pass, until someone looks (the container-management maintainer, #871)."""
    if kind == "bundle":
        _put(box, "1", _msg())
    else:
        _put_eml(box, "1", b"From: x@example.com\r\nSubject: hi\r\n\r\nbody\r\n")
    (box / "1.json").unlink()
    [r] = client.ingest(home, box, agent="a")
    assert not r.get("taken") and not r["ingested"]
    assert "without its sidecar" in r["reason"]


def _channel_pair():
    import socket
    ours, theirs = socket.socketpair()
    theirs.settimeout(0.5)
    return ours, theirs


def _sources_sent(conn):
    import socket
    from macf.channels.maceff_channel import parse_record
    data = b""
    try:
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    return [parse_record(line).source for line in data.decode().splitlines() if line]


def test_notice_level_triggered(home, box, monkeypatch):
    """R26: while unread mail exists the notice stays asserted, so each channel that attaches
    is told; once the cursor passes the mail, an owed notice is withdrawn, not delivered."""
    from macf.channels.maceff_channel import TAKES
    from macf.pd import notifier as nt
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    m = _msg()
    _put(box, "1", m)
    client.ingest(home, box, agent="a")
    n = nt.Notifier(home, {"amail": "agent"})
    n.boot()                                    # one notice owed for what waits at start
    first, first_end = _channel_pair()
    n.attach(first, takes=TAKES)
    n.flush()
    assert _sources_sent(first_end) == ["amail"]
    assert not n.owed
    n.detach(first)
    # a new session's channel, the mail still unread: asserted again
    second, second_end = _channel_pair()
    n.attach(second, takes=TAKES)
    n.flush()
    assert _sources_sent(second_end) == ["amail"]
    n.detach(second)
    # with no channel, a new arrival is owed; reading everything withdraws it
    _put(box, "2", _msg("two"))
    client.ingest(home, box, agent="a")
    n.poll()
    assert [o.source for o in n.owed.values()] == ["amail"]
    for x in store.read_all(home, include_seen=False):
        store.mark_read(home, x.message_id, "Reader_abc123")
    n.poll()
    assert not n.owed, "a notice for mail already read stayed owed"
    third, third_end = _channel_pair()
    n.attach(third, takes=TAKES)
    n.flush()
    assert _sources_sent(third_end) == [], "read mail was asserted"
    restarted = nt.Notifier(home, {"amail": "agent"})
    restarted.boot()
    assert not restarted.owed, "a restart owed a withdrawn notice again"


def test_unsilenced_mail_reaches_a_channel_that_stayed_attached(home, box, monkeypatch):
    """Silenced, the notice is settled without telling the session. Unsilenced, the same
    attached channel is told on the next pass, not only at an attach that may never come;
    once told, it isn't told again every pass (the container-management maintainer, #874)."""
    from macf.channels.maceff_channel import TAKES
    from macf.pd import notifier as nt
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    silenced = [True]

    class Rules:
        def delivers(self, source, subscriber):
            return not silenced[0]

    n = nt.Notifier(home, {"amail": "agent"}, rules=lambda: Rules())
    n.boot()
    ours, theirs = _channel_pair()
    n.attach(ours, takes=TAKES)
    _put(box, "1", _msg())
    client.ingest(home, box, agent="a")
    n.poll()
    n.flush()
    assert _sources_sent(theirs) == [], "silenced mail reached the session"
    silenced[0] = False
    n.poll()
    n.flush()
    assert _sources_sent(theirs) == ["amail"]
    for _ in range(3):
        n.poll()
        n.flush()
    assert _sources_sent(theirs) == [], "a told channel was told again every pass"



# --- MIS-0004 R29, R39, R40: the keystroke fallback types only on positive evidence ---------------
import json as _json

from test_pd_wake import ID1, FakePane, _waker, screen
from macf.pd import wake as _wk


def _turns(*records):
    return [_json.dumps(r) for r in records]


ASSISTANT_DONE = {"type": "assistant", "message": {"role": "assistant", "stop_reason": "end_turn",
                                                    "content": [{"type": "text", "text": "done"}]}}
ASSISTANT_TOOL = {"type": "assistant", "message": {"role": "assistant", "stop_reason": "tool_use",
                                                    "content": [{"type": "tool_use", "name": "Bash"}]}}
USER_PROMPT = {"type": "user", "message": {"role": "user", "content": "next please"}}
INTERRUPT = {"type": "user", "message": {"role": "user", "content": [
    {"type": "text", "text": "[Request interrupted by user]"}]}}
LOCAL_CMD = {"type": "user", "message": {"role": "user",
                                         "content": "<command-name>/mcp</command-name>"}}
LOCAL_OUT = {"type": "user", "message": {"role": "user",
                                         "content": "<local-command-stdout>ok</local-command-stdout>"}}


def test_turn_end_is_read_from_the_last_meaningful_record():
    assert _wk.turn_ended(_turns(USER_PROMPT, ASSISTANT_DONE)) is True
    assert _wk.turn_ended(_turns(ASSISTANT_DONE, USER_PROMPT)) is False
    assert _wk.turn_ended(_turns(USER_PROMPT, ASSISTANT_TOOL)) is False
    # The prototype's two gaps: an interrupt record and local-command records are skipped, not
    # read as an open turn (they failed safe, holding the gate until a person typed).
    assert _wk.turn_ended(_turns(ASSISTANT_DONE, INTERRUPT)) is True
    assert _wk.turn_ended(_turns(ASSISTANT_DONE, LOCAL_CMD, LOCAL_OUT)) is True
    # A /context or a ! command at an idle prompt writes meta and shell records, not a turn (CTB on #925).
    meta = {"type": "user", "isMeta": True, "message": {"role": "user", "content": "<local-command-caveat>x</local-command-caveat>"}}
    bash_in = {"type": "user", "message": {"role": "user", "content": "<bash-input>ls</bash-input>"}}
    bash_out = {"type": "user", "message": {"role": "user", "content": "<bash-stdout>a</bash-stdout>"}}
    assert _wk.turn_ended(_turns(ASSISTANT_DONE, meta, bash_in, bash_out)) is True
    # A channel message is isMeta too, but it starts a turn: the gate must stay shut (CTB on #925).
    channel = {"type": "user", "isMeta": True, "message": {"role": "user", "content": '<channel source="telegram" chat_id="1">hi</channel>'}}
    assert _wk.turn_ended(_turns(ASSISTANT_DONE, channel)) is False
    # Nothing readable is never evidence of an ended turn.
    assert _wk.turn_ended([]) is None and _wk.turn_ended(["not json"]) is None


@pytest.mark.parametrize("waiting, ended, typed", [
    (None, True, True),          # all three signals: type
    ("a permission prompt", True, False),
    (None, False, False),
    (None, None, False),         # transcript unreadable: fail closed
])
def test_keystrokes_need_idle_prompt(waiting, ended, typed):
    """R29: an empty box alone is not enough; no person may be waited on and the last turn must
    have ended. Each single-signal false type of the macOS catalog is a planted case here."""
    pane, events = FakePane([screen()]), []
    w = _waker(pane, events, waiting_on=lambda: waiting, turn_ended=lambda: ended).waker
    assert (w.tick([ID1]) == "sent") is typed
    assert bool(pane.typed) is typed
    if not typed:
        assert events and events[-1][0] == _wk.EVENT_HELD


def test_keystrokes_read_back():
    """R39: text and return go separately, the box is read back, and Enter is retried only while
    the box still holds the notice."""
    text = _wk.wake_text([ID1])
    pane, events = FakePane([screen(), screen(box=text), screen(box=text), screen(above=("✻ Thinking…",))]), []
    h = _waker(pane, events, waiting_on=lambda: None, turn_ended=lambda: True)
    assert h.waker.tick([ID1]) == "sent"
    assert pane.log[:2] == ["record", "type"] and pane.enters == 0, "the text goes alone, first"
    for _ in range(3):
        h.clock[0] += 5
        h.waker.tick([ID1])
    assert 1 <= pane.enters <= 2, "Enter only while the notice is still in the box"


def test_keystroke_notice_no_leading_digit():
    """R40: a survey bar reads as an empty box and a digit answers it, so no notice may begin with one."""
    assert not _wk.wake_text([ID1])[0].isdigit()
    pane, events = FakePane([screen()]), []
    w = _waker(pane, events, waiting_on=lambda: None, turn_ended=lambda: True).waker
    assert w.type_notice("1 mail waiting") is False and not pane.typed
    assert events[-1][0] == _wk.EVENT_HELD and "digit" in events[-1][1]["reason"]


def test_the_newest_transcript_of_the_project_is_read(tmp_path):
    import os
    proj = tmp_path / "work" / "proj"
    folder = tmp_path / ".claude" / "projects" / str(proj).replace("/", "-").replace("_", "-")
    folder.mkdir(parents=True)
    old, new = folder / "a.jsonl", folder / "b.jsonl"
    old.write_text("\n".join(_turns(ASSISTANT_DONE)) + "\n")
    new.write_text("\n".join(_turns(ASSISTANT_DONE, USER_PROMPT)) + "\n")
    os.utime(old, (1, 1))
    found = _wk.latest_transcript(proj, claude_home=tmp_path / ".claude")
    assert found == new and _wk.transcript_turn_ended(found) is False
    assert _wk.latest_transcript(tmp_path / "nowhere", claude_home=tmp_path / ".claude") is None
    assert _wk.transcript_turn_ended(None) is None


def test_an_adopted_sessions_own_transcript_is_read_not_the_newest(tmp_path):
    """A second session in the same project writes the newer file; the gate reads the adopted
    session's own, by its id, and a missing one is no evidence at all (CTB on #925)."""
    import os
    proj = tmp_path / "proj"
    folder = tmp_path / ".claude" / "projects" / str(proj).replace("/", "-").replace("_", "-")
    folder.mkdir(parents=True)
    own, other = folder / "3d52b89a-eeee.jsonl", folder / "ffff0000-1111.jsonl"
    own.write_text("\n".join(_turns(ASSISTANT_DONE, USER_PROMPT)) + "\n")
    other.write_text("\n".join(_turns(ASSISTANT_DONE)) + "\n")
    os.utime(own, (1, 1))
    home = tmp_path / ".claude"
    assert _wk.latest_transcript(proj, claude_home=home) == other
    assert _wk.latest_transcript(proj, claude_home=home, session_id="3d52b89a-eeee") == own
    assert _wk.latest_transcript(proj, claude_home=home, session_id="00000000-gone") is None


def test_the_core_names_the_session_waiting_and_its_transcript(tmp_path):
    from types import SimpleNamespace as NS
    from macf.pd.core import Core
    core = Core.__new__(Core)
    core._placeholders = {"agent_home": str(tmp_path)}
    sess = NS(spec=NS(kind="session", command=["py", "-m", "x", "--project-dir", "{agent_home}/proj"]),
              state="running", client_session=None)
    core._units = {"session": sess, "monitor": NS(spec=NS(kind="service", command=[]), state="running")}
    assert core.session_waiting_on() is None
    folder = tmp_path / ".claude" / "projects" / str(tmp_path / "proj").replace("/", "-").replace("_", "-")
    folder.mkdir(parents=True)
    (folder / "aaaa.jsonl").write_text("{}\n")
    (folder / "bbbb.jsonl").write_text("{}\n")
    import os
    os.utime(folder / "bbbb.jsonl", (1, 1))
    home = tmp_path / ".claude"
    # The project directory comes from Core's own lookup, the rendered --project-dir.
    assert core.session_transcript(claude_home=home) == folder / "aaaa.jsonl"
    sess.client_session = "bbbb"            # adopted: its own transcript, though older
    assert core.session_transcript(claude_home=home) == folder / "bbbb.jsonl"
    sess.state = "waiting_on_a_person"
    assert core.session_waiting_on() == "a person"
