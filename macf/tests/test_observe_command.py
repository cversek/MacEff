"""Observation acts through a command: the agent's daemon takes each one, reading who asks from
the socket (persistent_layer 5.4).

The repo owner ruled that the operator relays an invitation's secret. Invite comes only from the
live session, so a secret in the invite's reply would sit in the observed agent's own transcript
and context, and the agent would hold it first. So the act is split: the session's invite returns
no secret, and the operator fetches it once from outside the session. These tests run a real
daemon and stand in for the session by naming this test's own process as the session unit.
"""
import argparse
import json
import os
from types import SimpleNamespace

import pytest

from macf.notify.session import proc_start
from macf.observe import acts
from test_primal_daemon import ask, base, make_home, run_daemon  # noqa: F401 - fixtures

THEM = "Onlooker@cd34ef"


@pytest.fixture
def observed(tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """A running daemon whose session is switchable, a transcript to take offsets from, and an
    onlooker the roster places here."""
    daemon = run_daemon(make_home(tmp_path, []), base)
    session = [None]
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: session[0])
    transcript = tmp_path / "s.jsonl"
    transcript.write_text("x" * 100)
    from macf.utils import paths, roster
    monkeypatch.setattr(paths, "get_session_transcript_path", lambda sid: str(transcript))
    monkeypatch.setattr(roster, "local_roster", lambda **kw: SimpleNamespace(entries=[SimpleNamespace(card=THEM)]))

    def in_session(on=True):
        session[0] = (os.getpid(), proc_start(os.getpid())) if on else None
    return SimpleNamespace(daemon=daemon, in_session=in_session, transcript=transcript, log=isolated_events_log)


def _invite(lease_s=None):
    req = {"op": "observe_invite", "onlooker": THEM, "session_id": "0123abcd-0000"}
    if lease_s:
        req["lease_s"] = lease_s
    return req


def _rows(log, kind):
    return [r["data"] for r in map(json.loads, log.read_text().splitlines()) if r.get("event") == kind]


def test_the_session_invites_and_is_never_shown_the_secret(observed):
    """Outside the session, an invite is refused and nothing is recorded. From it, the invitation
    is recorded at the transcript's current size, and the reply carries no secret or digest."""
    d = observed.daemon
    refused = ask(d, _invite())
    assert not refused["ok"] and "live session" in refused["error"]
    assert _rows(observed.log, acts.EVENT_INVITE) == []

    observed.in_session()
    made = ask(d, _invite(lease_s=3600))
    assert made["ok"] and "secret" not in made
    assert made["observations"] == [{"onlooker": THEM, "status": "active", "lease_until": made["observations"][0]["lease_until"],
                                     "ended_by": None, "secret_held": True}]
    assert "sha256" not in json.dumps(made)
    [inv] = _rows(observed.log, acts.EVENT_INVITE)
    assert inv["stream_from"] == 100 and inv["observed"] == d.card


def test_the_operator_fetches_the_secret_once_from_outside_the_session(observed):
    """The session's ask is refused. From outside it the secret comes back once, matching the
    digest in the log, its fetch recorded first; the secret itself is never in the log, and a
    second ask says when the first was answered."""
    d = observed.daemon
    observed.in_session()
    ask(d, _invite())
    from_session = ask(d, {"op": "observe_secret", "onlooker": THEM})
    assert not from_session["ok"] and "never shown to the observed agent's session" in from_session["error"]

    observed.in_session(False)
    got = ask(d, {"op": "observe_secret", "onlooker": THEM})
    assert got["ok"] and got["secret"]
    [inv] = _rows(observed.log, acts.EVENT_INVITE)
    assert acts._digest(got["secret"]) == inv["secret_sha256"]
    assert got["secret"] not in observed.log.read_text()
    [fetched] = _rows(observed.log, acts.EVENT_SECRET_FETCHED)
    assert fetched["onlooker"] == THEM and fetched["by_pid"] > 0
    again = ask(d, {"op": "observe_secret", "onlooker": THEM})
    assert not again["ok"] and "was fetched at" in again["error"] and "given once" in again["error"]


def test_a_secret_the_daemon_no_longer_holds_says_invite_again(observed):
    observed.in_session()
    ask(observed.daemon, _invite())
    observed.daemon._secrets.clear()                    # as a daemon started after the invitation
    observed.in_session(False)
    lost = ask(observed.daemon, {"op": "observe_secret", "onlooker": THEM})
    assert not lost["ok"] and "doesn't hold" in lost["error"] and "invite again" in lost["error"]


