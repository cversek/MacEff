"""Cycle-scoped event reads, and the explicit carry that makes them honest.

A row limit is not a bound on a question. Removing the limits left one hazard —
a query for state that has NEVER been established scans the whole log — and a
limit answers that case wrongly rather than slowly. Cycle-scoping removes the
case instead of bounding it: worst-case cost is one cycle, and a miss means
exactly "not established in this cycle".

That is only true if state which legitimately outlives a cycle re-asserts itself
at the boundary. These tests cover both halves, because either half alone is
worse than neither: scoping without carrying drops the operator's authorisation,
and carrying without scoping is dead code.
"""

import json

import pytest

from macf.agent_events_log import CYCLE_BOUNDARY_EVENT, read_events
from macf.cycle_carry import carry_state_forward


def _write(log, records):
    """Write raw event records, bypassing append_event's breadcrumb machinery."""
    with open(log, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _ev(event, ts, **data):
    return {"timestamp": ts, "event": event, "breadcrumb": "", "data": data}


@pytest.fixture
def two_cycle_log(isolated_events_log):
    """A log holding two cycles, oldest first.

    old_mode is the trap: it is the same key as new_mode but on the far side of
    the boundary, so a scan that fails to stop will find it and report it as
    current.
    """
    _write(isolated_events_log, [
        _ev("mode_change", 100, mode="AUTO_MODE", enabled=True, cycle=1),
        _ev("tool_call", 101, name="old"),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
        _ev("tool_call", 201, name="new"),
        _ev("mode_change", 202, mode="USER_REMOTE", enabled=True, cycle=2),
    ])
    return isolated_events_log


class TestCycleScopedReads:

    def test_reverse_stops_at_the_boundary_and_includes_it(self, two_cycle_log):
        """The boundary opens the cycle it marks, so it is inside the window —
        callers read the cycle number off that very event."""
        seen = [e["event"] for e in read_events(reverse=True)]

        assert CYCLE_BOUNDARY_EVENT in seen
        assert "tool_call" in seen
        names = [e["data"].get("name") for e in read_events(reverse=True)
                 if e["event"] == "tool_call"]
        assert names == ["new"], "reached an event from the previous cycle"

    def test_forward_yields_the_same_window_in_order(self, two_cycle_log):
        """A forward reader gets the same bound as a reverse one. Exempting it
        would leave half the call sites unbounded while the API claimed
        otherwise."""
        forward = [e["timestamp"] for e in read_events(reverse=False)]
        reverse = [e["timestamp"] for e in read_events(reverse=True)]

        assert forward == sorted(forward), "forward reads must stay chronological"
        assert forward == list(reversed(reverse))
        assert min(forward) == 200, "forward read reached past the boundary"

    def test_scope_all_reads_the_whole_log(self, two_cycle_log):
        """Lifetime questions still have an answer — they just have to ask."""
        names = [e["data"].get("name") for e in read_events(reverse=True, scope="all")
                 if e["event"] == "tool_call"]
        assert names == ["new", "old"]

    def test_an_unrecognised_scope_is_refused(self, two_cycle_log):
        """A typo must not silently mean 'everything'. That is how the unbounded
        case comes back — quietly, through a caller that thought it was safe."""
        with pytest.raises(ValueError, match="scope"):
            list(read_events(scope="all_of_it"))

    def test_cost_does_not_grow_with_log_size(self, isolated_events_log):
        """The acceptance criterion, measured rather than asserted: ten thousand
        events BEFORE the boundary must not be touched by a cycle-scoped read."""
        records = [_ev("tool_call", i, name="ancient") for i in range(10_000)]
        records.append(_ev(CYCLE_BOUNDARY_EVENT, 20_000, cycle=2))
        records.extend(_ev("tool_call", 20_001 + i, name="recent") for i in range(3))
        _write(isolated_events_log, records)

        scanned = list(read_events(reverse=True))

        assert len(scanned) == 4, f"scanned {len(scanned)} events for a 4-event cycle"
        assert all(e["data"].get("name") != "ancient" for e in scanned
                   if e["event"] == "tool_call")


class TestCarryForward:

    def test_each_persistent_mode_carries_not_just_the_most_recent(self, isolated_events_log):
        """Keyed by mode, not by recency. Keying on recency alone would let a
        USER_REMOTE toggle silently drop AUTO_MODE — two modes, one slot."""
        _write(isolated_events_log, [
            _ev("mode_change", 100, mode="AUTO_MODE", enabled=True, cycle=1),
            _ev("mode_change", 101, mode="USER_REMOTE", enabled=True, cycle=1),
            _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
        ])

        carried = carry_state_forward(current_cycle=2)

        assert sorted(carried) == ["AUTO_MODE", "USER_REMOTE"]

    def test_a_carried_assertion_is_distinguishable_and_keeps_its_origin(self, isolated_events_log):
        """Provenance is the point. An authorisation granted in cycle 1 and
        carried into cycle 2 must not read as granted in cycle 2 — that is
        infrastructure manufacturing consent."""
        _write(isolated_events_log, [
            _ev("mode_change", 100, mode="AUTO_MODE", enabled=True, cycle=1),
            _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
        ])

        carry_state_forward(current_cycle=2)

        latest = next(e for e in read_events(reverse=True) if e["event"] == "mode_change")
        assert latest["data"]["carried"] is True
        assert latest["data"]["origin_cycle"] == 1
        assert latest["data"]["carried_into_cycle"] == 2

    def test_origin_survives_a_chain_of_carries(self, isolated_events_log):
        """The failure this prevents is cumulative: carried a hundred times, a
        grant that overwrote its own origin each hop would look current forever.
        """
        _write(isolated_events_log, [
            _ev("mode_change", 100, mode="AUTO_MODE", enabled=True,
                cycle=2, carried=True, origin_cycle=1),
            _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=3),
        ])

        carry_state_forward(current_cycle=3)

        latest = next(e for e in read_events(reverse=True) if e["event"] == "mode_change")
        assert latest["data"]["origin_cycle"] == 1, "the chain reported the last hop"
        assert latest["data"]["carried_into_cycle"] == 3

    def test_the_fold_covers_one_cycle_not_the_whole_log(self, isolated_events_log):
        """Bounded work at the boundary. A mode set two cycles ago and since
        turned off must not be resurrected by reaching further back."""
        _write(isolated_events_log, [
            _ev("mode_change", 50, mode="AUTO_MODE", enabled=True, cycle=1),
            _ev(CYCLE_BOUNDARY_EVENT, 100, cycle=2),
            _ev("mode_change", 150, mode="AUTO_MODE", enabled=False, cycle=2),
            _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=3),
        ])

        carry_state_forward(current_cycle=3)

        latest = next(e for e in read_events(reverse=True) if e["event"] == "mode_change")
        assert latest["data"]["enabled"] is False, "reached back past one cycle"

    def test_a_failed_carry_is_not_silence(self, isolated_events_log, capsys, monkeypatch):
        """An empty return has two opposite causes — nothing to carry, and every
        append failing. The return value cannot tell them apart, so the failure
        has to say so somewhere. Unreported, it drops the operator's
        authorisation at a boundary and looks exactly like a quiet cycle."""
        _write(isolated_events_log, [
            _ev("mode_change", 100, mode="AUTO_MODE", enabled=True, cycle=1),
            _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
        ])
        monkeypatch.setattr("macf.cycle_carry.append_event", lambda *a, **k: False)

        assert carry_state_forward(current_cycle=2) == []
        assert "carry-forward FAILED" in capsys.readouterr().err

    def test_nothing_to_carry_is_a_real_answer(self, isolated_events_log):
        """An empty carry is 'nothing persistent was set', not a failure. Saying
        so keeps a quiet cycle distinguishable from a broken fold."""
        _write(isolated_events_log, [
            _ev("tool_call", 100, name="x"),
            _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
        ])

        assert carry_state_forward(current_cycle=2) == []


