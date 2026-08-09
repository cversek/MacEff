"""Tests for mode-transition reinforcement messages (idea #091)."""

from macf.modes.transition_messages import (
    transition_reinforcement,
    OPERATIONAL_REINFORCEMENT,
    WORK_REINFORCEMENT,
)


def test_every_operational_mode_has_reinforcement():
    for mode in ("AUTO_MODE", "MANUAL_MODE", "USER_REMOTE"):
        assert transition_reinforcement(mode), f"no reinforcement for {mode}"


def test_every_work_mode_has_reinforcement():
    for mode in ("DISCOVER", "EXPERIMENT", "BUILD", "CURATE", "CONSOLIDATE", "SPRINT"):
        assert transition_reinforcement(mode), f"no reinforcement for {mode}"


def test_case_insensitive():
    assert transition_reinforcement("build") == transition_reinforcement("BUILD")


def test_unknown_or_empty_mode_returns_empty_string():
    # Callers print nothing (not a blank line) for these.
    assert transition_reinforcement("NOT_A_MODE") == ""
    assert transition_reinforcement("") == ""
    assert transition_reinforcement(None) == ""


def test_user_remote_message_names_the_hazard():
    msg = transition_reinforcement("USER_REMOTE")
    assert "hang" in msg.lower()
    assert "AskUserQuestion" in msg


def test_auto_mode_message_names_valid_stops():
    msg = transition_reinforcement("AUTO_MODE").lower()
    assert "scope" in msg and "stop" in msg
