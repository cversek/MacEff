"""`macf_tools events query`, the readable reader of the event log (MIS-0002 landing, Phase 10).

One line per event from a summary table with a generic fallback, every field under
``--verbose``, one JSON line per event under ``--json``. Times are given as 30m, 2h, 09:00, an
ISO time or an epoch. A scan bounded by ``--after`` stops at the cutoff instead of reading the
whole log, and ``--follow`` prints events as they are appended.
"""
import argparse
import json
import time
from datetime import datetime, timezone

import pytest

from macf.eventlog import reader as rd


def ev(name, ts, **data):
    return {"timestamp": ts, "event": name, "breadcrumb": "s_x/c_1/p_y/t_1", "data": data, "hook_input": {}}


# --- summaries ------------------------------------------------------------------------------

def test_each_wake_unit_and_notice_event_reads_as_a_line():
    cases = [
        (ev("pd_wake_sent", 0, ids=["msg-1", "msg-2"], chars=92), "mail: msg-1, msg-2"),
        (ev("pd_wake_held", 0, reason="dialog", waiting=2), "reason=dialog  waiting=2"),
        (ev("pd_unit_state", 0, unit="session", state="running", reason="first liveness", pid=7),
         "unit=session  state=running  reason=first liveness"),
        (ev("pd_unit_alive", 0, unit="session", pid=7, in_flight=0, waiting_on=None), "unit=session  pid=7  in_flight=0"),
        (ev("pd_control", 0, act="restart", unit="broker", asked_by="operator", reason="stuck"),
         "act=restart  unit=broker  asked_by=operator  reason=stuck"),
        (ev("pd_notice_delivered", 0, source="mail", via="channel", arrival_id="a1"), "source=mail  via=channel  arrival_id=a1"),
    ]
    for event, expected in cases:
        assert rd.summary_of(event) == expected, event["event"]


def test_an_event_without_an_entry_shows_its_first_fields_shortened():
    event = ev("something_new", 0, a=1, b="x" * 200, c=[1, 2], d={"k": 1}, e="not shown")
    text = rd.summary_of(event)
    assert text.startswith("a=1  b=" + "x" * 10) and "…" in text
    assert "c=[1, 2]" in text and 'd={"k": 1}' in text and "not shown" not in text


def test_a_line_carries_the_time_and_the_date_when_not_today():
    ts = datetime(2026, 10, 17, 9, 8, 49, tzinfo=timezone.utc).timestamp()
    event = ev("pd_wake_sent", ts, ids=["msg-1"])
    assert rd.format_line(event, timezone.utc, today=datetime(2026, 10, 17).date()) == "09:08:49  pd_wake_sent  mail: msg-1"
    assert rd.format_line(event, timezone.utc, today=datetime(2026, 10, 18).date()).startswith("10-17 09:08:49  ")


def test_verbose_shows_every_field():
    event = ev("pd_control", 0, act="stop", unit="broker", asked_by="operator", reason="r", peer="p")
    event["hook_input"] = {"tool_name": "Bash"}
    text = rd.format_verbose(event, timezone.utc)
    for field in ("breadcrumb: s_x/c_1/p_y/t_1", "act: stop", "unit: broker", "asked_by: operator",
                  "reason: r", "peer: p", 'hook_input: {"tool_name": "Bash"}'):
        assert field in text, field


# --- times ----------------------------------------------------------------------------------

def test_times_in_every_form_and_a_bad_one_refused():
    now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc).timestamp()
    assert rd.parse_when("30m", now) == now - 1800
    assert rd.parse_when("2h", now) == now - 7200
    assert rd.parse_when("7d", now) == now - 7 * 86400
    assert rd.parse_when("09:00", now, tz=timezone.utc) == now - 3 * 3600
    assert rd.parse_when("09:00:30", now, tz=timezone.utc) == now - 3 * 3600 + 30
    assert rd.parse_when("2026-10-17T11:00:00Z", now) == now - 3600
    assert rd.parse_when("1792245526.5", now) == 1792245526.5
    for bad in ("soon", "25:00", "30x", ""):
        with pytest.raises(ValueError):
            rd.parse_when(bad, now)


# --- selection ------------------------------------------------------------------------------

def test_a_time_bound_stops_the_scan_at_the_cutoff():
    now = 10_000.0
    newest_first = [ev("a", now - i) for i in range(0, 5000, 10)]       # 500 events, 10 s apart
    read = []

    def counted():
        for e in newest_first:
            read.append(e)
            yield e
    got = rd.select(counted(), after=now - 95)
    assert [e["timestamp"] for e in got] == [now - i for i in range(90, -1, -10)]   # oldest first
    assert len(read) < 20                       # stopped near the cutoff, not at the end of the log


