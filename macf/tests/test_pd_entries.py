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
    assert log.of(sc.EVENT_ENTRY_FIRED)[0]["late_s"] == 3 * 3600.0     # R34: due 09:00, fired 12:00
    now[0] = at("2026-10-19 12:20")
    s.tick()
    assert channel.received[-1] == ("pd_entry_due", once)
    restarted = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    restarted.tick()
    assert len(channel.received) == 2                          # nothing fires again


def test_a_recurring_entry_first_fires_one_step_after_it_is_made(tmp_path):
    """A recurrence counts its start as its first occurrence, and an entry's start is the moment
    it was made. The scheduler fires the first occurrence strictly after that, as the list and
    show views say, never the instant the entry is added (a trial finding, 20 October)."""
    from channel_receiver import ChannelReceiver
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from test_pd_schedule import CARD, Log, at, make_scheduler
    log, now = Log(), [at("2026-10-19 12:00")]
    entry_id = new_entry_id()
    log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": "rrule:FREQ=MINUTELY;INTERVAL=50",
                                   "zone": "UTC", "start": "2026-10-19T12:00:00+00:00", "action": "wake",
                                   "missed": "skip"})
    channel = ChannelReceiver(tmp_path / "agent")
    s = make_scheduler(tmp_path, [], log, now, on_notice=channel)
    s.tick()
    assert channel.received == []                              # made at 12:00: nothing due yet
    now[0] = at("2026-10-19 12:50")
    s.tick()
    assert channel.received == [("pd_entry_due", entry_id)]


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


def test_an_entry_from_a_tainted_context_is_marked(tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """After the session read untrusted input, an entry is made marked, with why; from a clean
    context it's unmarked. Marking is provenance: the operator's consent is the ask prompt on
    pd entry add, met before the request (the scheduler design, 5.3, as ruled on #744)."""
    import os

    from macf.agent_events_log import append_event
    from macf.notify.session import proc_start
    from test_primal_daemon import ask, make_home
    daemon = run_daemon(make_home(tmp_path, []), base)
    me = (os.getpid(), proc_start(os.getpid()))
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: me)

    def add(when):
        return ask(daemon, {"op": "entry_add", "when": when, "purpose": "p", "action": "wake", "missed": "once"})["entries"][-1]
    append_event("session_started", {"session_id": "s"})
    assert add("cron:0 9 * * *")["marked"] == []
    append_event("tool_call_started", {"tool": "WebFetch", "session_id": "s"})
    made = add("cron:0 9 * * *")
    assert made["marked"] == ["a web fetch"] and "state" not in made


def test_pd_entry_show_prints_one_entry_in_full(monkeypatch, capsys):
    import argparse

    from macf.pd import cli, client
    from macf.pd.interface import Response
    sent = []
    held = {"id": "e-0123456789ab", "agent": "Tester@abc123", "action": "wake", "when": "cron:0 9 * * *",
            "purpose": "the weekly audit is due", "missed": "once", "marked": ["a web fetch"]}

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
    assert "the weekly audit is due" in out and "a web fetch" in out
    assert run("show", "e-000000000000") == 1 and "no entry" in capsys.readouterr().err
    assert run("add", "in 20m", "p", "--missed", "once") == 0
    assert sent[-1]["action"] == "wake"
    with pytest.raises(SystemExit):                  # the operator sender was withdrawn (MIS-0002 revision)
        run("add", "in 20m", "p", "--remind", "--missed", "once")
    assert run("add", "in 20m", "p", "--check", "count", "--arg", "n=3", "--arg", "repo=o/r=x", "--missed", "once") == 0
    assert (sent[-1]["action"], sent[-1]["template"], sent[-1]["args"]) == ("check", "count", {"n": "3", "repo": "o/r=x"})
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