class TestCarryGapIsLoud:

    def test_state_older_than_the_carry_is_found_and_reported(self, isolated_events_log, capsys):
        """The migration case: cycles that predate this change were never
        carried. Falling back silently would drop the operator's mode; falling
        back loudly makes the gap a queryable fact."""
        from macf import event_queries
        event_queries._carry_gaps_reported.clear()

        _write(isolated_events_log, [
            _ev("mode_change", 100, mode="AUTO_MODE", enabled=True, cycle=1),
            _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
        ])

        auto, source = event_queries.get_auto_mode_from_events("sess1234")

        assert auto is True, "the operator's mode was dropped at the boundary"
        assert source == "pre_carry_fallback"
        assert "not carried into this cycle" in capsys.readouterr().err
        assert any(e["event"] == "carry_forward_missing"
                   for e in read_events(reverse=True, scope="all"))

    def test_a_carried_mode_uses_the_normal_path(self, isolated_events_log):
        """The complement, so the fallback is shown to DISCRIMINATE rather than
        merely to fire. A check only ever seen firing has been shown to fire."""
        from macf import event_queries
        event_queries._carry_gaps_reported.clear()

        _write(isolated_events_log, [
            _ev("mode_change", 100, mode="AUTO_MODE", enabled=True, cycle=1),
            _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
            _ev("mode_change", 201, mode="AUTO_MODE", enabled=True,
                cycle=2, carried=True, origin_cycle=1),
        ])

        auto, source = event_queries.get_auto_mode_from_events("sess1234")

        assert (auto, source) == (True, "event")
        assert not any(e["event"] == "carry_forward_missing"
                       for e in read_events(reverse=True, scope="all"))
