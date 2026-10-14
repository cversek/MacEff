"""The notifier in the primal daemon: notices held while they can't be delivered, and
written to the MacEff channel as closed records (MIS-0002 step 2, notices)."""
import json
import os
import socket
import time

import pytest

from macf.agent_events_log import read_events
from macf.channels.maceff_channel import build_event, parse_record
from macf.notify.session import proc_start
from macf.pd import notifier as nt
from test_primal_daemon import base, make_home, run_daemon  # noqa: F401 - fixtures


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
    n.attach(ours)
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
    n.attach(ours)
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
    second.attach(ours)
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


def test_nothing_is_sent_for_no_change(tmp_path, isolated_events_log):
    """Polls that find nothing new produce nothing to send (R46)."""
    home = _home(tmp_path)
    _mail(home, "old")
    n = nt.Notifier(home, {"amail": "agent"})
    n.boot()
    ours, theirs = _pair()
    n.attach(ours)
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
    n.attach(ours)
    assert n.flush() == 0 and len(n.owed) == 1 and not n.channels


# --- the daemon: who may attach --------------------------------------------------

def _declare_routes(home):
    from macf.pd.interface import declaration_path
    path = declaration_path(home)
    decl = json.loads(path.read_text())
    decl["notice_routes"] = {"amail": "agent"}
    path.write_text(json.dumps(decl))


def _connect(daemon):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(3)
    conn.connect(str(daemon.channel_path))
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
    conn = _connect(daemon)
    (record,) = _records(conn)
    assert record.source == "amail" and record.count == 1
    deadline = time.monotonic() + 3
    while daemon.notifier.owed and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not daemon.notifier.owed


def test_daemon_releases_the_channel_socket(tmp_path, base, isolated_events_log):
    from macf.pd.daemon import Daemon
    home = make_home(tmp_path, [])
    daemon = Daemon(home, base=base)
    daemon.start()
    daemon.stop()
    daemon.serve()
    assert not daemon.channel_path.exists()


def test_a_unit_past_its_limit_is_a_notice_held_and_delivered(tmp_path, isolated_events_log):
    """MIS-0002-R60: the daemon's own over-limit notice is owed only where the declaration
    routes it to the agent (R42), held through a restart like mail's (R41), and arrives on
    the channel as the never-masked pd_limit_exceeded notice."""
    home = _home(tmp_path)
    unrouted = nt.Notifier(home, {"amail": "agent"})
    assert unrouted.raise_notice("pd_limit_exceeded", "limit-worker-1") is False
    assert not unrouted.owed
    first = nt.Notifier(home, {"pd_limit_exceeded": "agent"})
    first.boot()
    assert first.raise_notice("pd_limit_exceeded", "limit-worker-2") is True
    assert first.flush() == 0                                # no channel: held
    second = nt.Notifier(home, {"pd_limit_exceeded": "agent"})   # the restarted daemon's
    second.boot()
    assert list(second.owed) == ["limit-worker-2"]
    ours, theirs = _pair()
    second.attach(ours)
    assert second.flush() == 1
    [record] = _records(theirs)
    assert record.source == "pd_limit_exceeded" and record.count is None
    assert "macf-daemon" in build_event(record)["params"]["content"]
    with pytest.raises(ValueError):
        second.raise_notice("amail", "not-raised-by-the-daemon")
