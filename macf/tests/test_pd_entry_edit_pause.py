"""An agent edits, pauses and resumes its own entries (the scheduler design, 1: "creates, lists,
edits, pauses and removes"). The event log stays the only store: an edit, a pause and a resume
are events, and the entries held are what they fold to."""
import argparse

from macf.pd.entries import (EVENT_ENTRY_ADDED, EVENT_ENTRY_CHANGED, EVENT_ENTRY_PAUSED, EVENT_ENTRY_RESUMED,
                             fold, new_entry_id)
from test_pd_entries import _live_session_daemon
from test_primal_daemon import base, run_daemon  # noqa: F401 - fixtures


def _ev(kind, **data):
    return {"event": kind, "data": {"agent": "A@abc123", **data}}


def test_the_fold_applies_an_edit_a_pause_and_a_resume_and_ignores_them_for_an_entry_not_held():
    eid, stranger = new_entry_id(), new_entry_id()
    added = _ev(EVENT_ENTRY_ADDED, id=eid, when="cron:0 9 * * *", purpose="old", missed="once")
    paused = _ev(EVENT_ENTRY_PAUSED, id=eid, at="2026-10-24T10:00:00+00:00")
    edited = _ev(EVENT_ENTRY_CHANGED, id=eid, when="cron:0 10 * * *", purpose="new", missed="skip")
    held = fold([added, paused, edited, _ev(EVENT_ENTRY_PAUSED, id=stranger, at="x")], "A@abc123")
    assert list(held) == [eid]
    assert held[eid]["purpose"] == "new" and held[eid]["when"] == "cron:0 10 * * *"
    assert held[eid]["paused_at"] == "2026-10-24T10:00:00+00:00"          # a pause outlives an edit
    resumed = fold([added, paused, edited, _ev(EVENT_ENTRY_RESUMED, id=eid, at="2026-10-24T11:00:00+00:00")],
                   "A@abc123")[eid]
    assert "paused_at" not in resumed and resumed["resumed_at"] == "2026-10-24T11:00:00+00:00"


def test_a_paused_entry_never_fires_and_a_resumed_one_does_not_make_up_what_the_pause_covered(tmp_path):
    from channel_receiver import ChannelReceiver
    from macf.pd import scheduler as sc
    from test_pd_schedule import CARD, Log, at, make_scheduler
    log, now = Log(), [at("2026-10-19 12:00")]
    eid = new_entry_id()
    log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": eid, "when": "rrule:FREQ=MINUTELY;INTERVAL=50",
                                   "zone": "UTC", "start": "2026-10-19T12:00:00+00:00", "action": "wake",
                                   "missed": "once"})
    log.append(EVENT_ENTRY_PAUSED, {"agent": CARD, "id": eid, "at": "2026-10-19T12:10:00+00:00"})
    channel = ChannelReceiver(tmp_path / "agent")
    now[0] = at("2026-10-19 15:00")                    # three firings due while paused
    s = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    s.tick()
    assert channel.received == [] and log.of(sc.EVENT_ENTRY_FIRED) == []
    log.append(EVENT_ENTRY_RESUMED, {"agent": CARD, "id": eid, "at": "2026-10-19T15:00:00+00:00"})
    resumed = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    resumed.tick()
    assert channel.received == []                      # nothing owed for 12:50, 13:40 or 14:30
    now[0] = at("2026-10-19 15:20")                    # the next step of its own phase
    resumed.tick()
    assert channel.received == [("pd_entry_due", eid)]
    assert log.of(sc.EVENT_ENTRY_FIRED)[-1]["missed"] == 0


