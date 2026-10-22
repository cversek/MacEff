"""The notifier in the primal daemon: notices held while they can't be delivered, and
written to the MacEff channel as closed records (MIS-0002 step 2, notices)."""
import json
import os
import socket
import time
from dataclasses import dataclass

import pytest

from macf.agent_events_log import read_events
from macf.channels.maceff_channel import TAKES, build_event, parse_record
from macf.notify.session import proc_start
from macf.pd import notifier as nt
from channel_receiver import ChannelReceiver
from test_primal_daemon import base, make_home, run_daemon  # noqa: F401 - fixtures


@pytest.fixture(autouse=True)
def _mail_box_from_the_home(monkeypatch):
    """These tests put mail in <home>/amail/pickup, the box chosen when nothing names one.
    Inside a seat MACEFF_AGENT_NAME is set, which would point the daemon elsewhere."""
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    monkeypatch.delenv("MACF_AMAIL_HANDOFF", raising=False)


def _box(home):
    box = home / "amail" / "pickup"
    box.mkdir(parents=True, exist_ok=True)
    return box


def _mail(home, name):
    (_box(home) / f"{name}.amsg").write_text("never read by the notifier")


def _home(tmp_path):
    home = tmp_path / "agent"
    _box(home)
    return home


def _pair():
    """A connected pair standing in for the daemon's end and the channel's end."""
    ours, theirs = socket.socketpair()
    theirs.settimeout(2)
    return ours, theirs


def _records(conn):
    data = b""
    try:
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
            if data.endswith(b"\n"):
                conn.settimeout(0.2)
    except socket.timeout:
        pass
    return [parse_record(line) for line in data.decode().splitlines()]


def _logged(name):
    return [e["data"] for e in read_events(reverse=False, scope="all") if e.get("event") == name]


def test_source_named(tmp_path, isolated_events_log):
    """Each notice names its source, in the record and in the event the channel builds (R38)."""
    home = _home(tmp_path)
    n = nt.Notifier(home, {"amail": "agent"})
    n.boot()
    _mail(home, "m1")
    n.poll()
    ours, theirs = _pair()
    n.attach(ours, takes=TAKES)
    assert n.flush() == 1
    (record,) = _records(theirs)
    assert record.source == "amail"
    assert build_event(record)["params"]["meta"]["notice_source"] == "amail"


def test_three_times(tmp_path, isolated_events_log):
    """The record carries when the store was read and when it was sent; the channel adds
    when it was received (R39). A notice held for a while shows the wait between them."""
    clock = [1000.0]
    home = _home(tmp_path)
    n = nt.Notifier(home, {"amail": "agent"}, clock=lambda: clock[0])
    n.boot()
    _mail(home, "m1")
    n.poll()
    clock[0] = 1300.0
    ours, theirs = _pair()
    n.attach(ours, takes=TAKES)
    n.flush()
    (record,) = _records(theirs)
    assert (record.read_at, record.sent_at) == (1000.0, 1300.0)
    meta = build_event(record)["params"]["meta"]
    assert (meta["read_at"], meta["sent_at"]) == ("1000.000", "1300.000")
    delivered = _logged(nt.EVENT_DELIVERED)
    assert delivered and delivered[-1]["read_at"] == 1000.0 and delivered[-1]["sent_at"] == 1300.0


def test_held_while_down(tmp_path, isolated_events_log):
    """A notice with no channel to take it is held, through a daemon restart, and goes out
    once a channel attaches. Mail that arrived while no daemon ran is announced once at the
    next start, not primed away (R41)."""
    home = _home(tmp_path)
    first = nt.Notifier(home, {"amail": "agent"})
    first.boot()
    _mail(home, "m1")
    first.poll()
    assert list(first.owed) and first.flush() == 0          # no channel: held

    _mail(home, "m2")                                        # arrives while no daemon runs
    second = nt.Notifier(home, {"amail": "agent"})           # the restarted daemon's
    second.boot()
    assert len(second.owed) == 2, "the held notice and the one for mail waiting at start"
    ours, theirs = _pair()
    second.attach(ours, takes=TAKES)
    assert second.flush() == 2
    assert [r.count for r in _records(theirs)] == [1, 2]

    third = nt.Notifier(home, {"amail": "agent"})            # and once delivered, never again
    third.boot()
    assert not third.owed


def test_routing_declared(tmp_path, isolated_events_log, capsys):
    """Only a source routed to the agent is polled for the session; one routed to the
    operator alone is not, and a declared source with no poller is said, not ignored (R42)."""
    home = _home(tmp_path)
    assert [s.name for s in nt.Notifier(home, {"amail": "both"}).sources] == ["amail"]
    assert nt.Notifier(home, {"amail": "operator"}).sources == []
    assert nt.Notifier(home, {"weather": "agent"}).sources == []
    assert "'weather' is declared but this daemon has no poller" in capsys.readouterr().err


