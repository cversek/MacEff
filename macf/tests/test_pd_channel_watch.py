"""A dark MacEff channel, derived by the daemon and told by the outside watch (MIS-0002-R115)."""
import json
import time
from dataclasses import dataclass, field

from macf.pd import watch
from macf.pd.channel_watch import DarkChannel
from macf.pd.interface import EVENT_CHANNEL_BACK, EVENT_CHANNEL_DARK

CARD = "Tester@abc123"
S1, S2 = (101, "start-1"), (202, "start-2")


@dataclass(frozen=True)
class Rig:
    """A tracker, what it said, and the clock it reads (a one-item list the test moves)."""
    t: DarkChannel
    said: list = field(default_factory=list)
    clock: list = field(default_factory=lambda: [0.0])


def _tracker(connect_s=60.0) -> Rig:
    said, clock = [], [0.0]
    t = DarkChannel(CARD, connect_s, append=lambda e, d: said.append((e, d)) or True, clock=lambda: clock[0])
    return Rig(t, said, clock)


def test_a_session_that_never_connects_goes_dark_once_past_its_window():
    rig = _tracker()
    t, said, clock = rig.t, rig.said, rig.clock
    t.tick(S1, False)
    clock[0] = 59.0
    t.tick(S1, False)
    assert said == [], "inside the declared window nothing is dark yet"
    clock[0] = 61.0
    t.tick(S1, False)
    clock[0] = 300.0
    t.tick(S1, False)
    assert [e for e, _ in said] == [EVENT_CHANNEL_DARK], "one event opens the stretch, no repeats"
    assert "within 60 s" in said[0][1]["reason"] and said[0][1]["session_pid"] == 101


def test_a_channel_that_drops_while_the_session_runs_is_dark_and_back_when_it_returns():
    rig = _tracker()
    t, said, clock = rig.t, rig.said, rig.clock
    t.tick(S1, True)
    clock[0] = 5.0
    t.tick(S1, False)
    t.tick(S1, False)
    clock[0] = 9.0
    t.tick(S1, True)
    assert [e for e, _ in said] == [EVENT_CHANNEL_DARK, EVENT_CHANNEL_BACK]
    assert "dropped" in said[0][1]["reason"]


def test_a_restart_is_not_a_dark_channel():
    """The old incarnation's channel goes with it; the new one starts its own window, and a
    dark stretch the restart ended is closed."""
    rig = _tracker()
    t, said, clock = rig.t, rig.said, rig.clock
    t.tick(S1, True)
    t.tick(None, False)                 # the session is between incarnations
    clock[0] = 10.0
    t.tick(S2, False)                   # a new incarnation, its channel not yet up
    assert said == [], "a restart dropped the channel; that is not dark"
    clock[0] = 100.0
    t.tick(S2, False)
    assert [e for e, _ in said] == [EVENT_CHANNEL_DARK]
    t.tick((303, "start-3"), False)        # restarted again, while dark
    assert [e for e, _ in said] == [EVENT_CHANNEL_DARK, EVENT_CHANNEL_BACK]
    assert "restarted" in said[1][1]["reason"]


def test_no_session_means_nothing_to_watch():
    rig = _tracker()
    t, said, clock = rig.t, rig.said, rig.clock
    for when in (0.0, 1000.0, 5000.0):
        clock[0] = when
        t.tick(None, False)
    assert said == []


def _log(tmp_path, rows):
    path = tmp_path / "agent_events_log.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_the_watch_reads_the_newest_channel_event_of_this_agent(tmp_path):
    now = time.time()
    path = _log(tmp_path, [
        {"timestamp": now - 50, "event": EVENT_CHANNEL_DARK, "data": {"agent": CARD, "reason": "dropped"}},
        {"timestamp": now - 40, "event": EVENT_CHANNEL_DARK, "data": {"agent": "Other@000000", "reason": "x"}},
    ])
    f = watch.check_channel(CARD, watch.last_channel_event(path, CARD, now), now)
    assert (f.subject, f.verdict) == ("channel", "DARK") and "dropped" in f.detail
    path = _log(tmp_path, [
        {"timestamp": now - 50, "event": EVENT_CHANNEL_DARK, "data": {"agent": CARD, "reason": "dropped"}},
        {"timestamp": now - 10, "event": EVENT_CHANNEL_BACK, "data": {"agent": CARD, "reason": "a channel attached"}},
    ])
    assert watch.check_channel(CARD, watch.last_channel_event(path, CARD, now), now).verdict == "ALIVE"
    lines, open_after = watch.transitions([watch.check_channel(CARD, watch.last_channel_event(
        _log(tmp_path, [{"timestamp": now - 5, "event": EVENT_CHANNEL_DARK,
                         "data": {"agent": CARD, "reason": "dropped"}}]), CARD, now), now)], {}, now)
    assert lines == [f"ALERT: {CARD} channel: DARK, dropped, 5 s ago"]
