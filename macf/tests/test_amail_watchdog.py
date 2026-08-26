"""Controls for the inbound watchdog — the supervisor that is NOT the watcher.

The deployment already had a sweep, a correct one, that exited non-zero on any
alert exactly as a scheduler needs. It was scheduled in one place: inside the
watcher's own loop. So the sweep whose purpose was to report that the watcher
had died shared the process that died, and the two went quiet together while
the receiver kept spooling mail nothing would drain.

That is why these tests are mostly about ABSENCE and STALENESS rather than
about sweeping. The sweep worked throughout the outage it was meant to catch.
What did not exist was anything outside the watcher looking at it.
"""
import json
import time

import pytest

from macf.amail import alerting
from macf.amail.daemons import inbound as daemon


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """Redirect every file the watchdog reads or writes into a temp tree."""
    monkeypatch.setattr(daemon, "HEARTBEAT", tmp_path / "watch.heartbeat")
    monkeypatch.setattr(daemon, "WD_HEARTBEAT", tmp_path / "watchdog.heartbeat")
    monkeypatch.setattr(daemon, "ALERTS", tmp_path / "alerts.jsonl")
    return tmp_path


class _FakeCfg:
    """Minimal cfg carrying only what the edge ledger path needs.

    A bare object() sends the ledger to the real deployment path, which is not
    writable from a test -- and the failure mode there is worth naming: an
    unwritable ledger degrades to LEVEL-TRIGGERED, re-raising every standing
    condition. The commit warns when that happens.
    """

    def __init__(self, tmp_path):
        self.spool_dir = tmp_path / "amail" / "spool"
        self.spool_dir.mkdir(parents=True, exist_ok=True)


def _stamp(path, *, epoch, interval_s=15, pid=4242):
    payload = {"ts": "x", "epoch": epoch, "pid": pid}
    if interval_s is not None:
        payload["interval_s"] = interval_s
    path.write_text(json.dumps(payload) + "\n")


