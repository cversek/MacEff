"""Agents' own entries: ids, and when an entry fires (design 2 and 3)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from macf.channels.maceff_channel import NoticeRecord
from macf.pd.entries import ENTRY_ID, new_entry_id, parse_when
from test_primal_daemon import base, run_daemon  # noqa: F401 - fixtures

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 19, 14, 0, tzinfo=NEW_YORK)


def test_an_entry_id_is_opaque_and_the_channel_takes_it():
    """An id carries no calling card, whose @ the channel's record refuses (#734's class), and
    every id made fits the record's pattern."""
    ids = {new_entry_id() for _ in range(200)}
    assert len(ids) == 200 and all(ENTRY_ID.match(i) for i in ids)
    for i in list(ids)[:20]:
        NoticeRecord(source="pd_run_failed", arrival_id=i, read_at=0.0, sent_at=0.0)


def test_each_shape_says_when_it_fires():
    """An instant, a time from now, tomorrow at a time, a cron and a recurrence, each read in the
    entry's zone. A relative time is fixed when the entry is made."""
    def first(text, **kw):
        return parse_when(text, NEW_YORK, NOW, **kw).next_after(NOW).astimezone(UTC).isoformat()
    assert first("2026-10-20T06:30") == "2026-10-20T10:30:00+00:00"
    assert first("in 20m") == "2026-10-19T18:20:00+00:00"
    assert first("in 3d") == "2026-10-22T18:00:00+00:00"
    assert first("tomorrow 06:30") == "2026-10-20T10:30:00+00:00"
    assert first("cron:0 9 * * 1-5") == "2026-10-20T13:00:00+00:00"
    assert first("rrule:FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1",
                 start=datetime(2026, 10, 1, 17, 0, tzinfo=NEW_YORK)) == "2026-10-30T21:00:00+00:00"
    once = parse_when("in 20m", NEW_YORK, NOW)
    assert once.next_after(once.at) is None                 # a one-shot fires once


@pytest.mark.parametrize("text, says", [
    ("next tuesday", "not a time an entry reads"),
    ("2026-10-19T09:00", "not in the future"),
    ("in 0m", "not in the future"),
    ("tomorrow 25:00", "names no time of day"),
    ("rrule:FREQ=YEARLY", "not supported"),
])
def test_a_time_it_cannot_read_is_refused_by_name(text, says):
    with pytest.raises(ValueError, match=says):
        parse_when(text, NEW_YORK, NOW)


def test_the_entries_held_are_what_the_events_fold_to():
    """The event log is the store (R16): an entry added is held until it's removed, and another
    agent's events, or a record whose id isn't an entry id, change nothing."""
    from macf.pd.entries import EVENT_ENTRY_ADDED, EVENT_ENTRY_REMOVED, fold
    me, other = "Tester@abc123", "Other@def456"
    a, b = new_entry_id(), new_entry_id()

    def ev(kind, card, entry_id, **data):
        return {"event": kind, "data": {"agent": card, "id": entry_id, **data}}
    events = [ev(EVENT_ENTRY_ADDED, me, a, purpose="check the pace"),
              ev(EVENT_ENTRY_ADDED, me, b, purpose="the weekly audit"),
              ev(EVENT_ENTRY_ADDED, other, new_entry_id(), purpose="not mine"),
              ev(EVENT_ENTRY_ADDED, me, "Tester@abc123-1", purpose="not an entry id"),
              ev(EVENT_ENTRY_REMOVED, other, b),
              ev(EVENT_ENTRY_REMOVED, me, a)]
    held = fold(events, me)
    assert list(held) == [b] and held[b]["purpose"] == "the weekly audit"


def test_only_the_live_session_makes_an_entry(tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """The daemon makes an entry only for a process below the session unit: with no session, or
    from outside it, the request is refused and nothing is recorded, though the entries held can
    still be read. From the session, the entry is recorded with its time fixed, and listed (the
    scheduler design, 1 and 5.5)."""
    import os

    from macf.notify.session import proc_start
    from test_primal_daemon import ask, make_home
    daemon = run_daemon(make_home(tmp_path, []), base)
    add = {"op": "entry_add", "when": "in 20m", "purpose": "check the pace", "action": "wake", "missed": "once"}
    refused = ask(daemon, add)
    assert not refused["ok"] and "live session" in refused["error"]
    listed = ask(daemon, {"op": "entry_list"})
    assert listed["ok"] and listed["entries"] == []           # reading needs only the uid

    me = (os.getpid(), proc_start(os.getpid()))            # this test stands in for the session
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: me)
    made = ask(daemon, add)
    assert made["ok"] and len(made["entries"]) == 1
    entry = made["entries"][0]
    assert ENTRY_ID.match(entry["id"]) and entry["purpose"] == "check the pace"
    assert entry["when"] == entry["first"]                  # "in 20m" fixed at its instant
    assert ask(daemon, {"op": "entry_list"})["entries"] == [entry]


