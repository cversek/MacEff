"""Each declared unit's health, derived from events alone (MIS-0002-R15, R16)."""
import os
import time

from macf.notify.session import proc_start
from macf.pd.health import ABSENT, ALIVE, GONE, STALE, UNREADABLE, health
from macf.pd.interface import Declaration, Unit

CARD = "Tester@abc123"


def declaration(*names):
    return Declaration(version=1, agent=CARD, units=[
        Unit(name=n, command=["true"], account="tester", restart="always",
             liveness_interval_s=10.0, memory_limit_mb=64) for n in names])


def alive(unit, *, at, pid=4242, start="t0", interval=10.0, card=CARD, **extra):
    return {"timestamp": at, "event": "pd_unit_alive",
            "data": {"agent": card, "unit": unit, "pid": pid, "proc_start": start,
                     "interval_s": interval, **extra}}


def state(unit, value, *, at, reason="because", card=CARD):
    return {"timestamp": at, "event": "pd_unit_state",
            "data": {"agent": card, "unit": unit, "state": value, "reason": reason}}


def by_unit(results):
    return {h.unit: h for h in results}


def test_liveness_probed():
    """ALIVE needs a recent liveness and the very process it names (R15).

    The probe is asked with the pid and start time the unit wrote; a pid that now
    belongs to another process reads GONE however recent the write. The default
    probe is checked against this test's own process, with its own start time and with
    pid 1's, which a probe that looked at the pid alone would accept.
    """
    now = time.time()
    asked = []

    def probe(pid, start):
        asked.append((pid, start))
        return start == "t0"

    found = by_unit(health(declaration("worker", "imposter"), [
        alive("worker", at=now - 5),
        alive("imposter", at=now - 5, start="t1"),
    ], now, probe))
    assert found["worker"].liveness == ALIVE
    assert found["imposter"].liveness == GONE and "no longer the process" in found["imposter"].detail
    assert sorted(asked) == [(4242, "t0"), (4242, "t1")]

    me = os.getpid()
    real = health(declaration("worker"), [alive("worker", at=now - 5, pid=me, start=proc_start(me))], now)
    assert real[0].liveness == ALIVE
    wrong = proc_start(1)   # pid 1's start: real on Linux and macOS, never this process's
    assert health(declaration("worker"), [alive("worker", at=now - 5, pid=me, start=wrong)], now)[0].liveness == GONE


def test_stopped_never_started_and_unreadable():
    """Stopped, never started and unreadable are three verdicts, none of them ALIVE."""
    now = time.time()
    garbled = {"timestamp": now - 1, "event": "pd_unit_alive", "data": {"agent": CARD, "unit": "garbled"}}
    found = by_unit(health(declaration("stopped", "never", "garbled"), [
        alive("stopped", at=now - 300),
        state("never", "starting", at=now - 2),
        garbled,
    ], now, lambda pid, start: True))
    assert found["stopped"].liveness == STALE and "300 s ago" in found["stopped"].detail
    assert found["never"].liveness == ABSENT
    assert found["garbled"].liveness == UNREADABLE


def test_each_declared_unit_once_and_nothing_else():
    """Declared units in declaration order, once each, however many events name them.
    Another agent's events and an undeclared unit's are ignored, so neither can read
    as a healthy unit of this agent."""
    now = time.time()
    results = health(declaration("worker", "broker"), [
        state("worker", "starting", at=now - 10),
        state("worker", "running", at=now - 9),
        alive("worker", at=now - 1),
        alive("worker", at=now - 1, card="Someone@ffffff", pid=1111),
        alive("stray", at=now - 1),
    ], now, lambda pid, start: True)
    assert [h.unit for h in results] == ["worker", "broker"]
    assert results[0].pid == 4242 and results[1].liveness == ABSENT


def test_state_is_the_last_recorded():
    """The state reported is the daemon's latest for the unit, with its reason and time."""
    now = time.time()
    found = health(declaration("worker"), [
        state("worker", "starting", at=now - 30),
        state("worker", "running", at=now - 29),
        state("worker", "failed", at=now - 3, reason="exited 1"),
    ], now, lambda pid, start: True)[0]
    assert (found.state, found.reason, found.since) == ("failed", "exited 1", now - 3)


def test_work_in_flight_and_a_wait_are_carried():
    """What the unit last reported (R21, R49) reaches the reader with the verdict."""
    now = time.time()
    found = health(declaration("session"), [
        alive("session", at=now - 2, in_flight=2, waiting_on="a permission prompt"),
    ], now, lambda pid, start: True)[0]
    assert (found.liveness, found.in_flight, found.waiting_on) == (ALIVE, 2, "a permission prompt")


def test_the_watch_and_the_readout_agree():
    """The outside watch gives the readout's verdict on the same event (R15, R16): both
    apply ``read_liveness``, so neither can drift to its own bound or probe. The stale
    case sits between three and four intervals, where a second bound would part them."""
    from macf.pd import watch

    now = time.time()
    decl = declaration("worker")
    cases = {
        "absent": None,
        "unreadable": {"timestamp": now - 5, "event": "pd_unit_alive",
                       "data": {"agent": CARD, "unit": "worker"}},
        "stale": alive("worker", at=now - 35),
        "gone": alive("worker", at=now - 5, start="t1"),
        "alive": alive("worker", at=now - 5),
    }
    for name, event in cases.items():
        readout = health(decl, [event] if event else [], now, lambda pid, start: start == "t0")[0]
        watched = watch.check_unit(CARD, decl.units[0], event, now, lambda pid, start: start == "t0")
        assert readout.liveness == watched.verdict == name.upper(), (name, readout, watched)


def test_a_malformed_row_costs_only_itself():
    """A row that isn't an event, or whose data isn't one, is skipped. One bad line in the
    log takes away no other unit's verdict."""
    now = time.time()
    rows = ["not an event", {"event": "pd_unit_alive", "data": "not data"}, alive("worker", at=now - 5)]
    found = by_unit(health(declaration("worker"), rows, now, lambda pid, start: True))
    assert found["worker"].liveness == ALIVE
