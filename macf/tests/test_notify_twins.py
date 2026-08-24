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


def _sidecar(directory, pid, session_id, proc_start, status="idle"):
    (directory / f"{pid}.json").write_text(json.dumps({
        "pid": pid,
        "sessionId": session_id,
        "procStart": str(proc_start),
        "status": status,
        "kind": "interactive",
        "cwd": "/somewhere",
        "messagingSocketPath": f"/run/user/1000/cc-socks/{pid}.sock",
        "updatedAt": 1700000000000,
    }))


def test_a_single_process_conversation_is_not_ambiguous(home):
    _sidecar(home, os.getpid(), "conv-solo", session.proc_start_ticks(os.getpid()))
    chosen, candidates = session.resolve_target("conv-solo")
    assert chosen is not None and chosen.pid == os.getpid()
    assert len(candidates) == 1


def test_twins_are_detected_and_the_newest_is_chosen(home, monkeypatch, capsys):
    """Both processes must be LIVE for this to be the ambiguous case at all."""
    live = os.getpid()
    ticks = session.proc_start_ticks(live)
    _sidecar(home, live, "conv-twin", ticks)
    _sidecar(home, live + 1, "conv-twin", ticks + 500)
    # Both pids report as live; the fixture cannot fork a real second process.
    monkeypatch.setattr(session, "proc_start_ticks", lambda pid: ticks)

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
    _sidecar(home, live, "conv-mixed", session.proc_start_ticks(live))
    _sidecar(home, 999999, "conv-mixed", 1)  # never running
    chosen, candidates = session.resolve_target("conv-mixed")
    assert len(candidates) == 1
    assert chosen.pid == live


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
    assert session.proc_start_ticks(pid) is None
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