def test_a_due_entry_fires_once_through_the_channel_even_across_a_restart(tmp_path):
    """A wake entry fires at its time as pd_entry_due, whose id is the entry's, through the
    channel's own record. Not before its time, and once: a daemon that restarts reads the
    firing back and doesn't fire it again. A recurring entry down across several firings fires
    once, for the newest (the scheduler design, 4.1 and 6)."""
    from channel_receiver import ChannelReceiver
    from macf.pd import scheduler as sc
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from test_pd_schedule import CARD, Log, at, make_scheduler
    log, now = Log(), [at("2026-10-19 12:00")]
    once, daily = new_entry_id(), new_entry_id()
    for entry_id, when in ((once, "2026-10-19T12:20:00+00:00"), (daily, "cron:0 9 * * *")):
        log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": when, "zone": "UTC",
                                       "start": "2026-10-16T08:00:00+00:00", "action": "wake", "missed": "once"})
    channel = ChannelReceiver(tmp_path / "agent")
    s = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    s.tick()
    assert channel.received == [("pd_entry_due", daily)]       # 09:00 on the 16th to the 19th: once
    assert log.of(sc.EVENT_ENTRY_FIRED)[0]["missed"] == 3
    now[0] = at("2026-10-19 12:20")
    s.tick()
    assert channel.received[-1] == ("pd_entry_due", once)
    restarted = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    restarted.tick()
    assert len(channel.received) == 2                          # nothing fires again


def test_a_skip_entry_records_a_missed_firing_and_says_nothing(tmp_path):
    """An entry whose missed policy is skip, due while the daemon was down, is recorded and not
    notified; on time, it notifies (the scheduler design, 3.5)."""
    from channel_receiver import ChannelReceiver
    from macf.pd import scheduler as sc
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from test_pd_schedule import CARD, Log, at, make_scheduler
    log, now = Log(), [at("2026-10-19 11:20")]
    entry_id = new_entry_id()
    log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": "cron:0 * * * *", "zone": "UTC",
                                   "start": "2026-10-19T09:30:00+00:00", "action": "wake", "missed": "skip"})
    channel = ChannelReceiver(tmp_path / "agent")
    s = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    s.tick()                                                   # 10:00 and 11:00 passed while down
    assert channel.received == [] and log.of(sc.EVENT_ENTRY_FIRED)[0]["notified"] is False
    now[0] = at("2026-10-19 12:00")
    s.tick()                                                   # 12:00, on time
    assert channel.received == [("pd_entry_due", entry_id)]


def test_a_wake_owed_longer_than_a_day_is_owed_again_at_a_restart(tmp_path):
    """The notifier holds an owed notice for a day. An entry fired two days ago and never
    delivered is owed again when the daemon restarts; one delivered since, or fired within the
    day (the notifier's own read-back holds it), is not (the scheduler design, 4.1)."""
    from channel_receiver import ChannelReceiver
    from macf.pd import scheduler as sc
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from macf.pd.notifier import EVENT_DELIVERED
    from test_pd_schedule import CARD, Log, at, make_scheduler
    log, now = Log(), [at("2026-10-19 12:00")]
    owed, delivered, recent = new_entry_id(), new_entry_id(), new_entry_id()
    for entry_id, when, fired in ((owed, "2026-10-17T09:00:00+00:00", "2026-10-17T09:00:00+00:00"),
                                  (delivered, "2026-10-17T09:30:00+00:00", "2026-10-17T09:30:00+00:00"),
                                  (recent, "2026-10-19T08:00:00+00:00", "2026-10-19T08:00:00+00:00")):
        log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": when, "zone": "UTC",
                                       "start": "2026-10-16T08:00:00+00:00", "action": "wake", "missed": "once"})
        log.append(sc.EVENT_ENTRY_FIRED, {"agent": CARD, "id": entry_id, "for": fired, "missed": 0, "notified": True})
    log.append(EVENT_DELIVERED, {"source": "pd_entry_due", "arrival_id": delivered, "via": "channel", "notifier": "pd"})
    channel = ChannelReceiver(tmp_path / "agent")
    make_scheduler(tmp_path, [], log, now, on_notice=channel)
    assert channel.received == [("pd_entry_due", owed)]