def test_where_the_operator_has_a_uid_only_it_gets_the_secret_or_ends_from_outside(observed, monkeypatch):
    observed.in_session()
    ask(observed.daemon, _invite())
    observed.in_session(False)
    monkeypatch.setattr(observed.daemon.core.declaration, "operator_uid", os.getuid() + 1)
    for op in ("observe_secret", "observe_end"):
        refused = ask(observed.daemon, {"op": op, "onlooker": THEM})
        assert not refused["ok"] and f"uid {os.getuid() + 1}" in refused["error"]


@pytest.mark.parametrize("from_session, ended_by, advisory", [(True, "observed", False), (False, "operator", True)])
def test_an_ending_is_named_by_where_it_came_from(observed, from_session, ended_by, advisory):
    """From the session, the observed agent's; from outside it, the operator's, shown as advisory
    where no operator uid is declared. The held secret goes with it."""
    observed.in_session()
    ask(observed.daemon, _invite())
    observed.in_session(from_session)
    ended = ask(observed.daemon, {"op": "observe_end", "onlooker": THEM})
    assert ended["ok"]
    [row] = ended["observations"]
    assert row["ended_by"] == ended_by and bool(row.get("ended_by_advisory")) is advisory
    assert not row["secret_held"] and THEM not in observed.daemon._secrets


def test_pause_and_resume_only_from_the_session_at_the_transcripts_size(observed):
    observed.in_session()
    ask(observed.daemon, _invite())
    observed.transcript.write_text("x" * 250)
    observed.in_session(False)
    assert "live session" in ask(observed.daemon, {"op": "observe_pause", "onlooker": THEM, "session_id": "0123abcd"})["error"]
    observed.in_session()
    assert ask(observed.daemon, {"op": "observe_pause", "onlooker": THEM, "session_id": "0123abcd"})["ok"]
    observed.transcript.write_text("x" * 400)
    assert ask(observed.daemon, {"op": "observe_resume", "onlooker": THEM, "session_id": "0123abcd"})["ok"]
    assert [p["at"] for p in _rows(observed.log, acts.EVENT_PAUSE) + _rows(observed.log, acts.EVENT_RESUME)] == [250, 400]


def test_an_onlooker_the_roster_does_not_place_here_is_not_invited(observed):
    observed.in_session()
    refused = ask(observed.daemon, {**_invite(), "onlooker": "Elsewhere@ef56ab"})
    assert not refused["ok"] and "not invited" in refused["error"]
    assert _rows(observed.log, acts.EVENT_INVITE) == []


def test_the_cli_names_its_session_and_prints_a_secret_only_when_one_comes_back(monkeypatch, capsys):
    from macf.observe import cli
    from macf.pd import cli as pd_cli, client
    from macf.pd.interface import Response
    from macf.utils import session
    sent, replies = [], [Response(ok=True, observations=[]), Response(ok=True, secret="s3cr3t", observations=[])]
    monkeypatch.setattr(client, "ask", lambda card, req, **kw: sent.append(req) or replies.pop(0))
    monkeypatch.setattr(pd_cli, "_this_agent", lambda: (None, "Observed@ab12cd"))
    monkeypatch.setattr(session, "get_current_session_id", lambda *a: "0123abcd-0000")
    parser = argparse.ArgumentParser()
    cli.add_observe_parser(parser.add_subparsers(dest="cmd"))
    for argv in (["observe", "invite", THEM, "--lease", "2h"], ["observe", "secret", THEM]):
        args = parser.parse_args(argv)
        assert args.func(args) == 0
    assert sent == [{"op": "observe_invite", "onlooker": THEM, "session_id": "0123abcd-0000", "lease_s": 7200.0},
                    {"op": "observe_secret", "onlooker": THEM}]
    out = capsys.readouterr().out
    assert out.count("s3cr3t") == 1 and "observe secret" in out.split("s3cr3t")[0]


def test_opening_the_session_asks_and_closing_it_does_not():
    from macf.utils.claude_settings import _DEFAULT_ASK
    assert {"Bash(macf_tools observe invite:*)", "Bash(macf_tools observe resume:*)"} <= set(_DEFAULT_ASK)
    assert not any("observe pause" in e or "observe end" in e or "observe secret" in e for e in _DEFAULT_ASK)