def _operator_heard(home, log, routes):
    """The operator's share, as the outside watch serves it: the watch's findings about this
    home's mail, read from the agent's own event log (*log*) under *routes*."""
    import shutil
    from macf.pd import watch
    from macf.pd.interface import Declaration, declaration_path
    declaration_path(home).write_text(Declaration(
        version=1, agent="Tester@abc123", unread_mail_threshold_s=600,
        notice_routes=routes).model_dump_json())
    if log.exists():
        shutil.copy(log, home / ".maceff" / "agent_events_log.jsonl")
    return [f.verdict for f in watch.check_home(home, time.time(), probe=None) if f.subject == "mail"]


@pytest.mark.parametrize("route", ["agent", "operator", "both"])
def test_each_route_reaches_its_audience_and_no_other(tmp_path, isolated_events_log, route):
    """R42: a source routed to the agent, or to both, reaches the agent's channel, a store's
    source and one the daemon raises alike; a source routed to the operator alone does not.
    The operator's share, the outside watch's alert, is given where the route is the
    operator's or both, and not where it is the agent's alone. Only unread mail may be routed
    to the operator alone (the repo owner's ruling of 2026-10-21), so in that case the other
    sources go to the agent and unread mail must reach the operator and not the agent."""
    from macf.agent_events_log import append_event
    from macf.pd.interface import EVENT_UNREAD_MAIL
    home = make_home(tmp_path, [])
    _box(home)
    others = "agent" if route == "operator" else route
    routes = {"amail": others, "pd_limit_exceeded": others, "pd_unread_mail": route}
    n = nt.Notifier(home, routes)
    n.boot()
    _mail(home, "m1")
    n.poll()
    n.raise_notice("pd_limit_exceeded", "limit-worker-1")
    n.raise_notice("pd_unread_mail", "unread-mail-1")
    append_event(EVENT_UNREAD_MAIL, {"agent": "Tester@abc123", "count": 1, "reason": "1 message(s) unread"})
    ours, theirs = _pair()
    n.attach(ours, takes=TAKES)
    n.flush()
    to_agent = sorted(r.source for r in _records(theirs))
    assert to_agent == sorted(s for s, r in routes.items() if r in ("agent", "both"))
    to_operator = _operator_heard(home, isolated_events_log, routes)
    assert to_operator == (["UNREAD"] if route in ("operator", "both") else [])


def test_a_route_outside_the_declared_ones_is_refused_at_load():
    """R42: a declaration names one of the routes for each source it routes, and a source the
    daemon must notice on (unread mail past a threshold) cannot be left unrouted."""
    from macf.pd.interface import Declaration
    with pytest.raises(ValueError):
        Declaration(version=1, agent="Tester@abc123", notice_routes={"amail": "nobody"})
    with pytest.raises(ValueError, match="pd_unread_mail"):
        Declaration(version=1, agent="Tester@abc123", unread_mail_threshold_s=600,
                    notice_routes={"amail": "agent"})


def test_nothing_is_sent_for_no_change(tmp_path, isolated_events_log):
    """Polls that find nothing new produce nothing to send (R46)."""
    home = _home(tmp_path)
    _mail(home, "old")
    n = nt.Notifier(home, {"amail": "agent"})
    n.boot()
    ours, theirs = _pair()
    n.attach(ours, takes=TAKES)
    n.flush()
    _records(theirs)
    for _ in range(5):
        n.poll()
    assert n.flush() == 0


def test_a_channel_that_went_away_keeps_the_notice_owed(tmp_path, isolated_events_log):
    home = _home(tmp_path)
    n = nt.Notifier(home, {"amail": "agent"})
    n.boot()
    _mail(home, "m1")
    n.poll()
    ours, theirs = _pair()
    theirs.close()
    n.attach(ours, takes=TAKES)
    assert n.flush() == 0 and len(n.owed) == 1 and not n.channels


# --- the daemon: who may attach --------------------------------------------------

def _declare_routes(home):
    from macf.pd.interface import declaration_path
    path = declaration_path(home)
    decl = json.loads(path.read_text())
    decl["notice_routes"] = {"amail": "agent"}
    path.write_text(json.dumps(decl))


def _connect(daemon, takes=None):
    """A channel's connection to the running daemon; with ``takes``, it sends that hello."""
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(3)
    conn.connect(str(daemon.channel_path))
    if takes is not None:
        conn.sendall(json.dumps({"hello": {"takes": list(takes)}}).encode() + b"\n")
    return conn


def test_peer_lineage_checked_by_the_daemon(tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """The daemon attaches a channel only below the session unit's live process, and refuses
    one when no session runs; a refused channel's notice stays owed (MIS-0002-R122)."""
    home = make_home(tmp_path, [])
    _declare_routes(home)
    _mail(home, "m1")
    daemon = run_daemon(home, base)
    assert daemon.channel_path.exists() and oct(daemon.channel_path.stat().st_mode)[-3:] == "600"

    refused = _connect(daemon)                               # no session unit runs
    assert refused.recv(1) == b"", "a channel was attached with no session to descend from"
    assert len(daemon.notifier.owed) == 1

    me = (os.getpid(), proc_start(os.getpid()))              # this test stands in for the session
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: me)
    conn = _connect(daemon, takes=TAKES)
    (record,) = _records(conn)
    assert record.source == "amail" and record.count == 1
    deadline = time.monotonic() + 3
    while daemon.notifier.owed and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not daemon.notifier.owed


