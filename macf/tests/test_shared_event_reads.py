"""One parse of the event log per hook invocation.

A hook asks the log many questions per call, and each used to stream the log
from its end: on a long cycle one PreToolUse call parsed the same events about
twenty-seven times. Inside shared_event_reads they share one parse. These tests
hold it to giving exactly what a streaming read gives.
"""
import importlib
import json
import pkgutil

import pytest

import macf.agent_events_log as ael
import macf.hooks
from macf.agent_events_log import (
    CYCLE_BOUNDARY_EVENT, append_event, read_events, shared_event_reads,
)


def _write(log, records):
    with open(log, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _ev(event, ts, **data):
    return {"timestamp": ts, "event": event, "breadcrumb": "", "data": data}


@pytest.fixture
def log(isolated_events_log):
    """Two cycles: fifty events before the boundary, fifty after."""
    records = [_ev("old", i, n=i) for i in range(50)]
    records.append(_ev(CYCLE_BOUNDARY_EVENT, 100, cycle=2))
    records += [_ev("new", 101 + i, n=i) for i in range(50)]
    _write(isolated_events_log, records)
    return isolated_events_log


@pytest.fixture
def parses(monkeypatch):
    """Counts the lines the shared window turns into events."""
    counted = []
    real = ael._parse

    def counting(line):
        event = real(line)
        if event is not None:
            counted.append(1)
        return event

    monkeypatch.setattr(ael, "_parse", counting)
    return counted


def _reads():
    """The questions a hook asks, in the shapes it asks them."""
    return {
        "cycle": [e["timestamp"] for e in read_events(reverse=True)],
        "all": [e["timestamp"] for e in read_events(reverse=True, scope="all")],
        "forward": [e["timestamp"] for e in read_events(reverse=False)],
        "first": next(e["timestamp"] for e in read_events(scope="all") if e["event"] == "old"),
    }


def test_shared_reads_give_what_streaming_reads_give_and_parse_once(log, parses):
    streamed = _reads()
    assert parses == [], "a read outside an invocation used the shared window"

    shared = shared_event_reads(_reads)()

    assert shared == streamed
    assert len(parses) == 101, f"parsed {len(parses)} events of a 101-event log"


def test_a_write_by_another_process_is_seen(log):
    @shared_event_reads
    def hook():
        next(read_events())
        with open(log, "a") as f:  # not append_event: someone else's write
            f.write(json.dumps(_ev("theirs", 999)) + "\n")
        return next(read_events())["event"]

    assert hook() == "theirs"


def test_our_own_append_extends_the_window_without_reading_it_again(log, parses):
    @shared_event_reads
    def hook():
        list(read_events(scope="all"))
        before = len(parses)
        append_event("ours", {"n": 1})
        newest = [e["event"] for e in read_events(scope="all")][:2]
        return newest, len(parses) - before

    newest, reparsed = hook()
    assert newest == ["ours", "new"]
    assert reparsed == 0, f"re-parsed {reparsed} lines after our own append"


def test_our_append_after_someone_elses_does_not_hide_theirs(log):
    """The window may take our record only if it had seen the file up to where
    the record begins; otherwise the other writer's line would be skipped."""
    @shared_event_reads
    def hook():
        next(read_events())
        with open(log, "a") as f:
            f.write(json.dumps(_ev("theirs", 999)) + "\n")
        append_event("ours", {"n": 1})
        return [e["event"] for e in read_events()][:3]

    assert hook() == ["ours", "theirs", "new"]


def test_a_cycle_read_stops_where_the_live_log_ends(isolated_events_log, monkeypatch):
    """No boundary in the live log: a cycle read ends with it, as the streaming
    path does, and never opens an archive; a lifetime read goes on into them."""
    _write(isolated_events_log, [_ev("a", 1), _ev("b", 2)])
    opened = []
    import macf.eventlog.archive as archive
    monkeypatch.setattr(archive, "select_archives", lambda p, *a, **k: opened.append(p) or [])

    @shared_event_reads
    def hook():
        cycle = [e["event"] for e in read_events()]
        after_cycle = len(opened)
        lifetime = [e["event"] for e in read_events(scope="all")]
        return {"cycle": cycle, "opened_by_cycle": after_cycle, "lifetime": lifetime}

    seen = hook()
    assert seen["cycle"] == ["b", "a"] and seen["lifetime"] == ["b", "a"]
    assert seen["opened_by_cycle"] == 0, "a cycle read opened the archives"
    assert len(opened) == 1


def test_past_the_cap_a_reader_still_gets_everything(log, monkeypatch):
    monkeypatch.setattr(ael, "SHARED_READ_CAP_BYTES", 1000)
    streamed = [e["timestamp"] for e in read_events(scope="all")]

    @shared_event_reads
    def hook():
        full = [e["timestamp"] for e in read_events(scope="all")]
        again = [e["timestamp"] for e in read_events(scope="all")]
        return {"full": full, "again": again, "stored": ael._shared.window.stored}

    seen = hook()
    assert seen["full"] == streamed and seen["again"] == streamed
    assert seen["stored"] < 1000 + 200, f"the window kept {seen['stored']} bytes past a 1000-byte cap"


def test_a_reader_that_changes_an_event_fails_the_invocation(log):
    @shared_event_reads
    def careless():
        next(read_events())["data"]["n"] = -1

    @shared_event_reads
    def careful():
        event = dict(next(read_events()))
        event["data"] = {**event["data"], "n": -1}

    with pytest.raises(AssertionError, match="modified 1 shared event"):
        careless()
    careful()


def test_every_hook_entry_point_shares_its_reads():
    """A new handler without the decorator would quietly keep the old cost."""
    names = [m.name for m in pkgutil.iter_modules(macf.hooks.__path__)
             if m.name.startswith("handle_")]
    assert len(names) >= 10, names
    bare = [n for n in names
            if getattr(importlib.import_module(f"macf.hooks.{n}"), "run", None) is not None
            and not getattr(importlib.import_module(f"macf.hooks.{n}").run, "shares_event_reads", False)]
    assert bare == [], f"hook entry points that read the log without sharing: {bare}"
