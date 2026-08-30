"""The death class: a silence that can be recovered afterwards.

A notifier that dies and restarts quietly leaves an interval in which arrivals
were real and nobody was told -- and that interval reads, from inside the agent,
exactly like an interval in which nothing happened. That is the confusion this
whole subsystem exists to end, reappearing inside the tool built to end it.
"""
import json

import pytest

from macf.notify import liveness


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def test_a_clean_first_start_records_no_gap(runtime):
    """Never having run is not downtime. Positive control for the negative case."""
    assert liveness.read().verdict == liveness.ABSENT
    assert liveness.note_start(cadence_s=30.0, now=1000.0) is None
    assert liveness.gaps() == []
    assert liveness.read(now=1000.0).verdict == liveness.ALIVE


def test_a_restart_after_death_records_the_interval(runtime):
    liveness.publish(cadence_s=10.0, now=1000.0)
    gap = liveness.note_start(cadence_s=10.0, now=5000.0)
    assert gap is not None
    assert gap["down_from"] == 1000.0
    assert gap["down_until"] == 5000.0
    assert gap["duration_s"] == 4000.0
    assert "NOT replayed" in gap["note"]
    assert len(liveness.gaps()) == 1


def test_a_restart_WITHIN_the_bound_is_not_a_gap(runtime):
    """A quick restart that never went stale did not lose a notice window."""
    liveness.publish(cadence_s=10.0, now=1000.0)
    assert liveness.note_start(cadence_s=10.0, now=1005.0) is None
    assert liveness.gaps() == []


def test_an_unreadable_prior_record_yields_UNKNOWN_downtime_not_zero(runtime):
    """'I could not read it' must not become 'nothing was missed'."""
    liveness.record_path().write_text("{corrupt")
    gap = liveness.note_start(cadence_s=10.0, now=2000.0)
    assert gap is not None
    assert gap["duration_s"] is None
    assert "UNKNOWN, not zero" in gap["note"]


def test_gaps_accumulate_and_are_bounded(runtime):
    for i in range(liveness.GAPS_RETAIN + 5):
        liveness.publish(cadence_s=1.0, now=float(i * 1000))
        liveness.note_start(cadence_s=1.0, now=float(i * 1000 + 500))
    assert len(liveness.gaps()) == liveness.GAPS_RETAIN


@pytest.mark.parametrize("setup,expect_code,expect_verdict", [
    ("alive", 0, liveness.ALIVE),
    ("stale", 1, liveness.STALE),
    ("absent", 2, liveness.ABSENT),
    ("corrupt", 3, liveness.UNREADABLE),
])
def test_watchdog_maps_each_state_to_its_OWN_exit_code(runtime, setup, expect_code, expect_verdict):
    """Three outcomes minimum, because 'I could not measure it' is not 'it is fine'.

    Each state is INDUCED rather than asserted, and each gets a distinct code, so
    a scheduler can act differently on 'fix the subsystem' vs 'start it' vs
    'fix the monitor'.
    """
    if setup == "alive":
        liveness.publish(cadence_s=30.0, now=1000.0)
        result = liveness.watchdog_check(now=1000.0)
    elif setup == "stale":
        liveness.publish(cadence_s=10.0, now=1000.0)
        result = liveness.watchdog_check(now=99999.0)
    elif setup == "absent":
        result = liveness.watchdog_check(now=1000.0)
    else:
        liveness.record_path().write_text("{corrupt")
        result = liveness.watchdog_check(now=1000.0)
    assert result.exit_code == expect_code
    assert result.verdict == expect_verdict
    assert result.verdict.lower() in result.message.lower()


def test_watchdog_message_carries_ITS_OWN_measurement_not_a_restated_config(runtime):
    """A notifier that restates the subject from its own config names the wrong one.

    The bound in the message must come from the record that was read.
    """
    liveness.publish(cadence_s=7.0, now=1000.0)
    result = liveness.watchdog_check(now=99999.0)
    assert "21s" in result.message, (
        f"bound must be derived from the record's own cadence: {result.message}")