def test_a_check_argument_with_a_brace_is_refused_even_by_a_loose_pattern():
    """A run renders its command's placeholders after the slots are filled, so a value holding
    {agent_home} would become a value the pattern never checked. Braces are refused whatever the
    pattern, and each slot still fills one whole argument of its kind (R143)."""
    from macf.pd.interface import CheckArg, CheckTemplate
    t = CheckTemplate(command=["/bin/echo", "<text>"], wake_when="stdout", timeout_s=30,
                      args={"text": CheckArg(kind="pattern", pattern=r".+")})
    assert t.argv({"text": "plain"}) == ["/bin/echo", "plain"]
    for bad in ("{agent_home}", "x}", "{"):
        with pytest.raises(ValueError):
            t.argv({"text": bad})


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
    log, now = Log(), [at("2026-10-19 12:05")]           # five minutes late, which the done record states
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
    # A check run states how late it began, in the done record its notice points to (R34; #757 review).
    assert {d["schedule"]: d["late_s"] for d in log.of(sc.EVENT_DONE)} == {moved: 300.0, quiet: 300.0}


def test_a_late_check_whose_policy_is_report_is_reported_and_not_run(tmp_path, monkeypatch):
    """An entry's missed-run policy is once, skip or report (R25). A late check under "report"
    says it was missed and runs nothing: the agent hears of it, and no program starts."""
    import sys

    from macf.pd import scheduler as sc
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from macf.pd.interface import CheckArg, CheckTemplate
    from test_pd_schedule import CARD, Log, at
    _not_writable(monkeypatch)
    template = CheckTemplate(command=[sys.executable, "-c", "print('ran')", "<n>"],
                             wake_when="stdout", timeout_s=10, args={"n": CheckArg(kind="integer")})
    log, now = Log(), [at("2026-10-19 12:05")]           # five minutes late: past the grace
    entry_id = new_entry_id()
    log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": "2026-10-19T12:00:00+00:00", "zone": "UTC",
                                   "start": "2026-10-19T11:00:00+00:00", "action": "check", "missed": "report",
                                   "template": "count", "args": {"n": "1"}, "state": "active"})
    s, channel = _check_scheduler(tmp_path, log, now, {"count": template})
    s.tick()
    assert not s.running, "a reported check starts no run"
    assert channel.received == [("pd_entry_due", entry_id)]
    fired = log.of(sc.EVENT_ENTRY_FIRED)
    assert fired and fired[-1]["notified"] is True and fired[-1]["late_s"] == 300.0
    assert not (tmp_path / "runs" / f"{entry_id}.out").exists()


def test_a_check_whose_program_the_agent_could_rewrite_or_that_changed_since_install_never_runs(tmp_path, monkeypatch):
    """A template whose program is in the agent's home, or one changed since pd install where
    that's checked, isn't started; the agent is told it failed (4.2)."""
    import sys

    from macf.pd import scheduler as sc
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from macf.pd.interface import CheckTemplate
    from test_pd_schedule import CARD, Log, at
    log, now = Log(), [at("2026-10-19 12:05")]           # five minutes late, which the done record states
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
    # A check refused before it starts still states how late it was due (R34; #757 review).
    assert {d["schedule"]: d["late_s"] for d in log.of(sc.EVENT_DONE)} == {in_home: 300.0, changed: 300.0}
    assert [source for source, _ in channel.received] == ["pd_run_failed", "pd_run_failed"]