# ---- R149: the channel declares its sources at attach; the rest is held ---------------

ENTRY_ID = "e-0123456789ab"


def _owe_an_entry(home):
    """Mail in the box and an entry's notice owed in the log, both read back at the daemon's boot,
    so nothing is raised from the test's thread while the serve loop runs."""
    from macf.agent_events_log import append_event
    _declare_routes(home)
    _mail(home, "m1")
    append_event(nt.EVENT_DETECTED, {"source": "pd_entry_due", "arrival_id": ENTRY_ID, "count": None,
                                     "store": "the event log", "notifier": nt.NOTIFIER})


def _session_is_this_test(daemon, monkeypatch):
    me = (os.getpid(), proc_start(os.getpid()))
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: me)


def _until(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.05)
    return condition()


def _entry_owed(daemon):
    return ENTRY_ID in daemon.notifier.owed


def test_a_source_the_attached_channel_did_not_declare_stays_held(tmp_path, base, run_daemon,
                                                                 isolated_events_log, monkeypatch):
    """MIS-0002-R149: a channel whose hello leaves out ``pd_entry_due`` is sent the mail it
    declared and not the entry's notice, which stays owed, never logged delivered; a second
    channel that declares it then receives it. The daemon records what each channel declared."""
    home = make_home(tmp_path, [])
    _owe_an_entry(home)
    daemon = run_daemon(home, base)
    _session_is_this_test(daemon, monkeypatch)
    partial = [s for s in TAKES if s != "pd_entry_due"]
    old = _connect(daemon, takes=partial)
    assert [r.source for r in _records(old)] == ["amail"]
    time.sleep(0.3)                                       # a notice sent in error has time to show
    assert _entry_owed(daemon), "an undeclared source's notice was not held"
    assert not [d for d in _logged(nt.EVENT_DELIVERED) if d["arrival_id"] == ENTRY_ID]

    new = _connect(daemon, takes=TAKES)
    assert [(r.source, r.arrival_id) for r in _records(new)] == [("pd_entry_due", ENTRY_ID)]
    assert _until(lambda: not _entry_owed(daemon))
    declared = _logged("pd_channel_declared")
    assert [sorted(d["takes"]) for d in declared] == [sorted(partial), sorted(TAKES)]
    old.close()
    new.close()


def test_a_channel_that_sends_no_hello_is_sent_nothing(tmp_path, base, run_daemon, isolated_events_log,
                                                       monkeypatch):
    """A channel that sends no hello declares nothing: it stays attached, past its hello's time,
    and is sent nothing, so every notice stays owed for a channel that declares it."""
    from macf.pd import daemon as dm
    monkeypatch.setattr(dm, "HELLO_TIMEOUT_S", 0.3)
    home = make_home(tmp_path, [])
    _owe_an_entry(home)
    daemon = run_daemon(home, base)
    _session_is_this_test(daemon, monkeypatch)
    silent = _connect(daemon)
    assert _until(lambda: daemon.notifier.channels)
    silent.settimeout(1.0)
    with pytest.raises(socket.timeout):
        silent.recv(1)                                    # neither a record nor a close
    assert daemon.notifier.channels, "a channel with no hello was dropped"
    assert len(daemon.notifier.owed) == 2
    assert not _logged(nt.EVENT_DELIVERED) and not _logged("pd_channel_declared")
    silent.close()


@pytest.mark.parametrize("hello", [
    b"not json\n",
    b'{"hello": {"takes": "amail"}}\n',                       # not a list
    b'{"hello": {"takes": ["amail"], "also": 1}}\n',          # an extra field
    b'{"hello": {"takes": ["amail; rm -rf ~"]}}\n',           # not a source's name
    b'{"hello": {"takes": ["amail"]}}\n{"more": 1}\n',        # a write after the hello
    b'{"hello": {"takes": ["am',                              # never finished, then its time runs out
])
def test_a_malformed_hello_detaches_the_channel(tmp_path, base, run_daemon, isolated_events_log, monkeypatch,
                                                hello):
    """A malformed hello, an unfinished one, or a write after it breaks the protocol: the daemon
    drops the channel, and what was owed stays owed."""
    from macf.pd import daemon as dm
    monkeypatch.setattr(dm, "HELLO_TIMEOUT_S", 0.3)
    home = make_home(tmp_path, [])
    _owe_an_entry(home)
    daemon = run_daemon(home, base)
    _session_is_this_test(daemon, monkeypatch)
    conn = _connect(daemon)
    conn.sendall(hello)
    assert conn.recv(1) == b"", "a channel that broke the protocol was kept"
    assert _until(lambda: not daemon.notifier.channels)
    assert len(daemon.notifier.owed) == 2
    conn.close()


