"""Observations and operator surfaces cross a compaction (MIS-0002-R91).

The per-call line reads presence from the current cycle's events. An invitation made in
an earlier cycle has no events in this one, so it is carried at the boundary, as a mode
or a focus is. A carried invitation is the observed agent's consent, so it keeps the
cycle it was given in and never reads as fresh, and its lease runs from the original.
"""
import json
import time

from macf.agent_events_log import CYCLE_BOUNDARY_EVENT, append_event, read_events
from macf.cycle_carry import carry_state_forward
from macf.observe.acts import (
    ACTIVE,
    EVENT_END,
    EVENT_INVITE,
    EVENT_PAUSE,
    EVENT_RESUME,
    PAUSED,
    fold,
    lapsed,
)
from macf.observe.presence import DAEMON_START, EVENT_SURFACE, fold_surfaces

WATCHER = "Watcher@abc123"
OTHER = "Other@def456"


def _write(log, records):
    with open(log, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _ev(event, ts, **data):
    return {"timestamp": ts, "event": event, "breadcrumb": "", "data": data}


def _invite(ts, onlooker=WATCHER, **extra):
    return _ev(EVENT_INVITE, ts, onlooker=onlooker, observed="Host@0a0a0a", stream_from=10,
               secret_sha256="ab" * 32, cycle=1, **extra)


def _this_cycle():
    return list(read_events(reverse=False))


def test_an_open_observation_crosses_and_an_ended_one_does_not(isolated_events_log):
    _write(isolated_events_log, [
        _invite(100),
        _invite(101, onlooker=OTHER),
        _ev(EVENT_END, 102, onlooker=OTHER, ended_by="onlooker"),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
    ])

    assert "observation" in carry_state_forward(current_cycle=2)
    state = fold(_this_cycle())
    assert set(state) == {WATCHER}
    assert state[WATCHER].status == ACTIVE and state[WATCHER].stream_from == 10


def test_a_carried_invitation_keeps_its_origin_and_says_it_was_carried(isolated_events_log):
    _write(isolated_events_log, [_invite(100), _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2)])
    carry_state_forward(current_cycle=2)
    append_event(CYCLE_BOUNDARY_EVENT, {"cycle": 3})
    carry_state_forward(current_cycle=3)

    invites = [e for e in _this_cycle() if e["event"] == EVENT_INVITE]
    assert len(invites) == 1
    data = invites[0]["data"]
    assert (data["origin_cycle"], data["carried"], data["carried_into_cycle"]) == (1, True, 3)
    assert data["carried_from_timestamp"] == 100


def test_the_lease_runs_from_the_original_invitation(isolated_events_log):
    """A boundary never extends an invitation: a lease due a minute after it reads lapsed
    at that minute, and one already run out at the boundary isn't carried."""
    now = time.time()
    _write(isolated_events_log, [
        _invite(100, lease_until=now + 60),
        _invite(101, onlooker=OTHER, lease_until=now - 1),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
    ])
    carry_state_forward(current_cycle=2)

    state = fold(_this_cycle())
    assert set(state) == {WATCHER}
    assert not lapsed(state[WATCHER], now + 59) and lapsed(state[WATCHER], now + 61)


def test_a_pause_open_at_the_boundary_is_still_withheld_and_a_later_resume_closes_it(isolated_events_log):
    _write(isolated_events_log, [
        _invite(100),
        _ev(EVENT_PAUSE, 101, onlooker=WATCHER, by="observed", at=20),
        _ev(EVENT_RESUME, 102, onlooker=WATCHER, by="observed", at=30),
        _ev(EVENT_PAUSE, 103, onlooker=WATCHER, by="observed", at=40),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
    ])
    carry_state_forward(current_cycle=2)

    o = fold(_this_cycle())[WATCHER]
    assert o.status == PAUSED and o.pauses == ((20, 30), (40, None))
    append_event(EVENT_RESUME, {"onlooker": WATCHER, "by": "observed", "at": 50})
    o = fold(_this_cycle())[WATCHER]
    assert o.status == ACTIVE and o.pauses == ((20, 30), (40, 50))


def test_present_surfaces_cross_and_gone_or_superseded_ones_do_not(isolated_events_log):
    _write(isolated_events_log, [
        _ev(EVENT_SURFACE, 100, surface="old-daemon-terminal", state="attached"),
        _ev(DAEMON_START, 101),
        _ev(EVENT_SURFACE, 102, surface="terminal", state="attached"),
        _ev(EVENT_SURFACE, 103, surface="telegram", state="reachable"),
        _ev(EVENT_SURFACE, 104, surface="remote-control", state="enabled"),
        _ev(EVENT_SURFACE, 105, surface="remote-control", state="gone"),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
    ])

    assert "surface" in carry_state_forward(current_cycle=2)
    assert fold_surfaces(_this_cycle()) == {"terminal": "attached", "telegram": "reachable"}


def test_the_carry_names_the_observe_events_it_folds():
    """The carry names these events rather than importing the observe package at module
    load; a renamed event would otherwise stop crossing without a word."""
    from macf.cycle_carry import OBSERVE_EVENTS
    assert OBSERVE_EVENTS == {EVENT_INVITE, EVENT_PAUSE, EVENT_RESUME, EVENT_END, EVENT_SURFACE, DAEMON_START}


