"""A forensic query is bounded by the bound its caller supplied.

`read_events` defaults to cycle scope, and that default is correct: it is why
worst-case query cost is O(events in one cycle) rather than O(log). The default
was established by flipping it and letting the existing tests name the sites
that legitimately read for a lifetime.

`query_events` was not among them, and the reason is the point of this file: a
cross-cycle query that returns empty produces **no test failure**, so the
instrument used to enumerate those sites could not see this one. Measured on a
real log before the fix, a query for a cycle with 3,174 events on disk returned
47 -- not zero. A zero invites suspicion; a plausible count reads as an answer.

Both polarities are asserted here deliberately. Widening every query to lifetime
scope would make the first test pass and reintroduce exactly the unbounded scan
the cycle-scope default exists to prevent, so the control that an UNBOUNDED
filter stays cycle-scoped is what makes the first assertion mean anything.
"""
import json
import time

import pytest

from macf.agent_events_log import (
    CYCLE_BOUNDARY_EVENT,
    query_events,
    query_scope_for,
    set_log_path,
)


def _write_log(path, cycles=(20, 25, 30), per_cycle=4):
    """A log spanning several cycles, newest last, with real boundary events."""
    lines = []
    t = 1_000_000.0
    for ci, cycle in enumerate(cycles):
        # The boundary event OPENS the cycle it marks.
        lines.append({
            "timestamp": t, "event": CYCLE_BOUNDARY_EVENT,
            "breadcrumb": f"s_aaaa/c_{cycle}/p_bbbb/t_{int(t)}", "data": {},
        })
        t += 1
        for _ in range(per_cycle):
            lines.append({
                "timestamp": t, "event": "cli_command_invoked",
                "breadcrumb": f"s_aaaa/c_{cycle}/p_bbbb/t_{int(t)}", "data": {},
            })
            t += 1
    path.write_text("".join(json.dumps(rec) + "\n" for rec in lines))
    return cycles, per_cycle


@pytest.fixture
def log(tmp_path):
    p = tmp_path / "agent_events_log.jsonl"
    meta = _write_log(p)
    set_log_path(p)
    yield p, meta
    set_log_path(None)


@pytest.mark.parametrize("filters,expected", [
    ({"breadcrumb": {"c": 25}}, "all"),
    ({"breadcrumb": {"s": "aaaa"}}, "all"),
    ({"breadcrumb": {"g": "deadbee"}}, "all"),
    ({"breadcrumb": {"t_min": 1}}, "all"),
    ({"since": 1.0}, "all"),
    ({"until": 2.0}, "all"),
    ({"session_id": "abc"}, "all"),
    # Neither of these bounds how far back to read: they match in any cycle.
    ({"event_type": "cli_command_invoked"}, "cycle"),
    ({"without_matching": "x"}, "cycle"),
    ({}, "cycle"),
])
def test_scope_is_derived_from_the_bound_the_caller_supplied(filters, expected):
    assert query_scope_for(filters) == expected


def test_a_query_for_an_earlier_cycle_finds_it(log):
    """The defect this file exists for: the events are on disk and reachable."""
    _, (cycles, per_cycle) = log
    older = cycles[0]
    results = query_events({"breadcrumb": {"c": older}})
    # boundary event + the cycle's own events
    assert len(results) == per_cycle + 1
    assert all(f"c_{older}" in e["breadcrumb"] for e in results)


def test_an_unbounded_filter_stays_cycle_scoped(log):
    """CONTROL, opposite polarity -- without this the test above is vacuous.

    Widening every query to lifetime scope satisfies the previous test and
    reinstates the unbounded scan. This is the assertion that fails when that
    happens, and it is why the fix derives scope rather than removing it.
    """
    _, (cycles, per_cycle) = log
    results = query_events({"event_type": "cli_command_invoked"})
    assert len(results) == per_cycle, (
        "an unbounded filter read past the cycle boundary: the cycle-scope "
        "default was widened rather than derived"
    )
    newest = cycles[-1]
    assert all(f"c_{newest}" in e["breadcrumb"] for e in results)


def test_an_explicit_scope_overrides_the_derivation(log):
    """The override exists so a caller can say why at the site."""
    _, (cycles, per_cycle) = log
    wide = query_events({"event_type": "cli_command_invoked"}, scope="all")
    assert len(wide) == per_cycle * len(cycles)
    narrow = query_events({"breadcrumb": {"c": cycles[0]}}, scope="cycle")
    assert narrow == []