def test_the_maceff_channel_declares_every_source_its_record_takes(tmp_path, base, run_daemon,
                                                                   isolated_events_log, monkeypatch):
    """The real channel, against the real daemon: its hello declares exactly the sources its
    record accepts, so an entry's notice reaches it."""
    import typing

    from macf.channels.maceff_channel import Channel, NoticeRecord
    home = make_home(tmp_path, [])
    _owe_an_entry(home)
    daemon = run_daemon(home, base)
    _session_is_this_test(daemon, monkeypatch)
    conn = Channel(daemon.card, base=base, out=None).connect_once()
    assert conn is not None
    conn.settimeout(3)
    assert sorted(r.source for r in _records(conn)) == ["amail", "pd_entry_due"]
    (declared,) = _logged("pd_channel_declared")
    assert set(declared["takes"]) == set(typing.get_args(NoticeRecord.model_fields["source"].annotation))
    conn.close()


def test_daemon_releases_the_channel_socket(tmp_path, base, isolated_events_log):
    from macf.pd.daemon import Daemon
    home = make_home(tmp_path, [])
    daemon = Daemon(home, base=base)
    daemon.start()
    daemon.stop()
    daemon.serve()
    assert not daemon.channel_path.exists()


def test_a_unit_past_its_limit_is_a_notice_held_and_delivered(tmp_path, isolated_events_log):
    """MIS-0002-R60: the daemon's own over-limit notice is owed to the agent, by its declared
    route or, unrouted, by default (R42, the ruling of 2026-10-21), held through a restart like
    mail's (R41), and arrives on the channel as the never-masked pd_limit_exceeded notice."""
    home = _home(tmp_path)
    unrouted = nt.Notifier(home, {"amail": "agent"})
    assert unrouted.raise_notice("pd_limit_exceeded", "limit-worker-1") is True
    assert list(unrouted.owed)
    first = nt.Notifier(home, {"pd_limit_exceeded": "agent"})
    first.boot()
    assert first.raise_notice("pd_limit_exceeded", "limit-worker-2") is True
    assert first.flush() == 0                                # no channel: held
    second = nt.Notifier(home, {"pd_limit_exceeded": "agent"})   # the restarted daemon's
    second.boot()
    assert list(second.owed) == ["limit-worker-1", "limit-worker-2"]   # both held across the restart
    ours, theirs = _pair()
    second.attach(ours, takes=TAKES)
    assert second.flush() == 2
    record = _records(theirs)[-1]
    assert record.source == "pd_limit_exceeded" and record.count is None
    assert "macf-daemon" in build_event(record)["params"]["content"]
    with pytest.raises(ValueError):
        second.raise_notice("amail", "not-raised-by-the-daemon")


# ---------------------------------------------------------------- unread mail (MIS-0002-R55)

class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@dataclass(frozen=True)
class _Rig:
    """A tracker, the events it wrote, the notices it raised, and the clock it reads."""
    tracker: object
    said: list
    notices: list
    clock: _Clock


def _unread(home, threshold=600.0, now=10_000.0, events=()) -> _Rig:
    from macf.pd.unread_mail import UnreadMail, pickup_box
    said, notices, clock = [], [], _Clock(now)
    tracker = UnreadMail("Resident@1a2b3c", threshold, pickup_box(home),
                         lambda source, nid: notices.append((source, nid)),
                         append=lambda e, d: said.append((e, d)) or True, wall=clock,
                         events=lambda: list(events))
    tracker.boot()
    return _Rig(tracker, said, notices, clock)


def _arrive(home, name, at):
    _mail(home, name)
    os.utime(_box(home) / f"{name}.amsg", (at, at))


def test_unread_mail_notice(tmp_path):
    """R55: one notice per unread spell, however many messages arrive in it; a read box and
    a new arrival past the threshold is a second spell; mail read in time gives none."""
    from macf.pd.interface import EVENT_UNREAD_MAIL, EVENT_UNREAD_MAIL_CLEARED
    home = _home(tmp_path)
    r = _unread(home)
    tracker, said, notices, clock = r.tracker, r.said, r.notices, r.clock
    # a spell with three arrivals: one notice
    _arrive(home, "a", 10_000)
    tracker.tick(0.0)
    assert notices == []                                  # not yet past the threshold
    _arrive(home, "b", 10_100)
    clock.now = 10_700
    tracker.tick(0.0)
    _arrive(home, "c", 10_800)
    clock.now = 12_000
    tracker.tick(0.0)
    assert len(notices) == 1 and notices[0][0] == "pd_unread_mail"
    assert [e for e, _ in said] == [EVENT_UNREAD_MAIL]
    assert said[0][1]["count"] == 2 and said[0][1]["agent"] == "Resident@1a2b3c"
    # read, then a new arrival past the threshold: a second spell, a second notice
    for name in "abc":
        (_box(home) / f"{name}.amsg").unlink()
    tracker.tick(0.0)
    assert [e for e, _ in said] == [EVENT_UNREAD_MAIL, EVENT_UNREAD_MAIL_CLEARED]
    _arrive(home, "d", 12_100)
    clock.now = 12_800
    tracker.tick(0.0)
    assert len(notices) == 2
    # mail read before the threshold: no notice, and no spell to clear
    (_box(home) / "d.amsg").unlink()
    tracker.tick(0.0)
    _arrive(home, "e", 13_000)
    clock.now = 13_300
    tracker.tick(0.0)
    (_box(home) / "e.amsg").unlink()
    tracker.tick(0.0)
    assert len(notices) == 2
    assert [e for e, _ in said].count(EVENT_UNREAD_MAIL) == 2