def test_the_cli_asks_the_daemon_and_says_what_it_answered(monkeypatch, capsys):
    """pd entry add sends the entry as asked, and pd entry list prints what is held; a refusal
    is printed as the daemon gave it, and exits non-zero."""
    import argparse

    from macf.pd import cli, client
    from macf.pd.interface import Response
    sent, held = [], {"id": "e-0123456789ab", "when": "2026-10-19T18:20:00+00:00", "first": "2026-10-19T18:20:00+00:00",
                      "missed": "once", "purpose": "check the pace"}

    def ask(card, request, **kw):
        sent.append(request)
        if request["op"] == "entry_add" and request["when"] == "never":
            return Response(ok=False, error="the entry's time was refused")
        return Response(ok=True, entries=[held])
    monkeypatch.setattr(client, "ask", ask)
    monkeypatch.setattr(cli, "_this_agent", lambda: (None, "Tester@abc123"))
    parser = argparse.ArgumentParser()
    cli.add_pd_parser(parser.add_subparsers(dest="cmd"))

    def run(*argv):
        args = parser.parse_args(["pd", "entry", *argv])
        return args.func(args)
    assert run("add", "in 20m", "check the pace", "--missed", "report") == 0
    assert sent[-1] == {"op": "entry_add", "when": "in 20m", "purpose": "check the pace", "action": "wake", "missed": "report"}
    assert "e-0123456789ab" in capsys.readouterr().out
    assert run("list") == 0 and "check the pace" in capsys.readouterr().out
    assert run("add", "never", "x", "--missed", "skip") == 1
    assert "the entry's time was refused" in capsys.readouterr().err


def test_the_agenda_shows_both_tiers_soonest_first():
    """Declared schedules' next runs and the agent's own entries, in one list, each marked with
    its tier and soonest first (story 15)."""
    from macf.pd.cli import agenda_lines
    from macf.pd.interface import CommandRun, Declaration, MissedRunPolicy, Schedule
    decl = Declaration(version=1, agent="Tester@abc123", timezone="UTC", notice_routes={"pd_run_failed": "agent"},
                       schedules=[Schedule(name="sweep", cron="0 13 * * *", missed_run=MissedRunPolicy(kind="skip"),
                                           target="isolated", run=CommandRun(command=["true"], wake_when="exit_code"),
                                           timeout_s=60)])
    entries = [{"id": "e-0123456789ab", "first": "2026-10-19T12:20:00+00:00", "purpose": "check the pace"}]
    lines = agenda_lines(decl, entries, datetime(2026, 10, 19, 12, 0, tzinfo=UTC))
    assert [line.split()[1] for line in lines] == ["entry", "declared"]
    assert lines[1].startswith("2026-10-19T13:00:00+00:00")


def test_from_a_tainted_context_a_recurring_entry_waits_and_a_one_shot_is_marked(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """After the session read untrusted input, a one-shot wake is made and marked, and a
    recurring one waits for the operator. From a clean context both are active and unmarked.
    The reading comes from the session's own tool events (the scheduler design, 5.3)."""
    import os

    from macf.agent_events_log import append_event
    from macf.notify.session import proc_start
    from test_primal_daemon import ask, make_home
    daemon = run_daemon(make_home(tmp_path, []), base)
    me = (os.getpid(), proc_start(os.getpid()))
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: me)

    def add(when):
        made = ask(daemon, {"op": "entry_add", "when": when, "purpose": "p", "action": "wake", "missed": "once"})
        return next(e for e in made["entries"] if e["id"] not in seen)
    seen = set()
    append_event("session_started", {"session_id": "s"})
    clean = add("cron:0 9 * * *")
    seen.add(clean["id"])
    assert (clean["state"], clean["marked"]) == ("active", [])
    append_event("tool_call_started", {"tool": "WebFetch", "session_id": "s"})
    recurring = add("cron:0 9 * * *")
    seen.add(recurring["id"])
    once = add("in 20m")
    assert (recurring["state"], recurring["marked"]) == ("waiting", ["a web fetch"])
    assert (once["state"], once["marked"]) == ("active", ["a web fetch"])


