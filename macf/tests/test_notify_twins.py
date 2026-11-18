"""The ambiguous target: two live processes serving one conversation.

Observed live, not imagined -- an interrupt-and-restart of a supervised session
can leave a background twin that resumes the same conversation. Both processes
are legitimate and alive, so the incarnation check does not help: it guards a
RECYCLED pid, not a DELIBERATE fork.

The design position under test is that the notifier does NOT resolve this
silently. It picks a target it can justify, and surfaces the ambiguity, because
an agent may decline to be told about the WORLD but never about ITSELF.
"""
import json
import os

import pytest

from macf.notify import session


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    d = tmp_path / ".claude" / "sessions"
    d.mkdir(parents=True)
    return d


def _sidecar(directory, pid, session_id, proc_start, status="idle", started_at_ms=None):
    (directory / f"{pid}.json").write_text(json.dumps({
        "pid": pid,
        "sessionId": session_id,
        "procStart": str(proc_start),
        **({"startedAt": started_at_ms} if started_at_ms else {}),
        "status": status,
        "kind": "interactive",
        "cwd": "/somewhere",
        "messagingSocketPath": f"/run/user/1000/cc-socks/{pid}.sock",
        "updatedAt": 1700000000000,
    }))


def test_a_single_process_conversation_is_not_ambiguous(home):
    _sidecar(home, os.getpid(), "conv-solo", session.proc_start(os.getpid()))
    chosen, candidates = session.resolve_target("conv-solo")
    assert chosen is not None and chosen.pid == os.getpid()
    assert len(candidates) == 1


def test_twins_are_detected_and_the_newest_is_chosen(home, monkeypatch, capsys):
    """Both processes must be LIVE for this to be the ambiguous case at all."""
    live = os.getpid()
    start = session.proc_start(live)
    _sidecar(home, live, "conv-twin", start)
    newer = session.proc_start_from_key(session.proc_start_key(start) + 500)
    _sidecar(home, live + 1, "conv-twin", newer)
    # Both pids report as live; the fixture cannot fork a real second process.
    monkeypatch.setattr(session, "proc_start", lambda pid: newer if pid == live + 1 else start)

    chosen, candidates = session.resolve_target("conv-twin")
    assert len(candidates) == 2, "both twins must be seen, not one"
    assert chosen.pid == live + 1, "newest proc_start wins"
    # The ambiguity is ANNOUNCED, never resolved silently.
    err = capsys.readouterr().err
    assert "live processes serve conversation" in err
    assert "recording the ambiguity" in err


def test_a_dead_twin_does_not_make_a_conversation_ambiguous(home):
    """A stale sidecar for an exited process is not a second agent.

    Sockets and sidecars outlive their processes -- measured, 51 stale sockets
    against 1 live pid on this host -- so liveness must come from /proc, not from
    the presence of a file.
    """
    live = os.getpid()
    _sidecar(home, live, "conv-mixed", session.proc_start(live))
    _sidecar(home, 999999, "conv-mixed", 1)  # never running
    chosen, candidates = session.resolve_target("conv-mixed")
    assert len(candidates) == 1
    assert chosen.pid == live


def test_a_sidecar_whose_number_came_back_is_not_a_live_session(home):
    """Pids start over when a container is recreated, so an old sidecar's number can come back.

    Seen on a recreate: three old sidecars named pids that had become threads of an unrelated
    service. The daemon took them for clients started by hand and held the seat's session down
    for as long as those threads lived. This test process began long after the recorded session.
    """
    live = os.getpid()
    other_start = session.proc_start_key(session.proc_start(live)) + 500
    _sidecar(home, live, "conv-old", session.proc_start_from_key(other_start), started_at_ms=1000)
    assert session.live_sessions() == []


def test_a_differing_start_with_no_proof_of_order_stays_live(home):
    """A false mismatch would start a second client beside a live session, so a differing start
    alone isn't enough: the process must also have begun after the session did."""
    live = os.getpid()
    other_start = session.proc_start_key(session.proc_start(live)) + 500
    other = session.proc_start_from_key(other_start)
    far_future_ms = 4102444800000
    _sidecar(home, live, "conv-order", other, started_at_ms=far_future_ms)
    assert [s.pid for s in session.live_sessions()] == [live]
    _sidecar(home, live, "conv-order", other)  # no startedAt at all
    assert [s.pid for s in session.live_sessions()] == [live]


def test_the_start_epoch_is_when_this_process_began():
    """Ticks count from boot, so comparing them with the wall clock means converting them."""
    import time
    began = session._start_epoch(session.proc_start(os.getpid()))
    assert began is not None and 0 <= time.time() - began < 86400 * 30


def test_a_sidecar_with_no_start_time_still_counts_as_live(home):
    """Unknown isn't stale: a guard against a second client must not start beside this one."""
    live = os.getpid()
    (home / f"{live}.json").write_text(json.dumps({
        "sessionId": "conv-nostart", "status": "idle", "updatedAt": 0,
    }))
    assert [s.pid for s in session.live_sessions()] == [live]


