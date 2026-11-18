"""Tests for the scope-gate idle-stop failsafe counter (BUG #1022).

Coverage target: macf/src/macf/task/scope_gate_failsafe.py

This module protects against a deadlocked Stop hook: when the scope gate
blocks completion and the agent has no useful work to do, a decrementing
counter lets the agent escape the loop after COUNT_INIT idle stops. These
tests exercise the counter's read/write/decrement/reset behavior in
isolation from the real runtime directory (every test monkeypatches
``_counter_path`` to a per-test tmp file, except those that test the path itself).
"""

import json

import pytest

from macf.task import scope_gate_failsafe as sgf

_REAL_COUNTER_PATH = sgf._counter_path


@pytest.fixture(autouse=True)
def isolated_counter_path(tmp_path, monkeypatch):
    """Redirect the failsafe's counter to a per-test file."""
    counter_file = tmp_path / "scope_gate_idle_counter.json"
    monkeypatch.setattr(sgf, "_counter_path", lambda: counter_file)
    return counter_file


def test_reset_sets_counter_to_count_init(isolated_counter_path):
    """reset() writes COUNT_INIT, regardless of prior state."""
    isolated_counter_path.write_text(json.dumps({"remaining": 0}))

    sgf.reset()

    assert sgf.current() == sgf.COUNT_INIT


def test_decrement_and_check_decrements_by_one_without_failing_open():
    """A single decrement from COUNT_INIT reduces by 1 and does not fail open."""
    remaining, fail_open = sgf.decrement_and_check()

    assert remaining == sgf.COUNT_INIT - 1
    assert fail_open is False


def test_decrement_and_check_fails_open_when_counter_reaches_zero():
    """Decrementing COUNT_INIT times reaches 0 and signals fail_open on that call."""
    for _ in range(sgf.COUNT_INIT - 1):
        _, fail_open = sgf.decrement_and_check()
        assert fail_open is False

    remaining, fail_open = sgf.decrement_and_check()

    assert remaining == 0
    assert fail_open is True


def test_decrement_and_check_does_not_go_negative():
    """Once at 0, further decrements stay at 0 (floor, not negative)."""
    for _ in range(sgf.COUNT_INIT):
        sgf.decrement_and_check()

    remaining, fail_open = sgf.decrement_and_check()

    assert remaining == 0
    assert fail_open is True


def test_current_defaults_to_count_init_when_file_missing(isolated_counter_path):
    """No sidecar file yet means the counter reads as fully replenished."""
    assert not isolated_counter_path.exists()

    assert sgf.current() == sgf.COUNT_INIT


def test_current_recovers_to_count_init_on_corrupt_json(isolated_counter_path):
    """Garbage on disk is treated as if the counter were never written."""
    isolated_counter_path.write_text("{not valid json")

    assert sgf.current() == sgf.COUNT_INIT


def test_the_counter_lives_in_this_users_runtime_dir_not_a_shared_tmp(tmp_path, monkeypatch):
    """Several agents share a container under separate accounts. A bare /tmp/macf is owned
    by whichever created it first, and the others could not write their counter, so their
    failsafe never counted down."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    (tmp_path / "run").mkdir()
    monkeypatch.setattr(sgf, "_counter_path", _REAL_COUNTER_PATH)
    path = sgf._counter_path()
    assert path.resolve().is_relative_to((tmp_path / "run").resolve())
    assert "/tmp/macf/" not in str(path)
    for _ in range(sgf.COUNT_INIT - 1):
        sgf.decrement_and_check()
    assert sgf.decrement_and_check() == (0, True), "it counts down to fail-open where it is stored"


def test_an_unsaveable_counter_is_reported_not_swallowed(tmp_path, monkeypatch, capsys):
    """A counter that cannot be written reads COUNT_INIT on every Stop, so the failsafe
    never fires; that must reach the agent and the operator, not pass in silence."""
    monkeypatch.setattr(sgf, "_counter_path", lambda: tmp_path / "missing" / "counter.json")
    sgf.decrement_and_check()
    assert "idle-stop counter could not be saved" in capsys.readouterr().err