def test_a_malformed_invitation_costs_only_itself(isolated_events_log, capsys):
    """A row that won't parse is skipped, with a line saying so, and the good invitation
    beside it still folds and still carries; the carry still writes its marker."""
    _write(isolated_events_log, [
        _ev(EVENT_INVITE, 99, onlooker=OTHER),
        {"timestamp": 99.5, "event": EVENT_INVITE, "breadcrumb": "", "data": None},
        {"timestamp": 99.7, "event": EVENT_INVITE, "breadcrumb": "", "data": ["not", "a", "dict"]},
        _invite(100),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
    ])

    assert "observation" in carry_state_forward(current_cycle=2)
    assert set(fold(_this_cycle())) == {WATCHER}
    assert any(e["event"] == "state_carried" for e in _this_cycle())
    assert "skipped" in capsys.readouterr().err


def test_malformed_surfaces_and_onlookers_cost_only_themselves_and_the_carry_completes(isolated_events_log, capsys):
    """A surface row whose data isn't a mapping, a surface named by a list, and invitations
    whose onlooker is a list or missing are each skipped with a line saying so. The good
    surface and invitation beside them still carry, and the marker says the carry is
    complete, so the next boundary does not walk back into the same rows again."""
    _write(isolated_events_log, [
        _ev(EVENT_SURFACE, 100, surface="terminal", state="attached"),
        {"timestamp": 101, "event": EVENT_SURFACE, "breadcrumb": "", "data": ["bad"]},
        _ev(EVENT_SURFACE, 102, surface=["unhashable"], state="attached"),
        _invite(103),
        _invite(104, onlooker=["also", "unhashable"]),
        _ev(EVENT_INVITE, 105, observed="Host@0a0a0a", stream_from=10, secret_sha256="cd" * 32),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
    ])

    assert {"observation", "surface"} <= set(carry_state_forward(current_cycle=2))
    assert set(fold(_this_cycle())) == {WATCHER}
    assert fold_surfaces(_this_cycle()) == {"terminal": "attached"}
    marker = [e for e in _this_cycle() if e["event"] == "state_carried"][-1]["data"]
    assert marker["complete"] is True
    assert capsys.readouterr().err.count("skipped a malformed") >= 4


def test_a_malformed_reinvitation_does_not_drop_the_good_one_from_the_carry(isolated_events_log):
    """The carry keeps a row only once it folds, so a bad re-invitation for the same onlooker
    can't replace the good one: the per-call line said they were watching before the
    boundary, and it says so after."""
    _write(isolated_events_log, [
        _invite(100),
        _ev(EVENT_INVITE, 101, onlooker=WATCHER, observed="Host@0a0a0a"),   # no offset or secret
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
    ])

    assert "observation" in carry_state_forward(current_cycle=2)
    state = fold(_this_cycle())
    assert set(state) == {WATCHER} and state[WATCHER].stream_from == 10


def test_a_family_that_raises_is_reported_failed_and_the_carry_still_finishes(isolated_events_log, monkeypatch, capsys):
    """For a row shape nobody has thought of yet: an exception in the observation or surface
    family is that family's failure, said on stderr. The carry still writes its marker, so
    the session-start hook keeps its recovery output instead of reporting a hook error."""
    from macf import cycle_carry

    def boom(*args, **kwargs):
        raise RuntimeError("a shape nobody thought of")
    monkeypatch.setattr(cycle_carry, "_open_observations", boom)
    monkeypatch.setattr(cycle_carry, "_present_surfaces", boom)
    _write(isolated_events_log, [_invite(100), _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2)])

    carry_state_forward(current_cycle=2)
    marker = [e for e in _this_cycle() if e["event"] == "state_carried"][-1]["data"]
    assert marker["complete"] is False
    err = capsys.readouterr().err
    assert "observation" in err and "surface" in err and "a shape nobody thought of" in err


def test_a_lease_that_is_not_a_time_costs_only_its_own_invitation(isolated_events_log, capsys):
    """CTB's probe: a lease the carry can't compare with the clock is skipped where it folds,
    so the two good consents beside it still cross. Taken as given, it raised in the carry
    and the family guard then dropped every open observation."""
    _write(isolated_events_log, [
        _invite(100),
        _invite(101, onlooker=OTHER),
        _invite(102, onlooker="Third@aaa111", lease_until="soon"),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
    ])

    assert "observation" in carry_state_forward(current_cycle=2)
    assert set(fold(_this_cycle())) == {WATCHER, OTHER}
    assert "lease_until must be a time" in capsys.readouterr().err


def test_a_lease_that_ran_out_before_the_boundary_is_ended_by_the_carry(isolated_events_log):
    """The head maintainer's review on #817: a lease that lapses and then meets a compaction
    before the daemon's next sweep was left open forever, since the carry dropped it and the
    sweep reads only the new cycle. The carry now writes the lease's ending on the way out,
    with no daemon running, so the log read across cycles says it ended (MIS-0002-R89)."""
    now = time.time()
    _write(isolated_events_log, [
        _invite(100, lease_until=now - 5),
        _ev(CYCLE_BOUNDARY_EVENT, 200, cycle=2),
    ])
    carry_state_forward(current_cycle=2)

    ends = [e["data"] for e in read_events(reverse=False, scope="all") if e["event"] == EVENT_END]
    assert [(d["onlooker"], d["ended_by"]) for d in ends] == [(WATCHER, "lease")]
    assert fold(read_events(reverse=False, scope="all"))[WATCHER].status == "ended"
    append_event(CYCLE_BOUNDARY_EVENT, {"cycle": 3})    # the next compaction owes nothing more
    carry_state_forward(current_cycle=3)
    assert len([e for e in read_events(reverse=False, scope="all") if e["event"] == EVENT_END]) == 1
