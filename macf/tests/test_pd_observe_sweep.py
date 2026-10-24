"""A running primal daemon records the end of an observation whose lease ran out (MIS-0002-R89).

``observe.record.sweep`` writes the ending a lapsed lease owes, the same kind of ending a party's
own end writes (R89), but only if something calls it. The daemon calls it on a beat of its own,
so the agent's log never says an observation is open after its lease ended. These tests run a
real daemon, not the sweep alone, since the defect was that nothing called it.
"""
import json
import time

from macf.observe import acts, record
from macf.pd import daemon as daemon_module
from test_primal_daemon import base, make_home, run_daemon  # noqa: F401 - fixtures

ME, THEM = "Observed@ab12cd", "Onlooker@cd34ef"


def _host(card):
    return None


def _endings(log):
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    return [r["data"] for r in rows if r.get("event") == acts.EVENT_END]


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_a_running_daemon_records_the_end_a_lapsed_lease_owes(
        tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    monkeypatch.setattr(daemon_module, "OBSERVE_SWEEP_S", 0.05)
    record.invite(ME, THEM, 0, container_of=_host, lease_until=time.time() + 0.3)
    run_daemon(make_home(tmp_path, []), base)
    assert _wait_for(lambda: _endings(isolated_events_log)), "the daemon never recorded the lapsed lease"
    ends = _endings(isolated_events_log)
    assert [(e["onlooker"], e["ended_by"]) for e in ends] == [(THEM, "lease")]
    time.sleep(0.3)                                     # later sweeps owe nothing more
    assert len(_endings(isolated_events_log)) == 1


def test_a_lease_still_running_is_left_open(tmp_path, base, run_daemon, isolated_events_log, monkeypatch):
    monkeypatch.setattr(daemon_module, "OBSERVE_SWEEP_S", 0.05)
    record.invite(ME, THEM, 0, container_of=_host, lease_until=time.time() + 3600)
    run_daemon(make_home(tmp_path, []), base)
    time.sleep(0.5)
    assert _endings(isolated_events_log) == []
    assert record.current()[THEM].status != acts.ENDED