def test_edit_and_resume_come_only_from_the_live_session_and_pause_from_anyone(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    from test_primal_daemon import ask
    daemon = _live_session_daemon(tmp_path, base, run_daemon, monkeypatch)
    eid = ask(daemon, {"op": "entry_add", "when": "cron:0 9 * * *", "purpose": "p", "action": "wake",
                       "missed": "once"})["entries"][-1]["id"]
    edited = ask(daemon, {"op": "entry_edit", "id": eid, "when": "cron:0 10 * * *", "purpose": "q"})
    assert edited["ok"] and edited["entries"][-1]["purpose"] == "q"
    assert daemon.scheduler.entries[eid]["when"] == "cron:0 10 * * *"
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: None)     # the operator, outside it
    assert "only from the agent's live session" in ask(daemon, {"op": "entry_edit", "id": eid, "purpose": "r"})["error"]
    assert ask(daemon, {"op": "entry_pause", "id": eid})["ok"]
    assert daemon.scheduler.entries[eid]["paused_at"]
    assert "already paused" in ask(daemon, {"op": "entry_pause", "id": eid})["error"]
    assert "only from the agent's live session" in ask(daemon, {"op": "entry_resume", "id": eid})["error"]
    import os

    from macf.notify.session import proc_start
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: (os.getpid(), proc_start(os.getpid())))
    assert ask(daemon, {"op": "entry_resume", "id": eid})["ok"]
    assert "paused_at" not in daemon.scheduler.entries[eid]
    assert "no entry" in ask(daemon, {"op": "entry_pause", "id": new_entry_id()})["error"]


def test_the_cli_sends_edit_pause_and_resume_and_refuses_an_empty_edit(monkeypatch, capsys):
    from macf.pd import cli, client
    from macf.pd.interface import Response
    sent = []
    monkeypatch.setattr(client, "ask", lambda card, request, **kw: sent.append(request) or Response(ok=True, entries=[]))
    monkeypatch.setattr(cli, "_this_agent", lambda: (None, "Tester@abc123"))
    parser = argparse.ArgumentParser()
    cli.add_pd_parser(parser.add_subparsers(dest="cmd"))
    eid = "e-0123456789ab"
    for argv in (["edit", eid, "--purpose", "new", "--missed", "skip"], ["pause", eid], ["resume", eid]):
        args = parser.parse_args(["pd", "entry", *argv])
        assert args.func(args) == 0
    assert sent == [{"op": "entry_edit", "id": eid, "purpose": "new", "missed": "skip"},
                    {"op": "entry_pause", "id": eid}, {"op": "entry_resume", "id": eid}]
    args = parser.parse_args(["pd", "entry", "edit", eid])
    assert args.func(args) == 2 and len(sent) == 3


def test_edit_and_resume_start_in_ask_like_add_and_pause_does_not():
    from macf.utils.claude_settings import _DEFAULT_ASK
    assert "Bash(macf_tools pd entry edit:*)" in _DEFAULT_ASK
    assert "Bash(macf_tools pd entry resume:*)" in _DEFAULT_ASK
    assert not any("pd entry pause" in rule for rule in _DEFAULT_ASK)


def test_an_edit_after_a_resume_does_not_make_up_what_the_pause_covered(tmp_path):
    """Review of #814 (the macOS maintainer's probe): a purpose-only edit keeps the start, so
    an edit that dropped the resume brought back every instant the pause covered."""
    from channel_receiver import ChannelReceiver
    from macf.pd import scheduler as sc
    from test_pd_schedule import CARD, Log, at, make_scheduler
    log, now = Log(), [at("2026-10-19 15:05")]
    eid = new_entry_id()
    form = {"agent": CARD, "id": eid, "when": "rrule:FREQ=MINUTELY;INTERVAL=50", "zone": "UTC",
            "start": "2026-10-19T12:00:00+00:00", "action": "wake", "missed": "once", "purpose": "old"}
    log.append(EVENT_ENTRY_ADDED, form)
    log.append(EVENT_ENTRY_PAUSED, {"agent": CARD, "id": eid, "at": "2026-10-19T12:10:00+00:00"})
    log.append(EVENT_ENTRY_RESUMED, {"agent": CARD, "id": eid, "at": "2026-10-19T15:00:00+00:00"})
    log.append(EVENT_ENTRY_CHANGED, {**form, "purpose": "new"})
    channel = ChannelReceiver(tmp_path / "agent")
    make_scheduler(tmp_path, [], log, now, on_notice=channel).tick()
    assert channel.received == [] and log.of(sc.EVENT_ENTRY_FIRED) == []