@pytest.mark.parametrize("route", ["agent", "operator", "both"])
def test_unread_mail_reaches_the_routes_declared_for_it(tmp_path, base, run_daemon, isolated_events_log,
                                                        route):
    """R55, end to end: a running daemon with a threshold notices mail left unread, and the
    notice reaches the routes declared for it and no other. The agent's share is the notice
    owed on its channel; the operator's is the outside watch's alert, read from the same log."""
    from macf.pd.interface import Declaration, EVENT_UNREAD_MAIL, declaration_path
    home = make_home(tmp_path, [])
    routes = {"pd_unread_mail": route}
    declaration_path(home).write_text(Declaration(
        version=1, agent="Tester@abc123", unread_mail_threshold_s=0.2,
        notice_routes=routes).model_dump_json())
    _mail(home, "waiting")
    daemon = run_daemon(home, base)
    to_agent = route in ("agent", "both")
    deadline = time.time() + 5
    while time.time() < deadline and not (
            list(read_events(only=(EVENT_UNREAD_MAIL,)))
            and (not to_agent or any(o.source == "pd_unread_mail" for o in daemon.notifier.owed.values()))):
        time.sleep(0.1)                                   # the serve loop ticks on its own
    time.sleep(0.3)                                       # a notice owed in error has time to show
    [event] = list(read_events(only=(EVENT_UNREAD_MAIL,)))
    assert event["data"]["agent"] == "Tester@abc123"
    assert any(o.source == "pd_unread_mail" for o in daemon.notifier.owed.values()) == to_agent
    to_operator = _operator_heard(home, isolated_events_log, routes)
    assert to_operator == (["UNREAD"] if route in ("operator", "both") else [])


def test_unread_mail_counts_only_the_time_the_session_ran(tmp_path):
    """A wait counts from arrival or the running session's start, whichever is later, and
    nothing is noticed while the declared session is down: an agent that wasn't there to
    read hasn't left its mail unread (the storm amail.alerting records)."""
    home = _home(tmp_path)
    r = _unread(home)
    tracker, said, notices, clock = r.tracker, r.said, r.notices, r.clock
    _arrive(home, "a", 1_000)                             # long before the session started
    clock.now = 10_000
    tracker.tick(None)                                    # the session isn't running
    assert notices == []
    tracker.tick(9_800)                                   # it started 200 s ago
    assert notices == []
    clock.now = 10_500                                    # 700 s of the session's own time
    tracker.tick(9_800)
    assert len(notices) == 1


def test_an_agent_without_a_session_counts_on_the_wall_clock(tmp_path):
    from macf.pd.unread_mail import ALWAYS_ACTIVE
    home = _home(tmp_path)
    r = _unread(home)
    tracker, said, notices, clock = r.tracker, r.said, r.notices, r.clock
    _arrive(home, "a", 9_000)
    tracker.tick(ALWAYS_ACTIVE)
    assert len(notices) == 1


def test_a_restarted_daemon_does_not_notice_an_open_spell_again(tmp_path):
    from macf.pd.interface import EVENT_UNREAD_MAIL, EVENT_UNREAD_MAIL_CLEARED
    home = _home(tmp_path)
    _arrive(home, "a", 1_000)
    opened = [{"event": EVENT_UNREAD_MAIL, "data": {"agent": "Other@000000"}},
              {"event": EVENT_UNREAD_MAIL, "data": {"agent": "Resident@1a2b3c"}}]
    r = _unread(home, events=opened)
    tracker, said, notices, clock = r.tracker, r.said, r.notices, r.clock
    tracker.tick(0.0)
    assert notices == [] and said == []
    closed = [{"event": EVENT_UNREAD_MAIL_CLEARED, "data": {"agent": "Resident@1a2b3c"}},
              {"event": EVENT_UNREAD_MAIL, "data": {"agent": "Resident@1a2b3c"}}]
    r = _unread(home, events=closed)
    tracker, said, notices, clock = r.tracker, r.said, r.notices, r.clock
    tracker.tick(0.0)
    assert len(notices) == 1


def test_an_unreadable_box_is_not_an_empty_one(tmp_path, monkeypatch):
    """A box that can't be read neither opens nor closes a spell."""
    from macf.pd import unread_mail
    home = _home(tmp_path)
    r = _unread(home)
    tracker, said, notices, clock = r.tracker, r.said, r.notices, r.clock
    _arrive(home, "a", 1_000)
    tracker.tick(0.0)
    assert len(notices) == 1
    monkeypatch.setattr(unread_mail, "unread_arrivals", lambda box: None)
    tracker.tick(0.0)
    assert [e for e, _ in said] == ["pd_unread_mail"]