def test_the_daemon_checks_a_check_entry_against_its_template_when_it_is_made(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """An unknown template, or arguments that don't fit, are refused when the entry is made. A
    check from a marked context is made marked, as any entry is: marking is provenance, and the
    operator's consent is the ask prompt on pd entry add (4.2, 5.3, as ruled on #744)."""
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
    assert (clean["marked"], clean["template"], clean["args"]) == ([], "count", {"n": "3"})
    append_event("tool_call_started", {"tool": "WebFetch", "session_id": "s"})
    assert add(template="count", args={"n": "3"})["entries"][-1]["marked"] == ["a web fetch"]


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


def test_the_list_and_agenda_show_when_an_entry_next_fires_not_when_it_first_did():
    """An hourly entry made days ago shows its next hour, and a one-shot that has fired shows none."""
    from datetime import datetime, timezone

    from macf.pd.cli import _next, agenda_lines
    now = datetime(2026, 10, 20, 13, 5, tzinfo=timezone.utc)
    hourly = {"id": "e-000000000001", "when": "cron:29 * * * *", "zone": "UTC", "start": "2026-10-17T03:00:00+00:00",
              "first": "2026-10-17T03:29:00+00:00", "purpose": "check-in"}
    done = {"id": "e-000000000002", "when": "2026-10-19T09:00:00+00:00", "zone": "UTC",
            "start": "2026-10-19T08:00:00+00:00", "first": "2026-10-19T09:00:00+00:00", "purpose": "once"}
    assert _next(hourly, now) == "2026-10-20T13:29:00+00:00"
    assert _next(done, now) == "none"
    assert agenda_lines(None, [done, hourly], now)[0].startswith("2026-10-20T13:29:00+00:00  entry     e-000000000001")


def test_pd_entry_add_starts_in_ask_and_an_operator_who_loosens_it_keeps_that(tmp_path, monkeypatch):
    """Installing the mode's permissions puts pd entry add in ask, so approving its prompt is the
    operator's consent. One the operator has moved to allow is left there, at every later install,
    unlike the permanent lists (persistent_layer 10.6)."""
    import json

    from macf.utils import claude_settings as cs
    rule = "Bash(macf_tools pd entry add:*)"
    settings = tmp_path / "settings.local.json"
    settings.write_text(json.dumps({"permissions": {}}))
    monkeypatch.setattr(cs, "_read_settings", lambda root=None: (json.loads(settings.read_text()), settings))
    added = cs.ensure_mode_safety_permissions()
    assert rule in added["ask_added"] and rule in json.loads(settings.read_text())["permissions"]["ask"]
    loosened = json.loads(settings.read_text())
    loosened["permissions"]["ask"].remove(rule)
    loosened["permissions"]["allow"].append(rule)
    settings.write_text(json.dumps(loosened))
    cs.ensure_mode_safety_permissions()
    after = json.loads(settings.read_text())["permissions"]
    assert rule not in after["ask"] and rule in after["allow"]


def _live_session_daemon(tmp_path, base, run_daemon, monkeypatch, home=None):
    """A daemon whose live session is this test's process, so an entry request is taken."""
    import os

    from macf.notify.session import proc_start
    from test_primal_daemon import make_home
    daemon = run_daemon(home or make_home(tmp_path, []), base)
    me = (os.getpid(), proc_start(os.getpid()))
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: me)
    return daemon


def _entry_events():
    from macf.agent_events_log import read_events
    from macf.pd.entries import ENTRY_EVENTS
    return list(read_events(reverse=False, scope="all", only=ENTRY_EVENTS))