def test_an_edit_after_untrusted_input_marks_an_entry_made_clean(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """Review of #814: the scheduler design's 5.3 guarantee holds at the new door. An entry made
    from a clean context and edited after the session read untrusted input comes back marked."""
    from macf.agent_events_log import append_event
    from test_primal_daemon import ask
    daemon = _live_session_daemon(tmp_path, base, run_daemon, monkeypatch)
    append_event("session_started", {"session_id": "s"})
    made = ask(daemon, {"op": "entry_add", "when": "cron:0 9 * * *", "purpose": "p", "action": "wake",
                        "missed": "once"})["entries"][-1]
    assert made["marked"] == []
    append_event("tool_call_started", {"tool": "WebFetch", "session_id": "s"})
    edited = ask(daemon, {"op": "entry_edit", "id": made["id"], "purpose": "q"})["entries"][-1]
    assert edited["marked"] == ["a web fetch"]


def test_a_paused_entry_shows_no_next_time_and_owes_no_wake_from_before_its_pause(tmp_path):
    """A pause means "stop waking me": the agenda shows no next firing, and a wake that was owed
    from before the pause isn't owed again at the next daemon start."""
    from channel_receiver import ChannelReceiver
    from macf.pd import scheduler as sc
    from macf.pd.cli import _next
    from test_pd_schedule import CARD, Log, at, make_scheduler
    log, now = Log(), [at("2026-10-23 09:00")]
    eid = new_entry_id()
    log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": eid, "when": "cron:0 9 * * *", "zone": "UTC",
                                   "start": "2026-10-19T08:00:00+00:00", "action": "wake", "missed": "once"})
    log.append(sc.EVENT_ENTRY_FIRED, {"agent": CARD, "id": eid, "for": "2026-10-20T09:00:00+00:00",
                                      "missed": 0, "notified": True})     # fired, never delivered
    log.append(EVENT_ENTRY_PAUSED, {"agent": CARD, "id": eid, "at": "2026-10-20T10:00:00+00:00"})
    channel = ChannelReceiver(tmp_path / "agent")
    s = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    s.tick()
    assert channel.received == []
    assert _next(s.entries[eid]) == "none"


def test_a_resume_says_how_many_firings_the_pause_covered(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """None is fired late, whatever the missed policy: a pause is a choice, not a miss. The
    resume says how many fell in it instead, so an entry whose policy is report still hears."""
    from datetime import datetime

    from macf.pd.entries import firings_between
    from test_primal_daemon import ask
    entry = {"when": "rrule:FREQ=MINUTELY;INTERVAL=50", "zone": "UTC", "start": "2026-10-19T12:00:00+00:00"}
    covered = firings_between(entry, datetime.fromisoformat("2026-10-19T12:10:00+00:00"),
                              datetime.fromisoformat("2026-10-19T15:00:00+00:00"))
    assert covered == 3                                  # 12:50, 13:40 and 14:30
    assert firings_between(entry, datetime.fromisoformat("2026-10-19T09:00:00+00:00"),
                           datetime.fromisoformat("2026-10-19T12:49:00+00:00")) == 0   # nothing before its start
    daemon = _live_session_daemon(tmp_path, base, run_daemon, monkeypatch)
    eid = ask(daemon, {"op": "entry_add", "when": "cron:0 9 * * *", "purpose": "p", "action": "wake",
                       "missed": "report"})["entries"][-1]["id"]
    ask(daemon, {"op": "entry_pause", "id": eid})
    entry = next(e for e in ask(daemon, {"op": "entry_resume", "id": eid})["entries"] if e["id"] == eid)
    assert entry["skipped_in_pause"] == 0 and "resumed_at" in entry