def test_globs_limit_and_before():
    newest_first = [ev("pd_wake_sent", 50), ev("tool_call_started", 40), ev("pd_wake_held", 30),
                    ev("pd_unit_state", 20), ev("pd_wake_held", 10)]
    names = lambda es: [e["event"] for e in es]
    assert names(rd.select(newest_first, patterns=["pd_wake_*"])) == ["pd_wake_held", "pd_wake_held", "pd_wake_sent"]
    assert names(rd.select(newest_first, patterns=["pd_wake_*", "pd_unit_*"], limit=2)) == ["pd_wake_held", "pd_wake_sent"]
    assert names(rd.select(newest_first, before=30)) == ["pd_wake_held", "pd_unit_state"]


# --- the command ----------------------------------------------------------------------------

def _query(**kw):
    base = {"event": None, "cycle": None, "git_hash": None, "session": None, "prompt": None, "after": None,
            "before": None, "limit": None, "follow": False, "command": None, "verbose": False,
            "json_output": False}
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def log():
    from macf.agent_events_log import get_log_path
    path = get_log_path()
    now = time.time()
    events = [ev("pd_wake_held", now - 3600, reason="dialog", waiting=1),
              ev("pd_wake_sent", now - 600, ids=["msg-9"], chars=40),
              ev("tool_call_started", now - 300, tool="Bash"),
              ev("pd_unit_state", now - 60, unit="session", state="running", reason="ok")]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return path, events


def test_the_command_reads_globbed_events_after_a_time(log, capsys):
    from macf.cli import cmd_events_query
    assert cmd_events_query(_query(event=["pd_*"], after="30m")) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [l.split("  ")[1] for l in lines] == ["pd_wake_sent", "pd_unit_state"]
    assert lines[0].endswith("mail: msg-9")


def test_json_lines_are_the_events_and_limit_keeps_the_newest(log, capsys):
    from macf.cli import cmd_events_query
    _, events = log
    assert cmd_events_query(_query(json_output=True)) == 0
    assert [json.loads(l) for l in capsys.readouterr().out.splitlines()] == events
    assert cmd_events_query(_query(limit=1)) == 0
    assert capsys.readouterr().out.split("  ")[1] == "pd_unit_state"


def test_a_bad_time_is_refused_with_the_forms_it_takes(log, capsys):
    from macf.cli import cmd_events_query
    assert cmd_events_query(_query(after="yesterday-ish")) == 2
    assert "30m, 2h, 7d, 09:00" in capsys.readouterr().err


# --- follow ---------------------------------------------------------------------------------