def test_no_notice_goes_out_without_its_record(tmp_path):
    """A spell opens in the log first: an event that fails to record raises no notice and
    leaves the spell closed, to be tried again, so a restart never notices it twice and the
    operator's watch, which reads only the log, never misses one (host-side maintainer)."""
    home = _home(tmp_path)
    r = _unread(home)
    _arrive(home, "a", 1_000)
    log_ok = [False]
    r.tracker.append = lambda e, d: log_ok[0] and (r.said.append((e, d)) or True)
    r.tracker.tick(0.0)
    assert r.notices == [] and r.tracker.in_spell is False
    log_ok[0] = True
    r.tracker.tick(0.0)
    assert len(r.notices) == 1 and r.tracker.in_spell is True
    # and a clearing that fails to record leaves the spell open, as the log still says
    (_box(home) / "a.amsg").unlink()
    log_ok[0] = False
    r.tracker.tick(0.0)
    assert r.tracker.in_spell is True
    log_ok[0] = True
    r.tracker.tick(0.0)
    assert r.tracker.in_spell is False and r.said[-1][0] == "pd_unread_mail_cleared"


def test_the_oldest_entry_is_named(tmp_path):
    """An entry `amail list` can't take in stays in the box and holds the spell open; the
    event and its reason name the oldest, so a person can find it."""
    home = _home(tmp_path)
    r = _unread(home)
    _arrive(home, "newer", 1_500)
    _arrive(home, "stuck", 1_000)
    r.tracker.tick(0.0)
    data = r.said[0][1]
    assert data["oldest"] == "stuck.amsg" and "stuck.amsg" in data["reason"]


def test_a_threshold_must_be_routed(tmp_path):
    from macf.pd.interface import Declaration
    with pytest.raises(ValueError, match="pd_unread_mail"):
        Declaration(version=1, agent="Resident@1a2b3c", unread_mail_threshold_s=600)
    d = Declaration(version=1, agent="Resident@1a2b3c", unread_mail_threshold_s=600,
                    notice_routes={"pd_unread_mail": "both"})
    assert d.unread_mail_threshold_s == 600


def test_the_unread_mail_notice_is_held_and_delivered_to_the_agent(tmp_path, isolated_events_log):
    home = _home(tmp_path)
    notifier = nt.Notifier(home, {"pd_unread_mail": "agent"})
    notifier.boot()
    assert notifier.raise_notice("pd_unread_mail", "unread-mail-1") is True
    ours, theirs = _pair()
    notifier.attach(ours, takes=TAKES)
    assert notifier.flush() == 1
    [record] = _records(theirs)
    assert record.source == "pd_unread_mail"
    operator_only = nt.Notifier(home, {"pd_unread_mail": "operator"})
    assert operator_only.raise_notice("pd_unread_mail", "unread-mail-2") is False


def test_a_daemon_with_a_threshold_notices_unread_mail(tmp_path, base, run_daemon, isolated_events_log):
    """End to end: the declaration's threshold builds the tracker, the serve loop ticks it,
    and an agent with no session unit counts on the wall clock."""
    from macf.pd.interface import Declaration, EVENT_UNREAD_MAIL, declaration_path
    home = make_home(tmp_path, [])
    declaration_path(home).write_text(Declaration(
        version=1, agent="Tester@abc123", unread_mail_threshold_s=0.2,
        notice_routes={"pd_unread_mail": "agent"}).model_dump_json())
    _mail(home, "waiting")
    daemon = run_daemon(home, base)
    assert daemon.unread_mail is not None and daemon.core.session_active_since() == float("-inf")
    deadline = time.time() + 5
    while time.time() < deadline and not list(read_events(only=(EVENT_UNREAD_MAIL,))):
        time.sleep(0.1)                                   # the serve loop ticks on its own
    [event] = list(read_events(only=(EVENT_UNREAD_MAIL,)))
    assert event["data"]["agent"] == "Tester@abc123" and event["data"]["count"] == 1
    assert any(o.source == "pd_unread_mail" for o in daemon.notifier.owed.values())


from test_primal_daemon import _crash, drive, make_core, make_unit, script  # noqa: E402,F401 - fixtures


