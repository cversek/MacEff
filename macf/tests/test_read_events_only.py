"""read_events(only=...): skip the lines that cannot be a named event.

Parsing is most of what a scan costs, and a question about one kind of event
used to parse every event between here and its answer. These tests hold the
filter to the unfiltered read: the same events, in the same order, and the
cycle boundary still stops a cycle-scoped read when the boundary itself is not
one of the names asked for.
"""
import json

import pytest

from macf.agent_events_log import CYCLE_BOUNDARY_EVENT, read_events, shared_event_reads


def _ev(event, ts, **data):
    return {"timestamp": ts, "event": event, "breadcrumb": "", "data": data}


@pytest.fixture
def log(isolated_events_log):
    records = [
        _ev("mode_change", 100, mode="AUTO_MODE", enabled=True),
        _ev("tool_call", 101, name="old"),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
        _ev("tool_call", 201, name="new"),
        # names the event it is not, inside its data: a line the filter parses and drops
        _ev("cli_command_invoked", 202, argv=["events", "query", "--event", "mode_change"]),
        _ev("mode_change", 203, mode="USER_REMOTE", enabled=True),
        _ev("tool_call", 204, name="newest"),
    ]
    with open(isolated_events_log, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return isolated_events_log


@pytest.mark.parametrize("scope", ["cycle", "all"])
@pytest.mark.parametrize("reverse", [True, False])
def test_the_same_events_in_the_same_order_as_filtering_an_unfiltered_read(log, scope, reverse):
    names = {"mode_change", "tool_call"}
    expected = [e for e in read_events(reverse=reverse, scope=scope) if e["event"] in names]
    assert expected, "the fixture must hold events of the named kinds"
    assert list(read_events(reverse=reverse, scope=scope, only=names)) == expected


def test_the_boundary_still_stops_a_cycle_read_when_it_is_not_named(log):
    seen = [(e["event"], e["timestamp"]) for e in read_events(scope="cycle", only=["mode_change"])]
    assert seen == [("mode_change", 203)], "the mode_change before the boundary must not be read"


def test_a_line_that_only_mentions_a_name_is_not_yielded(log):
    seen = [e["event"] for e in read_events(scope="all", only=["mode_change"])]
    assert seen == ["mode_change", "mode_change"]


def test_a_shared_window_gives_the_same_answer(log):
    @shared_event_reads
    def inside():
        return list(read_events(scope="all", only=("mode_change",))), list(read_events(only="tool_call"))

    assert inside() == (list(read_events(scope="all", only=("mode_change",))),
                        list(read_events(only="tool_call")))