def test_follow_yields_only_new_matching_events_and_waits_for_a_line_to_end(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_text(json.dumps(ev("pd_wake_sent", 1)) + "\n")              # already there: not followed
    new = ev("pd_wake_held", 2, reason="draft")
    steps = iter([
        lambda: path.open("a").write(json.dumps(ev("tool_call_started", 2)) + "\n" + json.dumps(new)[:20]),
        lambda: path.open("a").write(json.dumps(new)[20:] + "\n"),
    ])

    def sleep(_):
        next(steps)()
    got = rd.follow(path, lambda e: e["event"].startswith("pd_"), sleep=sleep)
    assert next(got) == new


def test_the_carried_notice_pointer_shows_what_it_says_it_will(capsys):
    """The pd_carried notice says its command shows what was carried, changed and lost: run the
    command exactly as the notice quotes it, and it does, an empty list included."""
    import re
    import shlex

    from macf.agent_events_log import get_log_path
    from macf.channels.maceff_channel import DAEMON_POINTERS
    from macf.cli import _build_parser
    path = get_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    older = ev("pd_carried", time.time() - 60, occasion="restart", carried=["old"], changed=[], lost=[])
    newest = ev("pd_carried", time.time(), occasion="compaction", carried=["amail-broker", "session"],
                changed=[], lost=["the session's working context (summarized)"])
    path.write_text(json.dumps(older) + "\n" + json.dumps(newest) + "\n")
    command = re.search(r"`(macf_tools events query[^`]*)`", DAEMON_POINTERS["pd_carried"]).group(1)
    args = _build_parser().parse_args(shlex.split(command)[1:])
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert "compaction" in out and "restart" not in out
    assert '"amail-broker"' in out and "changed: []" in out and "working context" in out


def test_a_carried_event_reads_as_its_occasion_and_counts():
    event = ev("pd_carried", 0, occasion="compaction", carried=["a", "b", "c"], changed=[], lost=["x"])
    assert rd.summary_of(event) == "compaction: carried 3, changed 0, lost 1"


def test_a_before_bound_reads_past_the_last_compaction(capsys):
    """Any time bound reads the whole log: an event before the last compaction is found by a
    query bounded only by --before (it once read the current cycle only)."""
    from macf.agent_events_log import get_log_path
    from macf.cli import cmd_events_query
    now = time.time()
    events = [ev("pd_wake_sent", now - 7200, ids=["msg-1"], chars=10),
              ev("compaction_detected", now - 3600, cycle=2, detection_method="hook"),
              ev("tool_call_started", now - 60, tool="Bash")]
    path = get_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    before = datetime.fromtimestamp(now - 5400).isoformat(timespec="seconds")
    assert cmd_events_query(_query(event=["pd_wake_sent"], before=before)) == 0
    assert "mail: msg-1" in capsys.readouterr().out


def test_follow_from_a_given_offset_yields_what_was_written_after_it(tmp_path):
    """An event written between the scan and the follow is not lost: follow can start at the
    byte the scan began from."""
    path = tmp_path / "log.jsonl"
    path.write_text(json.dumps(ev("a", 1)) + "\n")
    start = path.stat().st_size
    with path.open("a") as f:                    # written "during the scan"
        f.write(json.dumps(ev("b", 2)) + "\n")

    def stop_after_one_poll(_s, polls=[0]):
        polls[0] += 1
        if polls[0] > 1:
            raise KeyboardInterrupt

    got = []
    with pytest.raises(KeyboardInterrupt):
        for e in rd.follow(path, lambda e: True, sleep=stop_after_one_poll, start=start):
            got.append(e["event"])
    assert got == ["b"]


# --- the command's follow, through cmd_events_query ------------------------------------------

def _follow_once(monkeypatch):
    """The command's follow, polling once and then stopped as Ctrl+C stops it."""
    from functools import partial

    def stop_after_one_poll(_s, polls=[0]):
        polls[0] += 1
        if polls[0] > 1:
            raise KeyboardInterrupt

    monkeypatch.setattr(rd, "follow", partial(rd.follow, sleep=stop_after_one_poll, poll_s=0))


def _write_during_scan(monkeypatch, path, *events):
    """read_events, standing in for a scan during which ``events`` are written to the log: the
    scan reads what was there, then the events land before it returns."""
    import macf.agent_events_log as log_mod
    real = log_mod.read_events

    def scanning(*a, **kw):
        seen = list(real(*a, **kw))
        with path.open("a") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        return iter(seen)

    monkeypatch.setattr(log_mod, "read_events", scanning)


def test_follow_prints_an_event_written_while_the_scan_ran(log, capsys, monkeypatch):
    """The command measures where --follow starts before the scan, and passes it on: an event
    written during the scan is printed by the follow, not lost between the two."""
    from macf.cli import cmd_events_query
    path, _ = log
    _follow_once(monkeypatch)
    _write_during_scan(monkeypatch, path, ev("pd_wake_sent", time.time(), ids=["msg-during"], chars=5))
    assert cmd_events_query(_query(event=["pd_*"], follow=True)) == 0
    out = capsys.readouterr().out
    assert out.count("msg-during") == 1, out


def test_follow_holds_back_events_past_before(log, capsys, monkeypatch):
    """--before bounds the follow as it bounds the scan: an event stamped after it is not printed."""
    from macf.cli import cmd_events_query
    path, _ = log
    bound = time.time() - 30
    _follow_once(monkeypatch)
    _write_during_scan(monkeypatch, path,
                       ev("pd_wake_sent", bound - 10, ids=["msg-inside"], chars=5),
                       ev("pd_wake_sent", bound + 10, ids=["msg-past"], chars=5))
    before = datetime.fromtimestamp(bound).isoformat(timespec="seconds")
    assert cmd_events_query(_query(event=["pd_wake_sent"], before=before, follow=True)) == 0
    out = capsys.readouterr().out
    assert "msg-inside" in out and "msg-past" not in out, out


def test_an_event_from_today_shows_no_date_in_either_form(log, capsys):
    """The default line and the verbose line both leave the date off an event from today."""
    from macf.cli import _pick_tz, cmd_events_query
    _, events = log
    tz = _pick_tz()
    moment = datetime.fromtimestamp(events[-1]["timestamp"], tz=tz)
    if moment.date() != datetime.now(tz=tz).date():
        pytest.skip("the fixture's newest event fell on yesterday; run again after midnight passes")
    clock = moment.strftime("%H:%M:%S")
    for verbose in (False, True):
        assert cmd_events_query(_query(event=["pd_unit_state"], verbose=verbose)) == 0
        first = capsys.readouterr().out.splitlines()[0]
        assert first.startswith(f"{clock}  pd_unit_state"), (verbose, first)