def test_a_waiting_entry_fires_only_once_accepted_and_only_from_then(tmp_path):
    """A waiting entry never fires. Accepted, it fires from its acceptance on, and the firings
    it waited through aren't owed. Declined, it's gone (the scheduler design, 5.3)."""
    from channel_receiver import ChannelReceiver
    from macf.pd import scheduler as sc
    from macf.pd.entries import EVENT_ENTRY_ACCEPTED, EVENT_ENTRY_ADDED, EVENT_ENTRY_DECLINED
    from test_pd_schedule import CARD, Log, at, make_scheduler
    log, now = Log(), [at("2026-10-19 12:30")]
    hourly, declined = new_entry_id(), new_entry_id()
    for entry_id in (hourly, declined):
        log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": "cron:0 * * * *", "zone": "UTC",
                                       "start": "2026-10-19T08:30:00+00:00", "action": "wake", "missed": "once",
                                       "state": "waiting", "marked": ["a web fetch"]})
    channel = ChannelReceiver(tmp_path / "agent")
    s = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    s.tick()
    assert channel.received == [] and log.of(sc.EVENT_ENTRY_FIRED) == []
    log.append(EVENT_ENTRY_ACCEPTED, {"agent": CARD, "id": hourly, "at": "2026-10-19T12:30:00+00:00"})
    log.append(EVENT_ENTRY_DECLINED, {"agent": CARD, "id": declined, "at": "2026-10-19T12:30:00+00:00"})
    s = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    assert list(s.entries) == [hourly]
    s.tick()
    assert channel.received == []                              # 09:00 to 12:00 waited, not owed
    now[0] = at("2026-10-19 13:00")
    s.tick()
    assert channel.received == [("pd_entry_due", hourly)]
    assert log.of(sc.EVENT_ENTRY_FIRED)[0]["missed"] == 0


def test_only_the_operator_answers_an_entry_that_waits(tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """The operator's answer is a positive act: taken only while the session runs, from a process
    with a controlling terminal that isn't the agent's own. A command the agent backgrounds is
    reparented, so lineage can't refuse it; it has the agent's terminal or none, and is refused.
    A pane in the session's own multiplexer has its own terminal, and is taken. Accepting makes
    the entry active in the log and the scheduler, declining removes it, and an entry that doesn't
    wait can't be answered (the scheduler design, 5.3 and 5.4)."""
    import os

    from macf.agent_events_log import append_event
    from macf.notify.session import proc_start
    from macf.pd import daemon as pd_daemon
    from test_primal_daemon import ask, make_home
    daemon = run_daemon(make_home(tmp_path, []), base)
    me = os.getpid()
    session = [(me, proc_start(me))]
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: session[0])
    append_event("session_started", {"session_id": "s"})
    append_event("tool_call_started", {"tool": "WebFetch", "session_id": "s"})
    add = {"op": "entry_add", "when": "cron:0 9 * * *", "purpose": "p", "action": "wake", "missed": "once"}
    first = ask(daemon, add)["entries"][-1]
    second = ask(daemon, add)["entries"][-1]
    assert first["state"] == second["state"] == "waiting"

    def asked_from(tty, ppid=me):
        """The process table as ps would give it: the session's client on pts/0, and the asker."""
        table = {90001: {"ppid": me, "tty": "pts/0", "comm": "claude"},
                 me: {"ppid": 1, "tty": None, "comm": "python"}}
        monkeypatch.setattr(pd_daemon, "process_table", lambda: {**table, me: {"ppid": ppid, "tty": tty, "comm": "bash"}})

    def decide(entry, accept):
        return ask(daemon, {"op": "entry_decide", "id": entry["id"], "accept": accept})
    session[0] = None
    asked_from("pts/3")
    assert "isn't running" in decide(first, True)["error"]             # the session down
    session[0] = (me, proc_start(me))
    asked_from(None, ppid=1)
    assert "no controlling terminal" in decide(first, True)["error"]   # detached or backgrounded
    asked_from("pts/0", ppid=1)
    assert "agent's own terminal" in decide(first, True)["error"]      # reparented, the agent's terminal
    asked_from("pts/3")                                                 # a pane of its own
    accepted = decide(first, True)
    assert accepted["ok"] and {e["id"]: e["state"] for e in accepted["entries"]} == {
        first["id"]: "active", second["id"]: "waiting"}
    assert daemon.scheduler.entries[first["id"]]["state"] == "active"
    assert not decide(first, True)["ok"]                                # it no longer waits
    declined = decide(second, False)
    assert declined["ok"] and [e["id"] for e in declined["entries"]] == [first["id"]]
    assert second["id"] not in daemon.scheduler.entries


