"""The watcher must survive its input, and must say when it is not working.

A malformed authorization file used to raise out of the watch loop and end the
process permanently, while the receiver went on accepting mail nothing would
drain. That failure ACCUMULATED and looked healthy from outside, because the two
surviving services were still answering.

The repair creates a second hazard, and these tests cover both halves: a loop
that swallows its failures keeps stamping a perfectly fresh heartbeat while
draining nothing, so "alive" and "working" have to stop being the same question.
"""
import json
import time

import pytest

from macf.amail.daemons import inbound as daemon


class _Inbound:
    """Stands in for the macf.amail.inbound module the loop is handed.

    Ends the loop by raising KeyboardInterrupt, which is a BaseException and so
    passes straight through the loop's `except Exception`. That is itself part
    of what these tests assert: the catch is deliberately broad, and a stop
    signal must still be able to stop the service.
    """

    def __init__(self, *, raises=None, fail_times=None, stop_after=3):
        self.raises = raises
        self.fail_times = fail_times
        self.stop_after = stop_after
        self.calls = 0

    def process_spool(self, cfg):
        self.calls += 1
        if self.calls > self.stop_after:
            raise KeyboardInterrupt
        if self.raises and (self.fail_times is None
                            or self.calls <= self.fail_times):
            raise self.raises
        return []

    def sweep_aged(self, cfg, now=None):
        return {"alerts": 0, "aged_spool": [], "aged_pickup": []}


@pytest.fixture
def loop(tmp_path, monkeypatch):
    """Run `watch` against temp paths until the fake stops it.

    The fake ends the run, not a patched clock. An earlier version of this
    fixture counted `time.sleep` calls — which never fire at interval 0, so it
    span forever and the hang looked like a defect in the code under test.
    """
    monkeypatch.setattr(daemon, "HEARTBEAT", tmp_path / "watch.heartbeat")
    monkeypatch.setenv("AMAIL_WATCH_INTERVAL", "0")
    monkeypatch.setenv("AMAIL_WATCH_SWEEP_INTERVAL", "99999")

    def run(inbound):
        try:
            daemon.watch(object(), inbound)
        except KeyboardInterrupt:
            pass
        return json.loads((tmp_path / "watch.heartbeat").read_text())
    return run


class TestTheLoopSurvivesItsInput:
    def test_a_raising_spool_does_not_end_the_watcher(self, loop):
        """THE DEFECT. A malformed file must not be able to stop the service —
        there is no caller waiting, so report-and-return ends it permanently."""
        inbound = _Inbound(raises=ValueError("malformed contacts"))
        loop(inbound)
        assert inbound.calls >= 2, "the loop stopped after the first failure"

    def test_any_exception_type_is_survived_not_just_the_expected_ones(self, loop):
        """Narrowing this catch means the next unforeseen parse error ends the
        watcher again, which is the exact defect rather than a variant of it."""
        inbound = _Inbound(raises=RuntimeError("something nobody predicted"))
        loop(inbound)
        assert inbound.calls >= 2

    def test_it_recovers_when_the_input_is_repaired(self, loop):
        """The file is often mid-edit. Recovery must need no restart."""
        inbound = _Inbound(raises=ValueError("bad"), fail_times=1, stop_after=4)
        hb = loop(inbound)
        assert hb["consecutive_failures"] == 0 and hb["last_error"] == ""


class TestItPublishesThatItIsFailing:
    def test_the_heartbeat_carries_the_failure_count_and_the_error(self, loop):
        hb = loop(_Inbound(raises=ValueError("malformed contacts")))
        assert hb["consecutive_failures"] >= 1
        assert "malformed contacts" in hb["last_error"]

    def test_a_healthy_cycle_publishes_zero(self, loop):
        hb = loop(_Inbound())
        assert hb["consecutive_failures"] == 0


class TestFailingIsNotAlive:
    """The hazard the repair introduced. A wedged watcher stamps a perfectly
    fresh heartbeat forever, so an observer asking only 'is the stamp fresh?'
    reports green over a service that is draining nothing."""

    def _stamp(self, path, **extra):
        path.write_text(json.dumps({"epoch": time.time(), "pid": 7,
                                    "interval_s": 15, **extra}) + "\n")

    def test_a_fresh_heartbeat_with_failures_is_FAILING_not_alive(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(daemon, "HEARTBEAT", tmp_path / "hb")
        self._stamp(daemon.HEARTBEAT, consecutive_failures=3,
                    last_error="ValueError: malformed contacts")
        v = daemon.heartbeat_verdict()
        assert v["state"] == "failing"
        assert v["consecutive_failures"] == 3
        assert "NOT being drained" in v["detail"]

    def test_zero_failures_is_alive(self, tmp_path, monkeypatch):
        monkeypatch.setattr(daemon, "HEARTBEAT", tmp_path / "hb")
        self._stamp(daemon.HEARTBEAT, consecutive_failures=0)
        assert daemon.heartbeat_verdict()["state"] == "alive"

    def test_a_heartbeat_predating_the_field_is_still_alive(
            self, tmp_path, monkeypatch):
        """An older watcher publishes no failure count. Absent must read as
        zero, not as failing — otherwise the upgrade alarms on itself."""
        monkeypatch.setattr(daemon, "HEARTBEAT", tmp_path / "hb")
        self._stamp(daemon.HEARTBEAT)
        assert daemon.heartbeat_verdict()["state"] == "alive"

    def test_health_reports_unhealthy_while_failing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(daemon, "HEARTBEAT", tmp_path / "hb")
        monkeypatch.setattr(daemon, "WD_HEARTBEAT", tmp_path / "wd")
        self._stamp(daemon.HEARTBEAT, consecutive_failures=1, last_error="x")
        self._stamp(daemon.WD_HEARTBEAT, interval_s=300)
        assert daemon.health(object(), _Inbound()) == 1

    def test_the_watchdog_alarms_on_failing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(daemon, "HEARTBEAT", tmp_path / "hb")
        monkeypatch.setattr(daemon, "ALERTS", tmp_path / "alerts.jsonl")
        self._stamp(daemon.HEARTBEAT, consecutive_failures=2, last_error="x")
        kinds = [a["kind"] for a in daemon._check_once(object(), _Inbound())]
        assert kinds == ["watcher_failing"]