def test_after_restart_notice(make_core, script, tmp_path):
    """MIS-0002-R47 (pd_MUST_report_carried_changed_lost): after a restart and after a
    compaction, one pd_carried event says what was carried, what changed and what was lost,
    and the agent is owed one notice pointing to it, which arrives through the MacEff
    channel's own record (#734). A first start carries nothing and says nothing. Here a unit that survived the daemon is carried, one that died is started anew
    (changed), and an optional one that died isn't started again (lost)."""
    from macf.agent_events_log import append_event
    from macf.pd import core as pd_core

    def carried_events():
        return [e["data"] for e in read_events(reverse=False, scope="all", only=(pd_core.EVENT_CARRIED,))]

    # The survivor is the session unit, so its restart under the second daemon is checked too.
    survives = make_unit("survives", script, {}, restart="always").model_copy(update={"kind": "session"})
    dies = make_unit("dies", script, {})
    optional = make_unit("optional", script, {}).model_copy(update={"optional": True})
    first = make_core([survives, dies, optional], hosted=lambda: [])
    first.record_start(os.getpid(), "the first daemon's start")
    first.boot()
    first.start("optional", pd_core.POLICY, "the test wants it")
    assert drive(first, lambda: all(first.state(u) == "running" for u in ("survives", "dies", "optional")))
    assert carried_events() == []                                   # a first start is no restart
    left = _crash(first)
    for name in ("dies", "optional"):
        os.killpg(left[name].pid, 9)
        left[name].wait(timeout=5)

    now = [time.time()]
    channel = ChannelReceiver(tmp_path)
    second = make_core([survives, dies, optional], wall=lambda: now[0], hosted=lambda: [])
    second.on_notice = channel

    def owed():
        return [source for source, _ in channel.received]
    second.record_start(os.getpid(), "the second daemon's start")
    second.boot()
    report = carried_events()
    assert len(report) == 1 and report[0]["after"] == "the primal daemon restarted"
    assert (report[0]["carried"], report[0]["changed"], report[0]["lost"]) == (["survives"], ["dies"], ["optional"])
    assert owed() == ["pd_carried"]

    append_event("compaction_detected", {"source": "test"})
    second.tick()
    assert len(carried_events()) == 1                               # the settle lets the follower go first
    now[0] += pd_core.COMPACTION_SETTLE_S + 1
    second.tick()
    after = carried_events()[-1]
    assert after["after"] == "the session was compacted" and after["lost"] == [pd_core.CONTEXT_LOST]
    assert "survives" in after["carried"] and owed() == ["pd_carried", "pd_carried"]
    second.tick()
    assert len(carried_events()) == 2                               # once per compaction

    # The adopted session dies and comes back as a new process: that is a restart too.
    os.killpg(left["survives"].pid, 9)
    left["survives"].wait(timeout=5)
    assert drive(second, lambda: carried_events()[-1]["after"] == "the session unit restarted")
    assert carried_events()[-1]["changed"] == ["survives"] and owed().count("pd_carried") == 3
    # Each id names its occasion, so a daemon restart and a session restart in one second differ.
    assert [i.split("-")[1] for _, i in channel.received] == ["daemon", "compaction", "session"]


def test_a_session_restart_is_reported(make_core, script):
    """R47 for the session unit: when it comes back as a new process, its context is lost and
    the units beside it ran on, and that is reported once, with the notice. Its first start is
    no restart."""
    from macf.pd import core as pd_core
    session = make_unit("session", script, {"exit_after": 0.3}, restart="always").model_copy(
        update={"kind": "session"})
    worker = make_unit("worker", script, {})
    owed = []
    core = make_core([session, worker], hosted=lambda: [])
    core.on_notice = lambda source, nid: owed.append(source)
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    assert drive(core, lambda: any(e["data"]["after"] == "the session unit restarted" for e in
                                   read_events(reverse=False, scope="all", only=(pd_core.EVENT_CARRIED,))))
    first = [e["data"] for e in read_events(reverse=False, scope="all", only=(pd_core.EVENT_CARRIED,))][0]
    assert (first["carried"], first["changed"], first["lost"]) == (["worker"], ["session"], [pd_core.CONTEXT_LOST])
    assert owed[0] == "pd_carried"


@pytest.mark.parametrize("route", ["operator", "held_until_present"])
def test_a_route_that_reaches_nobody_is_refused_at_load(route):
    """R42 and R47, the repo owner's ruling of 2026-10-21 (option A): a declaration may name only
    routes something serves. The operator's route serves unread mail alone, by the outside watch;
    holding until present is served nowhere yet. Anything else is refused, naming the route that
    works, instead of being accepted and dropped."""
    from pydantic import ValidationError
    from macf.pd import interface
    with pytest.raises(ValidationError, match="route it to 'agent'"):
        interface.Declaration(version=1, agent="Tester@abc123", notice_routes={"pd_carried": route})
    interface.Declaration(version=1, agent="Tester@abc123", notice_routes={"pd_carried": "agent"})
    if route != "held_until_present":
        interface.Declaration(version=1, agent="Tester@abc123", notice_routes={"pd_unread_mail": route})


def test_both_keeps_its_agent_half_and_the_rest_is_said(tmp_path, isolated_events_log):
    """CTB on #552: a source routed to `both` is half served, so it loads, its notice reaches the
    agent, and the daemon names it as reaching the agent only. Unread mail's `both` is whole."""
    from macf.pd import interface
    d = interface.Declaration(version=1, agent="Tester@abc123",
                              notice_routes={"pd_run_failed": "both", "pd_unread_mail": "both"})
    assert d.half_served_routes() == ["pd_run_failed"]
    assert nt.Notifier(_home(tmp_path), d.notice_routes).raise_notice("pd_run_failed", "run-1") is True