def test_the_process_table_reads_terminals_and_finds_the_agents():
    """ps gives each process's parent, terminal and name; the agent's terminals are those of the
    client processes below the session unit, and a process with no terminal reads as None."""
    from macf.pd.daemon import agent_terminals, process_table
    import os
    table = process_table()
    assert os.getpid() in table and table[os.getpid()]["ppid"] == os.getppid()
    fake = {10: {"ppid": 1, "tty": None, "comm": "python"},
            11: {"ppid": 10, "tty": None, "comm": "tmux: server"},
            12: {"ppid": 11, "tty": "pts/0", "comm": "/usr/bin/claude"},
            13: {"ppid": 11, "tty": "pts/1", "comm": "bash"},
            14: {"ppid": 1, "tty": "pts/5", "comm": "claude"}}
    assert agent_terminals(fake, 10) == {"pts/0"}


def test_the_cli_answers_an_entry_and_shows_what_waits(monkeypatch, capsys):
    """pd entry accept and decline send the operator's answer; list shows an entry that waits,
    and one made from a marked context, as such."""
    import argparse

    from macf.pd import cli, client
    from macf.pd.interface import Response
    sent, held = [], {"id": "e-0123456789ab", "when": "cron:0 9 * * *", "first": "2026-10-20T09:00:00+00:00",
                      "missed": "once", "purpose": "check the pace", "state": "waiting", "marked": ["a web fetch"]}

    def ask(card, request, **kw):
        sent.append(request)
        return Response(ok=True, entries=[held])
    monkeypatch.setattr(client, "ask", ask)
    monkeypatch.setattr(cli, "_this_agent", lambda: (None, "Tester@abc123"))
    parser = argparse.ArgumentParser()
    cli.add_pd_parser(parser.add_subparsers(dest="cmd"))

    def run(*argv):
        args = parser.parse_args(["pd", "entry", *argv])
        return args.func(args)
    assert run("list") == 0 and "[waiting] [marked] check the pace" in capsys.readouterr().out
    assert run("add", "cron:0 9 * * *", "check the pace", "--missed", "once") == 0
    assert "waits for the operator's acceptance" in capsys.readouterr().out
    assert run("accept", "e-0123456789ab") == 0
    assert run("decline", "e-0123456789ab") == 0
    assert sent[-2:] == [{"op": "entry_decide", "id": "e-0123456789ab", "accept": True},
                         {"op": "entry_decide", "id": "e-0123456789ab", "accept": False}]


def test_a_reminder_always_waits_and_never_wakes_the_session(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """A reminder is for the operator, so it waits for the operator's acceptance even from a clean
    context, and the scheduler never raises pd_entry_due for it, accepted or not: the sender sends
    it (the scheduler design, 4.3)."""
    import os

    from channel_receiver import ChannelReceiver
    from macf.agent_events_log import append_event
    from macf.notify.session import proc_start
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from test_pd_schedule import CARD, Log, at, make_scheduler
    from test_primal_daemon import ask, make_home
    daemon = run_daemon(make_home(tmp_path, []), base)
    me = (os.getpid(), proc_start(os.getpid()))
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: me)
    append_event("session_started", {"session_id": "s"})
    made = ask(daemon, {"op": "entry_add", "when": "in 20m", "purpose": "p", "action": "remind", "missed": "once"})
    assert made["entries"][-1]["state"] == "waiting" and made["entries"][-1]["marked"] == []

    log, now = Log(), [at("2026-10-19 12:00")]
    log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": new_entry_id(), "when": "cron:0 * * * *", "zone": "UTC",
                                   "start": "2026-10-19T11:30:00+00:00", "action": "remind", "missed": "once",
                                   "state": "active", "accepted_at": "2026-10-19T11:30:00+00:00"})
    channel = ChannelReceiver(tmp_path / "agent")
    make_scheduler(tmp_path, [], log, now, on_notice=channel).tick()
    assert channel.received == []