class TestTheWatcherVerdictHasThreeStates:
    """Absent and stale are different facts and must not be collapsed.

    A deployment that does not run the watcher and a deployment whose watcher
    died look identical if the only question asked is "is it fresh?" — and only
    one of them is an outage.
    """

    def test_absent_is_absent_not_stale(self, paths):
        v = daemon.heartbeat_verdict()
        assert v["state"] == "absent"
        assert "never run" in v["detail"]

    def test_a_fresh_stamp_is_alive(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        assert daemon.heartbeat_verdict()["state"] == "alive"

    def test_an_old_stamp_is_stale(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time() - 10_000)
        v = daemon.heartbeat_verdict()
        assert v["state"] == "stale" and v["age_s"] >= 10_000

    def test_unreadable_is_its_own_state_and_not_alive(self, paths):
        """THE FAIL-OPEN THAT MATTERS. A corrupt heartbeat says liveness is
        UNKNOWN. Treating unknown as healthy is how a supervisor reports green
        over a dead subject."""
        daemon.HEARTBEAT.write_text("{not json")
        v = daemon.heartbeat_verdict()
        assert v["state"] == "unreadable"
        assert "UNKNOWN" in v["detail"]

    def test_a_heartbeat_with_no_epoch_is_not_alive(self, paths):
        daemon.HEARTBEAT.write_text(json.dumps({"ts": "x", "pid": 1}) + "\n")
        assert daemon.heartbeat_verdict()["state"] == "stale"


class TestTheBoundIsDerivedNotRestated:
    """The observer computes its staleness bound from the cadence the observed
    publishes. Two places configuring one interval drift, and the drift only
    shows up when the bound is wrong in the direction that stays quiet."""

    def test_a_slow_watcher_is_given_proportionally_longer(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time(), interval_s=600)
        assert daemon.heartbeat_verdict()["bound_s"] == 6000

    def test_a_fast_watcher_does_not_shrink_below_the_floor(self, paths):
        """A 15s cadence times ten is 150s, under the floor. Without the floor
        a single slow spool drain would be reported as a death."""
        _stamp(daemon.HEARTBEAT, epoch=time.time(), interval_s=15)
        assert daemon.heartbeat_verdict()["bound_s"] == daemon.HEARTBEAT_BOUND_FLOOR_S

    def test_a_heartbeat_predating_the_published_cadence_still_works(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time(), interval_s=None)
        assert daemon.heartbeat_verdict()["bound_s"] == daemon.HEARTBEAT_BOUND_FLOOR_S


class _FakeInbound:
    def __init__(self, report=None, raises=None):
        self.report = report or {"alerts": 0, "aged_spool": [], "aged_pickup": [],
                                 "findings": []}
        self.raises = raises
        self.calls = 0

    def sweep_aged(self, cfg, now=None):
        self.calls += 1
        if self.raises:
            raise self.raises
        return self.report


class TestOnePass:
    def test_a_dead_watcher_raises_an_alarm(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time() - 10_000)
        alarms = daemon._check_once(object(), _FakeInbound())
        assert [a["kind"] for a in alarms] == ["watcher_stale"]

    def test_a_live_watcher_and_a_clean_sweep_raise_nothing(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        assert daemon._check_once(object(), _FakeInbound()) == []

    def test_aged_entries_raise_an_alarm_naming_both_populations(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        fake = _FakeInbound({"alerts": 2, "aged_spool": ["a.eml"],
                             "aged_pickup": ["bob/b.eml"],
                             "findings": [alerting.classify_system("spool:a.eml", "aged"),
                                          alerting.classify_system("pickup:bob/b.eml", "aged")]})
        alarms = daemon._check_once(object(), fake)
        assert alarms[0]["kind"] == "aged_entries"
        assert alarms[0]["aged_spool"] == ["a.eml"]
        assert alarms[0]["aged_pickup"] == ["bob/b.eml"]

    def test_a_STANDING_condition_alarms_ONCE_across_repeated_passes(self, paths):
        """The wiring, at the level the deployment actually runs.

        The edge ledger was built, unit-tested and connected to nothing: the
        sweep re-raised every standing condition on every pass, which is how two
        undrained messages became thirty-six pages in nine hours. The unit tests
        exercised the ledger; nothing exercised the caller.
        """
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        report = {"alerts": 1, "aged_spool": ["a.eml"], "aged_pickup": [],
                  "findings": [alerting.classify_system("spool:a.eml", "aged")]}

        cfg = _FakeCfg(paths)
        first = daemon._check_once(cfg, _FakeInbound(report))
        assert [a["kind"] for a in first] == ["aged_entries"]

        for _ in range(35):
            again = daemon._check_once(cfg, _FakeInbound(report))
            assert again == [], "a true-and-persisting condition must not re-alarm"

    def test_RECOVERY_is_announced_when_the_condition_clears(self, paths):
        """Told when it breaks and never when it heals, a reader cannot learn
        the current state except by asking."""
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        report = {"alerts": 1, "aged_spool": ["a.eml"], "aged_pickup": [],
                  "findings": [alerting.classify_system("spool:a.eml", "aged")]}
        cfg = _FakeCfg(paths)
        daemon._check_once(cfg, _FakeInbound(report))

        clean = {"alerts": 0, "aged_spool": [], "aged_pickup": [], "findings": []}
        alarms = daemon._check_once(cfg, _FakeInbound(clean))
        assert [a["kind"] for a in alarms] == ["cleared"]
        assert alarms[0]["resolved_key"] == "spool:a.eml"

    def test_a_CRASH_between_detection_and_alarm_RE_RAISES_rather_than_swallows(
            self, paths, monkeypatch):
        """Ordering that is invisible until something dies.

        Committing the ledger before the alarm is built produces identical
        behaviour in every run that completes -- which is why the mutation for
        it survived a full suite. The orderings differ only when the process
        dies in between, and then they differ in the direction that matters: a
        lost notice is worse than a repeated one.
        """
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        cfg = _FakeCfg(paths)
        report = {"alerts": 1, "aged_spool": ["a.eml"], "aged_pickup": [],
                  "findings": [alerting.classify_system("spool:a.eml", "aged")]}

        real_alert = daemon._alert

        def dies(kind, *a, **k):
            if kind == "aged_entries":
                raise RuntimeError("process died building the alarm")
            return real_alert(kind, *a, **k)

        monkeypatch.setattr(daemon, "_alert", dies)
        with pytest.raises(RuntimeError):
            daemon._check_once(cfg, _FakeInbound(report))

        # The condition must still be unseen, so the next pass raises it.
        monkeypatch.setattr(daemon, "_alert", real_alert)
        alarms = daemon._check_once(cfg, _FakeInbound(report))
        assert [a["kind"] for a in alarms] == ["aged_entries"], (
            "a condition lost to a crash must be re-raised, not swallowed")

    def test_a_NEW_condition_beside_a_standing_one_still_alarms(self, paths):
        """Both polarities: suppression must not become deafness."""
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        one = {"alerts": 1, "aged_spool": ["a.eml"], "aged_pickup": [],
               "findings": [alerting.classify_system("spool:a.eml", "aged")]}
        cfg = _FakeCfg(paths)
        daemon._check_once(cfg, _FakeInbound(one))
        assert daemon._check_once(cfg, _FakeInbound(one)) == []

        two = {"alerts": 2, "aged_spool": ["a.eml", "b.eml"], "aged_pickup": [],
               "findings": [alerting.classify_system("spool:a.eml", "aged"),
                            alerting.classify_system("spool:b.eml", "aged")]}
        alarms = daemon._check_once(cfg, _FakeInbound(two))
        assert [a["kind"] for a in alarms] == ["aged_entries"]
        assert alarms[0]["new_keys"] == ["spool:b.eml"]
        assert alarms[0]["ongoing_keys"] == ["spool:a.eml"]

    def test_a_sweep_that_raises_becomes_an_alarm_not_an_exception(self, paths):
        """THE LOOP-SCOPED RULE, at the one place it decides whether the
        supervisor survives. The sweep reads a spool an unprivileged uid can
        lose access to; letting that escape would kill the watchdog with the
        same class of fault it exists to outlive."""
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        alarms = daemon._check_once(object(), _FakeInbound(raises=OSError("EACCES")))
        assert [a["kind"] for a in alarms] == ["sweep_failed"]

    def test_watcher_liveness_is_still_checked_when_config_did_not_load(self, paths):
        """Degraded, and saying so, beats not starting. The heartbeat check
        needs no config, and it is the half that detects the outage."""
        _stamp(daemon.HEARTBEAT, epoch=time.time() - 10_000)
        kinds = [a["kind"] for a in daemon._check_once(None, _FakeInbound())]
        assert kinds == ["watcher_stale", "sweep_unavailable"]


class TestAlarmsAreDurable:
    def test_an_alarm_is_appended_to_the_alert_file(self, paths):
        daemon._alert("k", "d", extra=1)
        daemon._alert("k2", "d2")
        lines = daemon.ALERTS.read_text().strip().split("\n")
        assert [json.loads(x)["kind"] for x in lines] == ["k", "k2"]

    def test_an_unwritable_alert_file_does_not_raise(self, paths, monkeypatch):
        """An alarm that cannot be filed must still be raised. The supervisor
        may not die of the thing it is reporting."""
        monkeypatch.setattr(daemon, "ALERTS", paths / "nope" / "x.jsonl")
        monkeypatch.setattr(daemon.Path, "mkdir",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
        assert daemon._alert("k", "d")["kind"] == "k"


class TestHealthIsTheOutsideSurface:
    """`health` is where the chain reaches something a human or a scheduler can
    act on, so its exit code carries the whole verdict."""

    def test_all_green_exits_zero(self, paths, capsys):
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        _stamp(daemon.WD_HEARTBEAT, epoch=time.time(), interval_s=300)
        assert daemon.health(object(), _FakeInbound()) == 0
        assert json.loads(capsys.readouterr().out)["healthy"] is True

    def test_a_dead_watcher_exits_non_zero(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time() - 10_000)
        _stamp(daemon.WD_HEARTBEAT, epoch=time.time(), interval_s=300)
        assert daemon.health(object(), _FakeInbound()) == 1

    def test_a_dead_WATCHDOG_exits_non_zero_even_with_a_live_watcher(self, paths):
        """The reading nobody should trust: a green watcher reported by a
        supervisor that has itself stopped checking. Without this the chain
        just moves one level up and goes quiet there."""
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        _stamp(daemon.WD_HEARTBEAT, epoch=time.time() - 10_000, interval_s=300)
        assert daemon.health(object(), _FakeInbound()) == 1

    def test_a_missing_watchdog_exits_non_zero(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        assert daemon.health(object(), _FakeInbound()) == 1

    def test_aged_entries_alone_exit_non_zero(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        _stamp(daemon.WD_HEARTBEAT, epoch=time.time(), interval_s=300)
        fake = _FakeInbound({"alerts": 1, "aged_spool": ["a.eml"], "aged_pickup": []})
        assert daemon.health(object(), fake) == 1

    def test_a_sweep_that_raises_does_not_report_healthy(self, paths):
        _stamp(daemon.HEARTBEAT, epoch=time.time())
        _stamp(daemon.WD_HEARTBEAT, epoch=time.time(), interval_s=300)
        assert daemon.health(object(), _FakeInbound(raises=OSError("x"))) == 1


class TestTheWatcherPublishesItsCadence:
    def test_the_heartbeat_payload_carries_interval_s(self):
        """The derived bound depends on the watcher publishing this. If the
        field is dropped the observer silently falls back to the floor, which
        is wrong in the quiet direction for any slow cadence."""
        import inspect
        assert "interval_s" in inspect.getsource(daemon.watch)
