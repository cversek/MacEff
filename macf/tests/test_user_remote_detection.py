"""Tests for USER_REMOTE presence-mode detection (#143).

USER_REMOTE is set explicitly and auto-clears the instant the operator returns
to the CLI — where "CLI activity" means source in {direct, mid_turn_enqueue},
NOT a Telegram ("channel") message (the operator is still remote then).
"""

from unittest.mock import patch

from macf.modes import detection


def _ev(event, ts, **data):
    return {"event": event, "timestamp": ts, "data": data}


def _detect(events):
    # read_events returns most-recent-first; both callers inside _detect_user_remote
    # (the mode_change scan and _get_last_user_activity_timestamp) hit this mock.
    with patch.object(detection, "read_events", return_value=events):
        return detection._detect_user_remote("s")


def test_no_mode_change_is_not_remote():
    assert _detect([_ev("user_activity_detected", 100, source="direct")]) is False


def test_enabled_with_only_channel_activity_is_remote():
    events = [
        _ev("user_activity_detected", 200, source="channel"),
        _ev("mode_change", 100, mode="USER_REMOTE", enabled=True),
    ]
    assert _detect(events) is True


def test_direct_cli_activity_after_set_clears_it():
    events = [
        _ev("user_activity_detected", 200, source="direct"),
        _ev("mode_change", 100, mode="USER_REMOTE", enabled=True),
    ]
    assert _detect(events) is False


def test_mid_turn_enqueue_counts_as_cli_and_clears():
    events = [
        _ev("user_activity_detected", 200, source="mid_turn_enqueue"),
        _ev("mode_change", 100, mode="USER_REMOTE", enabled=True),
    ]
    assert _detect(events) is False


def test_channel_activity_never_clears():
    events = [
        _ev("user_activity_detected", 300, source="channel"),
        _ev("user_activity_detected", 250, source="channel"),
        _ev("mode_change", 100, mode="USER_REMOTE", enabled=True),
    ]
    assert _detect(events) is True


def test_cli_activity_before_set_does_not_clear():
    # A CLI message that predates going remote must not cancel USER_REMOTE.
    events = [
        _ev("mode_change", 100, mode="USER_REMOTE", enabled=True),
        _ev("user_activity_detected", 50, source="direct"),
    ]
    assert _detect(events) is True


def test_most_recent_change_disabled_is_not_remote():
    events = [
        _ev("mode_change", 200, mode="USER_REMOTE", enabled=False),
        _ev("mode_change", 100, mode="USER_REMOTE", enabled=True),
    ]
    assert _detect(events) is False


def test_iso_timestamp_is_parsed():
    events = [
        _ev("user_activity_detected", "2026-08-09T18:00:05Z", source="direct"),
        _ev("mode_change", "2026-08-09T18:00:00Z", mode="USER_REMOTE", enabled=True),
    ]
    # direct activity 5s after set → cleared
    assert _detect(events) is False