def test_pd_entry_show_prints_one_entry_in_full(monkeypatch, capsys):
    import argparse

    from macf.pd import cli, client
    from macf.pd.interface import Response
    sent = []
    held = {"id": "e-0123456789ab", "agent": "Tester@abc123", "action": "remind", "when": "cron:0 9 * * *",
            "purpose": "the weekly audit is due", "missed": "once", "state": "waiting", "marked": ["a web fetch"]}

    def ask(card, request, **kw):
        sent.append(request)
        return Response(ok=True, entries=[held])
    monkeypatch.setattr(client, "ask", ask)
    monkeypatch.setattr(cli, "_this_agent", lambda: (None, "Tester@abc123"))
    parser = argparse.ArgumentParser()
    cli.add_pd_parser(parser.add_subparsers(dest="cmd"))

    def run(*argv):
        args = parser.parse_args(["pd", "entry", *argv])
        return args.func(args)
    assert run("show", "e-0123456789ab") == 0
    out = capsys.readouterr().out
    assert "the weekly audit is due" in out and "a web fetch" in out and "waiting" in out
    assert run("show", "e-000000000000") == 1 and "no entry" in capsys.readouterr().err
    assert run("add", "in 20m", "p", "--remind", "--missed", "once") == 0
    assert sent[-1]["action"] == "remind"
    assert run("add", "in 20m", "p", "--check", "count", "--arg", "n=3", "--arg", "repo=o/r=x", "--missed", "once") == 0
    assert (sent[-1]["action"], sent[-1]["template"], sent[-1]["args"]) == ("check", "count", {"n": "3", "repo": "o/r=x"})
    assert run("add", "in 20m", "p", "--check", "count", "--remind", "--missed", "once") == 2
    assert run("add", "in 20m", "p", "--check", "count", "--arg", "n", "--missed", "once") == 2


def test_a_check_template_fills_whole_arguments_of_the_declared_kind():
    """Each slot takes one whole argv element of its declared kind, so text meant to splice in a
    second command is refused, and a template's slots must match its declared args (4.2)."""
    from pydantic import ValidationError

    from macf.pd.interface import CheckArg, CheckTemplate
    t = CheckTemplate(command=["gh", "issue", "view", "<issue>", "--repo", "<repo>"], wake_when="stdout", timeout_s=30,
                      args={"issue": CheckArg(kind="integer"), "repo": CheckArg(kind="pattern", pattern=r"[\w.-]+/[\w.-]+")})
    assert t.argv({"issue": "552", "repo": "o/r"}) == ["gh", "issue", "view", "552", "--repo", "o/r"]
    for bad in ({"issue": "552; curl x", "repo": "o/r"}, {"issue": "552", "repo": "o/r --web"}, {"issue": "552"}):
        with pytest.raises(ValueError):
            t.argv(bad)
    with pytest.raises(ValidationError):
        CheckTemplate(command=["gh", "<issue>"], wake_when="stdout", timeout_s=30, args={})
    with pytest.raises(ValidationError):
        CheckTemplate(command=["<prog>"], wake_when="stdout", timeout_s=30, args={"prog": CheckArg(kind="integer")})


def _not_writable(monkeypatch, *writable):
    """The test's interpreter, which the runner's account can usually write, is treated as the
    operator's: only the paths given read as writable by the agent."""
    from macf.pd import scheduler as sc
    monkeypatch.setattr(sc, "agent_can_write", lambda program: any(str(program).startswith(str(w)) for w in writable))


def _check_scheduler(tmp_path, log, now, templates, **options):
    from channel_receiver import ChannelReceiver
    from macf.pd import scheduler as sc
    from macf.pd.interface import Declaration
    from test_pd_schedule import CARD, ROUTED
    channel = ChannelReceiver(tmp_path / "agent")
    decl = Declaration(version=1, agent=CARD, timezone="UTC", notice_routes=ROUTED, check_templates=templates)
    s = sc.Scheduler(decl, CARD, {"agent_home": str(tmp_path / "home")}, work_dir=tmp_path / "runs",
                     append=log.append, events=log.read, now=lambda: now[0], on_notice=channel, **options)
    s.boot()
    return s, channel


def test_a_check_wakes_the_agent_only_when_its_condition_holds_and_keeps_what_it_said(tmp_path, monkeypatch):
    """A check entry runs its template at its time. Its firing wakes nobody; its run does, when
    the condition holds, and the output is kept for the agent. Nothing to say, no notice (4.2)."""
    import sys

    from macf.pd import scheduler as sc
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from macf.pd.interface import CheckArg, CheckTemplate
    from test_pd_schedule import CARD, Log, at, finish
    _not_writable(monkeypatch)
    template = CheckTemplate(command=[sys.executable, "-c", "import sys; print('moved' * int(sys.argv[1]))", "<n>"],
                             wake_when="stdout", timeout_s=10, args={"n": CheckArg(kind="integer")})
    log, now = Log(), [at("2026-10-19 12:00")]
    moved, quiet = new_entry_id(), new_entry_id()
    for entry_id, n in ((moved, "1"), (quiet, "0")):
        log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": "2026-10-19T12:00:00+00:00", "zone": "UTC",
                                       "start": "2026-10-19T11:00:00+00:00", "action": "check", "missed": "once",
                                       "template": "count", "args": {"n": n}, "state": "active"})
    s, channel = _check_scheduler(tmp_path, log, now, {"count": template})
    s.tick()
    assert channel.received == [] and set(s.running) == {moved, quiet}
    finish(s)
    assert channel.received == [("pd_entry_due", moved)]
    assert (tmp_path / "runs" / f"{moved}.out").read_text() == "moved\n"
    assert not (tmp_path / "runs" / f"{quiet}.out").exists()
    assert {d["schedule"]: d["wake"] for d in log.of(sc.EVENT_DONE)} == {moved: True, quiet: False}


