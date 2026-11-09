"""A time floor on event reads, and a shared window that parses only what a reader wants (#881).

The budget's readers ask for a few events of one type within eight days, five or six times per
hook call. On a long-lived seat that window is tens of thousands of lines, and the shared read
parsed every one of them, about a second per tool call. ``since`` stops a reverse read at the
first line older than the floor, judged by the line's leading timestamp, and a reader asking for
some events only (``only=``) leaves the others' lines unparsed, in the shared window too.
"""
import json

import pytest

import macf.agent_events_log as ael
from macf.agent_events_log import read_events, shared_event_reads

DAY = 86400.0
NOW = 100 * DAY


def _write(log, records):
    with open(log, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _ev(event, ts, **data):
    return {"timestamp": ts, "event": event, "breadcrumb": "", "data": data}


@pytest.fixture
def month(isolated_events_log):
    """Thirty days of hourly events, with a rare one every fifth day."""
    records = []
    for h in range(30 * 24):
        ts = NOW - 30 * DAY + h * 3600
        records.append(_ev("rare" if h % (5 * 24) == 0 else "busy", ts, h=h))
    _write(isolated_events_log, records)
    return isolated_events_log


@pytest.fixture
def parses(monkeypatch):
    counted = []
    real = ael._parse

    def counting(line):
        event = real(line)
        if event is not None:
            counted.append(event["event"])
        return event

    monkeypatch.setattr(ael, "_parse", counting)
    return counted


def test_a_floor_yields_only_the_window_and_stops_there(month):
    floor = NOW - 7 * DAY
    got = list(read_events(reverse=True, scope="all", since=floor))
    assert got and all(e["timestamp"] >= floor for e in got)
    assert len(got) == 7 * 24


def _rare_within(floor):
    return [h for h in range(30 * 24) if h % (5 * 24) == 0 and NOW - 30 * DAY + h * 3600 >= floor][::-1]


def test_with_a_floor_a_streaming_read_for_a_rare_event_walks_only_the_window(month, monkeypatch):
    """With only= alone, a reader looking for a rare event walks back past the window for an
    old one. The floor stops the walk at the first line older than it."""
    floor = NOW - 7 * DAY
    judged = []
    real = ael._older
    monkeypatch.setattr(ael, "_older", lambda line, since: judged.append(1) or real(line, since))
    got = [e["data"]["h"] for e in read_events(reverse=True, scope="all", only=("rare",), since=floor)]
    assert got == _rare_within(floor)
    assert len(judged) == 7 * 24 + 1            # the window, and the one line that ends it


def test_in_a_shared_window_a_reader_parses_only_the_lines_it_wants(month, parses):
    floor = NOW - 7 * DAY
    got = shared_event_reads(lambda: [e["data"]["h"] for e in read_events(
        reverse=True, scope="all", only=("rare",), since=floor)])()
    assert got == _rare_within(floor)
    assert parses == ["rare"] * len(got)


def test_in_a_shared_window_each_reader_parses_only_what_it_wants_and_once(month, parses):
    floor = NOW - 7 * DAY

    @shared_event_reads
    def hook():
        a = list(read_events(reverse=True, scope="all", only=("rare",), since=floor))
        b = list(read_events(reverse=True, scope="all", only=("rare",), since=floor))
        return a, b

    a, b = hook()
    assert a == b and a
    assert parses == ["rare"] * len(a)          # parsed once, shared by the second reader


def test_a_line_written_another_way_is_still_judged_by_its_content(isolated_events_log):
    """A line whose keys come in another order has no leading timestamp or name to read, so it
    is parsed to judge it, in the shared window and outside it."""
    with open(isolated_events_log, "w") as f:
        f.write(json.dumps({"event": "rare", "timestamp": NOW - 9 * DAY, "data": {"h": 0}}) + "\n")
        f.write(json.dumps({"event": "rare", "timestamp": NOW - DAY, "data": {"h": 1}}) + "\n")
        f.write(json.dumps(_ev("busy", NOW, h=2)) + "\n")
    floor = NOW - 7 * DAY

    def read():
        return [e["data"]["h"] for e in read_events(reverse=True, scope="all", only=("rare",), since=floor)]

    assert read() == [1]
    assert shared_event_reads(read)() == [1]
