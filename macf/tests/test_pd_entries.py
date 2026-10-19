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
    """The daemon takes an entry request only from a process below the session unit: with
    no session, or from outside it, the request is refused and nothing is recorded. From the
    session, the entry is recorded with its time fixed, and listed (the scheduler design, 1)."""
    import os

    from macf.notify.session import proc_start
    from test_primal_daemon import ask, make_home
    daemon = run_daemon(make_home(tmp_path, []), base)
    add = {"op": "entry_add", "when": "in 20m", "purpose": "check the pace", "action": "wake", "missed": "once"}
    refused = ask(daemon, add)
    assert not refused["ok"] and "live session" in refused["error"]
    assert ask(daemon, {"op": "entry_list"})["ok"] is False

    me = (os.getpid(), proc_start(os.getpid()))            # this test stands in for the session
    monkeypatch.setattr(daemon.core, "session_incarnation", lambda: me)
    made = ask(daemon, add)
    assert made["ok"] and len(made["entries"]) == 1
    entry = made["entries"][0]
    assert ENTRY_ID.match(entry["id"]) and entry["purpose"] == "check the pace"
    assert entry["when"] == entry["first"]                  # "in 20m" fixed at its instant
    assert ask(daemon, {"op": "entry_list"})["entries"] == [entry]