def test_a_check_whose_program_the_agent_could_rewrite_or_that_changed_since_install_never_runs(tmp_path, monkeypatch):
    """A template whose program is in the agent's home, or one changed since pd install where
    that's checked, isn't started; the agent is told it failed (4.2)."""
    import sys

    from macf.pd import scheduler as sc
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from macf.pd.interface import CheckTemplate
    from test_pd_schedule import CARD, Log, at
    log, now = Log(), [at("2026-10-19 12:00")]
    _not_writable(monkeypatch, tmp_path)                       # what the agent can write: here, its tmp tree
    mine = CheckTemplate(command=[str(tmp_path / "home" / "bin" / "check")], wake_when="exit_code", timeout_s=10)
    fine = CheckTemplate(command=[sys.executable, "-c", "pass"], wake_when="exit_code", timeout_s=10)
    in_home, changed = new_entry_id(), new_entry_id()
    for entry_id, name in ((in_home, "mine"), (changed, "fine")):
        log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": "2026-10-19T12:00:00+00:00", "zone": "UTC",
                                       "start": "2026-10-19T11:00:00+00:00", "action": "check", "missed": "once",
                                       "template": name, "args": {}, "state": "active"})
    from macf.pd.interface import Declaration
    from test_pd_schedule import ROUTED
    installed = sc.schedule_digests(Declaration(version=1, agent=CARD, timezone="UTC", notice_routes=ROUTED,
                                                check_templates={"mine": mine}))
    log.append(sc.EVENT_INSTALLED, {"agent": CARD, "digests": {**installed, "template:fine": "an older digest"}})
    s, channel = _check_scheduler(tmp_path, log, now, {"mine": mine, "fine": fine}, check_installed=True)
    s.tick()
    assert s.running == {}
    outcomes = {d["schedule"]: d["outcome"] for d in log.of(sc.EVENT_DONE)}
    assert "can write" in outcomes[in_home] and "changed since the last pd install" in outcomes[changed]
    assert [source for source, _ in channel.received] == ["pd_run_failed", "pd_run_failed"]


def test_the_daemon_checks_a_check_entry_against_its_template_when_it_is_made(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """An unknown template, or arguments that don't fit, are refused when the entry is made. A
    check from a marked context waits even as a one-shot, since it runs a command (4.2, 5.3)."""
    import os
    import sys

    from macf.agent_events_log import append_event
    from macf.notify.session import proc_start
    from macf.pd import scheduler as sc
    from macf.pd.interface import CheckArg, CheckTemplate, Declaration, declaration_path
    from test_primal_daemon import CARD, ask, make_home
    home = make_home(tmp_path, [])
    _not_writable(monkeypatch)
    template = CheckTemplate(command=[sys.executable, "-c", "pass", "<n>"], wake_when="exit_code", timeout_s=10,
                             args={"n": CheckArg(kind="integer")})
    decl = Declaration(version=1, agent=CARD, check_templates={"count": template})
    declaration_path(home).write_text(decl.model_dump_json())
    append_event(sc.EVENT_INSTALLED, {"agent": CARD, "digests": sc.schedule_digests(decl)})
    daemon = run_daemon(home, base)
    me = (os.getpid(), proc_start(os.getpid()))
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: me)
    append_event("session_started", {"session_id": "s"})

    def add(**fields):
        return ask(daemon, {"op": "entry_add", "when": "in 20m", "purpose": "p", "action": "check", "missed": "once",
                            **fields})
    assert "no check template 'other'" in add(template="other")["error"]
    assert "don't fit" in add(template="count", args={"n": "1; rm"})["error"]
    clean = add(template="count", args={"n": "3"})["entries"][-1]
    assert (clean["state"], clean["template"], clean["args"]) == ("active", "count", {"n": "3"})
    append_event("tool_call_started", {"tool": "WebFetch", "session_id": "s"})
    assert add(template="count", args={"n": "3"})["entries"][-1]["state"] == "waiting"