def test_an_entry_request_without_a_missed_run_policy_is_refused_at_the_socket(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """MIS-0002-R24 (schedule_MUST_declare_missed-run_policy), the entry half: from the live
    session, an entry_add that names no missed-run policy is refused at the daemon's socket,
    never given a default, and nothing is recorded. The same request naming one is made."""
    from test_primal_daemon import ask
    daemon = _live_session_daemon(tmp_path, base, run_daemon, monkeypatch)
    add = {"op": "entry_add", "when": "in 20m", "purpose": "check the pace", "action": "wake"}
    refused = ask(daemon, add)
    assert not refused["ok"] and "Field required" in refused["error"]
    assert _entry_events() == [] and ask(daemon, {"op": "entry_list"})["entries"] == []
    made = ask(daemon, {**add, "missed": "skip"})
    assert made["ok"] and [e["missed"] for e in made["entries"]] == ["skip"]


@pytest.mark.parametrize("permission", [
    {"permissions": {"allow": ["Bash"]}},
    {"allowed_tools": ["Bash(gh pr merge:*)"]},
    {"permission_mode": "bypassPermissions"},
])
def test_an_entry_request_carrying_a_permission_is_refused_at_the_socket(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch, permission):
    """MIS-0002-R31 (schedule_MUST_settle_permission_at_creation), the entry half: an entry
    carries no permission of its own. From the live session, an entry_add with a permission
    field, of any spelling, is refused at the daemon's socket and nothing is recorded."""
    from test_primal_daemon import ask
    daemon = _live_session_daemon(tmp_path, base, run_daemon, monkeypatch)
    add = {"op": "entry_add", "when": "in 20m", "purpose": "p", "action": "wake", "missed": "once"}
    refused = ask(daemon, {**add, **permission})
    assert not refused["ok"] and "request refused" in refused["error"]
    assert _entry_events() == []
    assert ask(daemon, add)["ok"]                         # the same entry, with no permission, is made


def test_an_entry_whose_missed_run_policy_is_not_listed_is_refused_at_the_socket(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """MIS-0002-R25 (missed-run_policy_MUST_be_listed), the entry half: from the live session,
    an entry_add whose missed-run policy is anything but once, skip or report, a schedule's
    policy name, a near spelling or an empty one among them, is refused at the daemon's socket
    and nothing is recorded. Each of the three listed values is made."""
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from test_primal_daemon import ask
    daemon = _live_session_daemon(tmp_path, base, run_daemon, monkeypatch)
    add = {"op": "entry_add", "when": "in 20m", "purpose": "p", "action": "wake"}
    for missed in ("run_once", "catch_up", "", "Once", "skip ", "report_only", "window", None):
        refused = ask(daemon, {**add, "missed": missed})
        assert not refused["ok"] and "request refused" in refused["error"], missed
    assert _entry_events() == [] and ask(daemon, {"op": "entry_list"})["entries"] == []
    for missed in ("once", "skip", "report"):
        assert ask(daemon, {**add, "missed": missed})["ok"], missed
    assert [e["data"]["missed"] for e in _entry_events() if e["event"] == EVENT_ENTRY_ADDED] == ["once", "skip", "report"]


def test_an_entry_that_fired_late_says_how_late_where_its_notice_points(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch, capsys):
    """MIS-0002-R34 (late_run_MUST_state_lateness), the entry half: an entry the daemon fires
    three hours late raises pd_entry_due, received through the MacEff channel's own record, and
    the command its pointer names, run with the notice's id, states the firing's instant and how
    late it fired. The lateness is read from the pd_entry_fired event, the log's only record."""
    import re
    import shlex
    from datetime import timedelta

    from macf.agent_events_log import append_event
    from macf.channels.maceff_channel import DAEMON_POINTERS, TAKES
    from macf.cli import _build_parser
    from macf.pd import cli, client
    from macf.pd import scheduler as sc
    from macf.pd.entries import EVENT_ENTRY_ADDED
    from test_pd_notice import _connect, _records
    from test_primal_daemon import CARD, make_home, wait_for
    home = make_home(tmp_path, [])
    entry_id = new_entry_id()
    due = (datetime.now(UTC) - timedelta(hours=3, minutes=5)).replace(microsecond=0)
    append_event(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": due.isoformat(), "zone": "UTC",
                                     "start": (due - timedelta(hours=1)).isoformat(), "first": due.isoformat(),
                                     "purpose": "the weekly audit is due", "action": "wake", "missed": "once"})
    daemon = _live_session_daemon(tmp_path, base, run_daemon, monkeypatch, home=home)
    assert wait_for(lambda: any(e["event"] == sc.EVENT_ENTRY_FIRED for e in _fired_events()))
    conn = _connect(daemon, takes=TAKES)
    [record] = [r for r in _records(conn) if r.source == "pd_entry_due"]
    conn.close()
    assert record.arrival_id == entry_id

    command = re.search(r"`(macf_tools pd entry show <id>)`", DAEMON_POINTERS["pd_entry_due"]).group(1)
    real_ask = client.ask
    monkeypatch.setattr(client, "ask", lambda card, request, **kw: real_ask(card, request, base=base, **kw))
    monkeypatch.setattr(cli, "_this_agent", lambda: (home, CARD))
    args = _build_parser().parse_args(shlex.split(command.replace("<id>", record.arrival_id))[1:])
    capsys.readouterr()
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert "the weekly audit is due" in out
    assert f"for {due.isoformat()}, fired 3h 5m late" in out, out


def test_the_last_firing_reads_on_time_within_the_grace_and_says_what_it_stood_for():
    """How entry show words a firing: on time within the scheduler's grace, late in days, hours
    and minutes past it, with the firings a late one stood for; an entry never fired says so."""
    from macf.pd.cli import _last_fired
    assert _last_fired(None) == "not yet"
    assert _last_fired({"for": "T", "late_s": 59.0, "missed": 0, "notified": True}) == "for T, on time"
    assert _last_fired({"for": "T", "late_s": 10800.0, "missed": 3, "notified": True}) == (
        "for T, fired 3h 0m late, standing for 3 earlier firing(s) missed")
    assert _last_fired({"for": "T", "late_s": 90000.0, "missed": 0, "notified": False}) == (
        "for T, fired 1d 1h 0m late; no wake was sent")
    assert "not recorded" in _last_fired({"for": "T", "late_s": None})


def _fired_events():
    from macf.agent_events_log import read_events
    from macf.pd import scheduler as sc
    return list(read_events(reverse=False, scope="all", only=(sc.EVENT_ENTRY_FIRED,)))


def test_entry_add_and_remove_are_events_and_a_restarted_scheduler_holds_their_fold(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    """MIS-0002-R131 (entry_MUST_be_events): each add and each remove asked at the daemon's
    socket is an event in the agent's log, and a daemon restarted from that log holds, in its
    scheduler, exactly the entries those events fold to."""
    from macf.pd.entries import EVENT_ENTRY_ADDED, EVENT_ENTRY_REMOVED, fold
    from test_primal_daemon import CARD, ask, make_home, wait_for
    home = make_home(tmp_path, [])
    first = _live_session_daemon(tmp_path, base, run_daemon, monkeypatch, home=home)
    add = {"op": "entry_add", "when": "cron:0 9 * * *", "purpose": "p", "action": "wake", "missed": "once"}
    a = ask(first, add)["entries"][-1]["id"]
    b = ask(first, {**add, "purpose": "kept"})["entries"][-1]["id"]
    assert ask(first, {"op": "entry_remove", "id": a})["ok"]
    events = _entry_events()
    assert [(e["event"], e["data"]["id"]) for e in events] == [
        (EVENT_ENTRY_ADDED, a), (EVENT_ENTRY_ADDED, b), (EVENT_ENTRY_REMOVED, a)]
    folded = fold(events, CARD)
    assert list(folded) == [b]

    first.stop()
    assert wait_for(lambda: not first.record_path.exists())
    second = run_daemon(home, base)
    assert set(second.scheduler.entries) == set(folded) == {b}
    assert second.scheduler.entries[b]["purpose"] == "kept"
    assert [e["id"] for e in ask(second, {"op": "entry_list"})["entries"]] == [b]


def test_a_check_runs_its_template_with_no_shell(tmp_path, monkeypatch):
    """MIS-0002-R143 (check_MUST_run_operator_template): the scheduler executes the template's
    argv directly, with no shell between, so shell syntax a filled argument carries reaches the
    program as one literal argument and runs nothing."""
    import shutil

    from macf.pd.entries import EVENT_ENTRY_ADDED
    from macf.pd.interface import CheckArg, CheckTemplate
    from test_pd_schedule import CARD, Log, at, finish
    _not_writable(monkeypatch)
    planted = tmp_path / "planted"
    word = f"x; touch {planted} $(touch {planted}) | cat"
    echo = shutil.which("echo", path="/usr/bin:/bin")
    template = CheckTemplate(command=[echo, "<word>"],
                             wake_when="stdout", timeout_s=10, args={"word": CheckArg(kind="pattern", pattern=r"[^\n]+")})
    log, now = Log(), [at("2026-10-19 12:00")]
    entry_id = new_entry_id()
    log.append(EVENT_ENTRY_ADDED, {"agent": CARD, "id": entry_id, "when": "2026-10-19T12:00:00+00:00", "zone": "UTC",
                                   "start": "2026-10-19T11:00:00+00:00", "action": "check", "missed": "once",
                                   "template": "echo", "args": {"word": word}, "state": "active"})
    s, channel = _check_scheduler(tmp_path, log, now, {"echo": template})
    s.tick()
    finish(s)
    assert channel.received == [("pd_entry_due", entry_id)]
    assert (tmp_path / "runs" / f"{entry_id}.out").read_text() == word + "\n"
    assert not planted.exists()


def test_pd_agenda_lists_both_tiers_each_marked(tmp_path, monkeypatch, capsys):
    """MIS-0002-R145 (agenda_MUST_list_both_tiers): pd agenda, the command, prints the declared
    schedules and the agent's own entries in one list, each line marked with its tier, and an
    entry made from a tainted context marked so."""
    import argparse

    from macf.pd import cli, client, core
    from macf.pd.interface import CommandRun, Declaration, MissedRunPolicy, Response, Schedule
    decl = Declaration(version=1, agent="Tester@abc123", timezone="UTC", notice_routes={"pd_run_failed": "agent"},
                       schedules=[Schedule(name="sweep", cron="0 13 * * *", missed_run=MissedRunPolicy(kind="skip"),
                                           target="isolated", run=CommandRun(command=["true"], wake_when="exit_code"),
                                           timeout_s=60)])
    entries = [{"id": "e-0123456789ab", "when": "cron:0 9 * * *", "zone": "UTC", "start": "2026-10-19T08:00:00+00:00",
                "first": "2026-10-19T09:00:00+00:00", "purpose": "check the pace", "marked": ["a web fetch"]}]
    sent = []
    monkeypatch.setattr(cli, "_this_agent", lambda: (tmp_path, "Tester@abc123"))
    monkeypatch.setattr(core, "load_declaration", lambda home, card: decl)
    monkeypatch.setattr(client, "ask", lambda card, request, **kw: sent.append(request) or Response(ok=True, entries=entries))
    parser = argparse.ArgumentParser()
    cli.add_pd_parser(parser.add_subparsers(dest="cmd"))
    args = parser.parse_args(["pd", "agenda"])
    assert args.func(args) == 0 and sent == [{"op": "entry_list"}]
    lines = capsys.readouterr().out.splitlines()
    tiers = {line.split()[1]: line for line in lines}
    assert set(tiers) == {"declared", "entry"} and len(lines) == 2
    assert "sweep" in tiers["declared"] and "0 13 * * *" in tiers["declared"]
    assert "e-0123456789ab" in tiers["entry"] and "[marked] check the pace" in tiers["entry"]


def test_setting_the_mode_puts_pd_entry_add_in_ask_unless_the_operator_allowed_it(tmp_path, monkeypatch, capsys):
    """MIS-0002-R146 (entry_add_MUST_start_in_ask): macf_tools mode set, the command, puts
    pd entry add in the client's ask list; once the operator has moved it to allow, a later
    mode set leaves it there."""
    import argparse
    import json

    from macf import cli as macf_cli
    from macf import modes
    from macf.transcript_monitor import daemon as tm
    from macf.utils import paths
    rule = "Bash(macf_tools pd entry add:*)"
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    settings = project / ".claude" / "settings.local.json"
    settings.write_text(json.dumps({"permissions": {}}))
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))       # the client's global settings, here
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setattr(paths, "find_project_root", lambda: project)
    monkeypatch.setattr(modes, "set_auto_mode", lambda **kw: (True, "AUTO_MODE set"))
    monkeypatch.setattr(macf_cli, "get_current_session_id", lambda: "s")
    monkeypatch.setattr(tm, "is_running", lambda: True)

    def mode_set():
        return macf_cli.cmd_mode_set(argparse.Namespace(mode="AUTO_MODE", auth_token="t"))
    assert mode_set() == 0
    permissions = json.loads(settings.read_text())["permissions"]
    assert rule in permissions["ask"] and rule not in permissions.get("allow", [])
    loosened = json.loads(settings.read_text())
    loosened["permissions"]["ask"].remove(rule)
    loosened["permissions"]["allow"].append(rule)
    settings.write_text(json.dumps(loosened))
    assert mode_set() == 0
    after = json.loads(settings.read_text())["permissions"]
    assert rule not in after["ask"] and rule in after["allow"]