def test_a_sidecar_whose_start_matches_is_a_live_session(home):
    live = os.getpid()
    _sidecar(home, live, "conv-here", session.proc_start(live))
    assert [s.pid for s in session.live_sessions()] == [live]


def test_an_unknown_conversation_yields_no_target_rather_than_a_guess(home):
    chosen, candidates = session.resolve_target("conv-does-not-exist")
    assert chosen is None
    assert candidates == []


def test_socket_path_is_taken_from_what_the_client_PUBLISHED(home):
    """Constructing the path duplicates the client's layout decision in our code."""
    pid = os.getpid()
    (home / f"{pid}.json").write_text(json.dumps({
        "sessionId": "conv-pub", "procStart": "1", "status": "idle",
        "messagingSocketPath": "/somewhere/else/custom.sock", "updatedAt": 0,
    }))
    info = session.read_session_info(pid)
    assert info.socket_path == "/somewhere/else/custom.sock"


def test_status_is_turn_state_and_is_never_treated_as_liveness(home):
    """MEASURED: `status` is stamped at transitions, not on a heartbeat.

    A session that died mid-turn leaves `busy` behind forever, so a notifier that
    aged this field would report a corpse as working.
    """
    pid = 999999  # not running
    _sidecar(home, pid, "conv-dead", 1, status="busy")
    info = session.read_session_info(pid)
    assert info.status == "busy"
    assert session.proc_start(pid) is None
    assert info not in session.live_sessions()


def test_a_sidecar_without_a_conversation_id_is_REFUSED_not_given_one(home, capsys):
    """Found by the mutation sweep, not by design -- the suite was green without it.

    Inventing an identity for an unidentifiable session is worse than refusing it.
    Two such sessions would share the invented id, so they would appear to be
    twins of each other, and the conversation-keyed dedup would then suppress one
    unrelated agent's notice because a different agent had already been told.
    A fabricated identity turns an idempotency control into a silent drop.
    """
    pid = os.getpid()
    (home / f"{pid}.json").write_text(json.dumps({
        "procStart": "1", "status": "idle", "updatedAt": 0,
    }))
    assert session.read_session_info(pid) is None
    assert "names no sessionId" in capsys.readouterr().err
    # and it must not appear as a live session at all
    assert [s.pid for s in session.live_sessions()] == []


def test_a_supervisor_CLAIM_beats_the_newest_start_ordering(home, monkeypatch, capsys):
    """An ORDERING is a weaker answer than an IDENTITY.

    The measured mechanism: a supervised client is spawned into its own session,
    so an interrupt in the pane reaches the SUPERVISOR rather than the client. If
    the supervisor dies there the client is orphaned, and the next supervisor
    spawns a fresh one -- two processes, one conversation. The orphan is older.

    Newest-start therefore usually picks correctly, but the supervisor RECORDS
    which child it spawned, and asking the party that made the decision is not a
    guess. Here the claim points at the OLDER pid, so only an implementation that
    actually consults it can pass.
    """
    live, ticks = os.getpid(), 100
    _sidecar(home, live, "conv-sup", ticks)
    _sidecar(home, live + 1, "conv-sup", ticks + 500)   # newer
    monkeypatch.setattr(session, "proc_start", lambda pid: str(ticks + 500 if pid == live + 1 else ticks))
    monkeypatch.setattr(session, "supervised_child_pids", lambda: {live})

    chosen, candidates = session.resolve_target("conv-sup")
    assert len(candidates) == 2
    assert chosen.pid == live, "the supervisor's claim must outrank the ordering"
    assert "authoritative" in capsys.readouterr().err


def test_it_falls_back_to_newest_start_when_no_supervisor_claims_one(home, monkeypatch, capsys):
    """An unsupervised session is ordinary, not an error.

    Fail-closed here would refuse to notify a perfectly healthy agent, on an
    advisory path, because a supervision registry had nothing to say about it.
    """
    live, ticks = os.getpid(), 100
    _sidecar(home, live, "conv-nosup", ticks)
    _sidecar(home, live + 1, "conv-nosup", ticks + 500)
    monkeypatch.setattr(session, "proc_start", lambda pid: str(ticks + 500 if pid == live + 1 else ticks))
    monkeypatch.setattr(session, "supervised_child_pids", lambda: set())

    chosen, _ = session.resolve_target("conv-nosup")
    assert chosen.pid == live + 1, "newest wins when nothing authoritative applies"
    err = capsys.readouterr().err
    assert "fallback" in err, "the report must say WHICH rule decided"


def test_an_unreadable_supervisor_registry_does_not_block_delivery(monkeypatch, capsys):
    """Advisory refinement. Its failure must not become a missed notice."""
    import macf.supervisor as sup

    def boom():
        raise OSError("registry gone")

    monkeypatch.setattr(sup, "_iter_live_supervisors", boom)
    assert session.supervised_child_pids() == set()
    assert "falling back to newest-start" in capsys.readouterr().err