def test_a_half_served_both_is_said_at_start(tmp_path, capsys):
    """The daemon names a source routed to `both` whose operator half nothing serves, once, at start."""
    import shutil
    import tempfile
    from pathlib import Path
    from macf.pd import interface
    from macf.pd.daemon import Daemon
    home = tmp_path / "home"
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text("abc123def4567890\n")
    (home / ".maceff" / "config.json").write_text('{"agent_identity": {"moniker": "Tester"}}')
    interface.declaration_path(home).write_text(interface.Declaration(
        version=1, agent="Tester@abc123", notice_routes={"pd_run_failed": "both"}).model_dump_json())
    base = Path(tempfile.mkdtemp(prefix="pd-", dir="/tmp"))
    try:
        Daemon(home, base=base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    assert "routes pd_run_failed to 'both', and only the agent's half is served" in capsys.readouterr().err


def test_an_unrouted_carried_notice_reaches_the_agent(tmp_path, isolated_events_log):
    """R47: a declaration rendered with no routes, as the containers' are, still tells the session
    what was carried, changed and lost; the notice goes to the agent by default."""
    notifier = nt.Notifier(_home(tmp_path), {})
    assert notifier.raise_notice("pd_carried", "carried-1") is True
    assert list(notifier.owed)


def test_the_daemon_wires_its_core_and_scheduler_notices_to_its_notifier(tmp_path):
    """R60's subject is the primal daemon: the core's over-limit notice reaches the channel only
    because the daemon connects the core to its notifier. Review on #770 planted that wiring away
    and every other test passed, since they wire it by hand."""
    import shutil
    import tempfile
    from pathlib import Path
    from macf.pd import interface
    from macf.pd.daemon import Daemon
    home = tmp_path / "home"
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text("abc123def4567890\n")
    (home / ".maceff" / "config.json").write_text('{"agent_identity": {"moniker": "Tester"}}')
    interface.declaration_path(home).write_text(
        interface.Declaration(version=1, agent="Tester@abc123").model_dump_json())
    base = Path(tempfile.mkdtemp(prefix="pd-", dir="/tmp"))
    try:
        daemon = Daemon(home, base=base)
        assert daemon.core.on_notice == daemon.notifier.raise_notice
        assert daemon.scheduler.on_notice == daemon.notifier.raise_notice
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_unit_measured_past_its_limit_reaches_the_channel(make_core, script, tmp_path, monkeypatch,
                                                            isolated_events_log):
    """MIS-0002-R60 (pd_MUST_notice_limit_exceeded): the core's own memory reading, not a
    notice raised by hand, owes the notice. A running unit read under its declared limit owes
    nothing; read over it, the core raises pd_limit_exceeded into the notifier, wired as the
    daemon wires it, and the record goes out on the channel."""
    from macf.pd import core as pd_core
    used = [10.0]                                                   # the unit's limit is 64 MB
    monkeypatch.setattr(pd_core, "tree_rss_mb", lambda pid: used[0])
    notifier = nt.Notifier(_home(tmp_path), {"pd_limit_exceeded": "agent"})
    notifier.boot()
    core = make_core([make_unit("worker", script, {})], memory_check_s=0.0)
    core.on_notice = notifier.raise_notice
    core.boot()
    assert drive(core, lambda: core.state("worker") == "running")
    core.tick()
    assert not notifier.owed, "a unit under its limit owed a notice"
    used[0] = 80.0
    core.tick()
    assert [o.source for o in notifier.owed.values()] == ["pd_limit_exceeded"]
    ours, theirs = _pair()
    notifier.attach(ours, takes=TAKES)
    assert notifier.flush() == 1
    [record] = _records(theirs)
    assert record.source == "pd_limit_exceeded"
    [over] = [e["data"] for e in read_events(reverse=False, scope="all", only=(pd_core.EVENT_OVER_LIMIT,))]
    assert (over["unit"], over["used_mb"], over["limit_mb"]) == ("worker", 80.0, 64)


def test_a_compaction_no_daemon_saw_is_reported_at_the_next_start(make_core, script):
    """Review of #714. The tail starts at the log's end, so a compaction made while no daemon
    ran, or inside the settle before a restart, is taken up when the next daemon boots, once its
    settle has passed. One a report already covers isn't reported again."""
    from macf.agent_events_log import append_event
    from macf.pd import core as pd_core

    def reports():
        return [e["data"] for e in read_events(reverse=False, scope="all", only=(pd_core.EVENT_CARRIED,))
                if e["data"].get("occasion") == "compaction"]

    unit = make_unit("worker", script, {})
    append_event("compaction_detected", {"source": "test"})       # while no daemon ran
    now = [time.time()]
    core = make_core([unit], wall=lambda: now[0])
    core.boot()
    core.tick()
    assert reports() == []                                          # the settle still applies
    now[0] += pd_core.COMPACTION_SETTLE_S + 1
    core.tick()
    assert len(reports()) == 1
    core.shutdown("the next daemon starts")

    again = make_core([unit], wall=lambda: now[0])
    again.boot()
    now[0] += pd_core.COMPACTION_SETTLE_S + 1
    again.tick()
    assert len(reports()) == 1                                      # already covered
