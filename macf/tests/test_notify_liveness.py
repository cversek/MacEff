"""Four verdicts, because two of them report a healthy system as broken and a
broken one as healthy.

Every verdict here is induced rather than asserted: the record is written,
removed, corrupted and backdated, and each produces its own answer.
"""
import json

import pytest

from macf.notify import liveness


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    """Isolate the liveness record from the real runtime directory."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def test_absent_when_never_stamped(runtime):
    """A deployment that does not run the notifier is not an outage."""
    result = liveness.read()
    assert result.verdict == liveness.ABSENT
    assert result.is_alive is False


def test_alive_immediately_after_publishing(runtime):
    assert liveness.publish(cadence_s=30.0) is True
    result = liveness.read()
    assert result.verdict == liveness.ALIVE
    assert result.cadence_s == 30.0
    assert result.age_s is not None and result.age_s >= 0


def test_stale_when_backdated_past_its_OWN_cadence(runtime):
    """The bound is computed from the record's cadence, not from a second copy."""
    liveness.publish(cadence_s=10.0, now=1000.0)
    within = liveness.read(now=1000.0 + 10.0 * liveness.STALENESS_MULTIPLIER - 1)
    beyond = liveness.read(now=1000.0 + 10.0 * liveness.STALENESS_MULTIPLIER + 1)
    assert within.verdict == liveness.ALIVE
    assert beyond.verdict == liveness.STALE


def test_a_shorter_cadence_moves_its_own_bound(runtime):
    """A component that changes its interval changes its own staleness bound.

    This is what publishing the cadence buys. With a hard-coded bound the same
    timestamp would produce the same verdict for both cadences.
    """
    liveness.publish(cadence_s=1.0, now=1000.0)
    fast = liveness.read(now=1010.0)
    liveness.publish(cadence_s=100.0, now=1000.0)
    slow = liveness.read(now=1010.0)
    assert fast.verdict == liveness.STALE
    assert slow.verdict == liveness.ALIVE


@pytest.mark.parametrize("body", [
    "{not json at all",
    json.dumps({"cadence_s": 30}),
    json.dumps({"stamped_at": "yesterday", "cadence_s": 30}),
    json.dumps({"stamped_at": 1000.0, "cadence_s": 0}),
])
def test_unreadable_is_never_alive(runtime, body):
    """'I could not read it' feels like 'no news'. It is not."""
    liveness.record_path().write_text(body)
    result = liveness.read()
    assert result.verdict == liveness.UNREADABLE
    assert result.is_alive is False


def test_counters_survive_a_republish(runtime):
    liveness.publish(cadence_s=5.0, deliveries=3, suppressions=2, failures=1, last_delivery_at=42.0)
    result = liveness.read()
    assert (result.deliveries, result.suppressions, result.failures) == (3, 2, 1)
    assert result.last_delivery_at == 42.0
