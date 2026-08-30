"""V26 — the acceptor is coupled to its processor's liveness, alarm-only.

Left uncoupled, a stopped consumer turns a silent failure into an ACCUMULATING
one: the queue grows with no bound while the deployment presents as healthy,
because every surface a caller touches is still answering. That is how inbound
stayed down for over a day.

The trigger is the SPOOL, not the heartbeat. A heartbeat is a report; the spool
is the world, and the world is what the acceptor can observe without trusting
anyone. The heartbeat is read only to make the alarm specific.
"""
import json
import time
from types import SimpleNamespace

import pytest

from macf.amail.daemons import receiver


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(receiver, "SPOOL", tmp_path / "spool")
    monkeypatch.setattr(receiver, "ALERTS", tmp_path / "alerts.jsonl")
    monkeypatch.setattr(receiver, "LOG_PATH", tmp_path / "ingest.jsonl")
    monkeypatch.setattr(receiver, "WATCH_HEARTBEAT", tmp_path / "hb")
    monkeypatch.setattr(receiver, "_last_drain_alarm", 0.0)
    (tmp_path / "spool").mkdir()

    def spool_entry(age_s):
        p = tmp_path / "spool" / f"m{age_s}.eml"
        p.write_text("x")
        t = time.time() - age_s
        import os
        os.utime(p, (t, t))
        return p

    def heartbeat(**kw):
        (tmp_path / "hb").write_text(json.dumps(
            {"epoch": time.time(), "consecutive_failures": 0, **kw}) + "\n")

    def alarms():
        f = tmp_path / "alerts.jsonl"
        return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []

    # A namespace rather than a tuple: three same-typed callables returned
    # positionally would let a reorder swap their meaning silently, which
    # is the defect MACEFF004 names -- and the gate caught it here.
    return SimpleNamespace(spool_entry=spool_entry, heartbeat=heartbeat,
                           alarms=alarms)


class TestItAlarmsWhenNothingIsDraining:
    def test_a_fresh_spool_is_silent(self, rig):
        rig.spool_entry(5)
        rig.heartbeat()
        receiver.check_drain()
        assert rig.alarms() == []

    def test_an_empty_spool_is_silent(self, rig):
        rig.heartbeat()
        receiver.check_drain()
        assert rig.alarms() == []

    def test_an_aged_entry_alarms(self, rig):
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        rig.heartbeat()
        receiver.check_drain()
        assert len(rig.alarms()) == 1
        assert rig.alarms()[0]["kind"] == "spool_not_draining"


class TestItNeverRefuses:
    def test_check_drain_returns_none_and_raises_nothing(self, rig):
        """ALARM-ONLY IS THE POINT. Refusing at the edge would bound the queue
        by bouncing real senders during an outage now detected in seconds —
        spending other people's mail on a problem whose danger was that nobody
        knew, and that part is fixed."""
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        rig.heartbeat()
        assert receiver.check_drain() is None

    def test_a_broken_spool_does_not_raise_into_the_accept_path(
            self, rig, monkeypatch, tmp_path):
        """This runs after a message is accepted. A receiver that failed to
        deliver mail because its own health check raised would be a worse bug
        than the one it watches for."""
        monkeypatch.setattr(receiver, "SPOOL", tmp_path / "does-not-exist")
        assert receiver.check_drain() is None

    def test_an_unwritable_alert_file_does_not_raise(self, rig, monkeypatch, tmp_path):
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        rig.heartbeat()
        monkeypatch.setattr(receiver, "ALERTS", tmp_path / "ro" / "x.jsonl")
        monkeypatch.setattr(receiver.Path, "mkdir",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
        assert receiver.check_drain() is None


class TestTheAlarmIsRateLimited:
    def test_a_second_immediate_check_does_not_alarm_again(self, rig):
        """The condition persists across every message that arrives during an
        outage. One alarm per message would bury the one that mattered under
        thousands of identical lines."""
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        rig.heartbeat()
        receiver.check_drain()
        receiver.check_drain()
        receiver.check_drain()
        assert len(rig.alarms()) == 1

    def test_it_alarms_again_after_the_interval(self, rig, monkeypatch):
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        rig.heartbeat()
        receiver.check_drain()
        monkeypatch.setattr(receiver, "_last_drain_alarm",
                            time.time() - receiver.DRAIN_ALARM_INTERVAL_S - 1)
        receiver.check_drain()
        assert len(rig.alarms()) == 2


class TestTheAlarmDistinguishesTheRemedies:
    """A consumer that says it is dead and one that says it is fine while
    draining nothing need completely different remedies. An alarm that cannot
    tell them apart sends the reader to guess."""

    def _detail(self, rig):
        receiver.check_drain()
        return rig.alarms()[0]["detail"]

    def test_a_dead_consumer_is_named_as_probably_dead(self, rig):
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        rig.heartbeat(epoch=time.time() - 5000)
        assert "probably DEAD" in self._detail(rig)

    def test_a_failing_consumer_is_named_as_alive_but_failing(self, rig):
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        rig.heartbeat(consecutive_failures=3, last_error="ValueError: bad contacts")
        d = self._detail(rig)
        assert "ALIVE but failing" in d and "bad contacts" in d

    def test_a_healthy_consumer_points_at_the_spool_itself(self, rig):
        """The most useful case: the consumer is fine and still nothing drains,
        which is a permissions or configuration mismatch, not an outage."""
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        rig.heartbeat()
        d = self._detail(rig)
        assert "reports HEALTHY" in d and "NOT draining" in d

    def test_an_unreadable_heartbeat_says_unknown_not_healthy(self, rig, tmp_path):
        """Unknown is not healthy. Reading across a uid boundary can fail for
        reasons that have nothing to do with the consumer's state."""
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        (tmp_path / "hb").write_text("{not json")
        assert "UNKNOWN" in self._detail(rig)

    def test_the_alarm_says_mail_is_still_being_accepted(self, rig):
        """So the reader knows the queue is still growing — the alarm reports a
        condition, it does not imply the flow has stopped."""
        rig.spool_entry(receiver.DRAIN_BOUND_S + 60)
        rig.heartbeat()
        assert "still being ACCEPTED" in self._detail(rig)