def test_an_entry_is_removed_by_the_agent_or_the_operator_and_stops(tmp_path, base, run_daemon, isolated_events_log,
                                                                     monkeypatch, capsys):
    """Removing only stops work, so the agent's session and the operator outside it may both
    remove an entry; it leaves the log's fold and the scheduler, and an unknown id is refused."""
    import argparse
    import os

    from macf.notify.session import proc_start
    from macf.pd import cli, client
    from test_primal_daemon import ask, make_home
    daemon = run_daemon(make_home(tmp_path, []), base)
    session = [(os.getpid(), proc_start(os.getpid()))]
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: session[0])
    add = {"op": "entry_add", "when": "cron:0 9 * * *", "purpose": "p", "action": "wake", "missed": "once"}
    first = ask(daemon, add)["entries"][-1]["id"]
    second = ask(daemon, add)["entries"][-1]["id"]
    gone = ask(daemon, {"op": "entry_remove", "id": first})            # from the session
    assert gone["ok"] and [e["id"] for e in gone["entries"]] == [second] and first not in daemon.scheduler.entries
    session[0] = None                                                   # the operator, outside it
    assert ask(daemon, {"op": "entry_remove", "id": second})["entries"] == []
    assert second not in daemon.scheduler.entries
    assert "no entry" in ask(daemon, {"op": "entry_remove", "id": second})["error"]

    sent = []
    monkeypatch.setattr(client, "ask", lambda card, request, **kw: sent.append(request) or
                        __import__("macf.pd.interface", fromlist=["Response"]).Response(ok=True, entries=[]))
    monkeypatch.setattr(cli, "_this_agent", lambda: (None, "Tester@abc123"))
    parser = argparse.ArgumentParser()
    cli.add_pd_parser(parser.add_subparsers(dest="cmd"))
    args = parser.parse_args(["pd", "entry", "remove", "e-0123456789ab"])
    assert args.func(args) == 0 and sent == [{"op": "entry_remove", "id": "e-0123456789ab"}]


def test_ps_lines_without_a_terminal_read_as_none(monkeypatch):
    """Linux writes ? and macOS ?? for a process with no controlling terminal; both read as None."""
    import subprocess

    from macf.pd import daemon as pd_daemon

    class Done:
        stdout = "  1     0 ?        systemd\n 42     1 ??       launchd job\n 77    42 pts/2    -bash\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Done())
    assert pd_daemon.process_table() == {1: {"ppid": 0, "tty": None, "comm": "systemd"},
                                         42: {"ppid": 1, "tty": None, "comm": "launchd job"},
                                         77: {"ppid": 42, "tty": "pts/2", "comm": "-bash"}}


def test_a_program_counts_as_writable_by_its_file_or_its_folder(tmp_path):
    """The agent could rewrite a program it can write, or replace one in a folder it can write;
    a root-owned program in a root-owned folder is neither (MIS-0002-R143)."""
    import os
    import stat

    from macf.pd.scheduler import agent_can_write
    mine = tmp_path / "check"
    mine.write_text("#!/bin/sh\n")
    assert agent_can_write(mine)
    readonly = tmp_path / "readonly"                     # can't be written, but its folder can
    readonly.write_text("x")
    readonly.chmod(stat.S_IRUSR | stat.S_IXUSR)
    assert agent_can_write(readonly) or os.geteuid() == 0
    locked = tmp_path / "locked"
    locked.mkdir()
    prog = locked / "tool"
    prog.write_text("x")
    prog.chmod(stat.S_IRUSR | stat.S_IXUSR)
    open_file = locked / "open"                      # writable itself, in a folder that isn't
    open_file.write_text("x")
    locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        if os.geteuid() != 0:                     # root can write anything, so the check is moot there
            assert not agent_can_write(prog)
            assert agent_can_write(open_file)
    finally:
        locked.chmod(stat.S_IRWXU)
    assert not agent_can_write(__import__("pathlib").Path("/bin/sh").resolve()) or os.geteuid() == 0


def test_a_template_must_name_its_program_by_absolute_path(tmp_path, monkeypatch):
    from macf.pd.interface import CheckTemplate
    from test_pd_schedule import Log, at
    _not_writable(monkeypatch)
    bare = CheckTemplate(command=["gh", "api", "x"], wake_when="stdout", timeout_s=10)
    s, _ = _check_scheduler(tmp_path, Log(), [at("2026-10-19 12:00")], {"bare": bare})
    assert "absolute path" in s.template_refusal("bare", {})
