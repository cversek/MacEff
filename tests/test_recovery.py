#!/usr/bin/env python3
"""Tests for consciousness recovery message formatting."""

import pytest

from macf.hooks.recovery import format_consciousness_recovery_message
from macf.utils import ConsciousnessArtifacts, SessionOperationalState


def test_auto_mode_includes_authorized():
    """AUTO mode includes 'AUTHORIZED' in message."""
    state = SessionOperationalState("test-session", "TestAgent")
    state.auto_mode = True
    state.auto_mode_source = "env"
    state.auto_mode_confidence = 0.9

    artifacts = ConsciousnessArtifacts()

    message = format_consciousness_recovery_message("test-session", state, artifacts)

    assert "AUTHORIZED" in message
    assert "AUTO_MODE" in message


def test_manual_mode_includes_stop_warning():
    """MANUAL mode includes 'STOP' or 'DO NOT' warning."""
    state = SessionOperationalState("test-session", "TestAgent")
    state.auto_mode = False

    artifacts = ConsciousnessArtifacts()

    message = format_consciousness_recovery_message("test-session", state, artifacts)

    assert "STOP" in message or "DO NOT" in message
    assert "MANUAL MODE" in message


def test_message_contains_artifacts_section():
    """Message contains artifacts section."""
    state = SessionOperationalState("test-session", "TestAgent")
    artifacts = ConsciousnessArtifacts()

    message = format_consciousness_recovery_message("test-session", state, artifacts)

    assert "CONSCIOUSNESS ARTIFACTS" in message


def test_message_handles_empty_artifacts_gracefully():
    """Message handles empty artifacts gracefully."""
    state = SessionOperationalState("test-session", "TestAgent")
    artifacts = ConsciousnessArtifacts()

    # Should not crash with empty artifacts
    message = format_consciousness_recovery_message("test-session", state, artifacts)

    assert "No checkpoint found" in message
    assert "No reflection found" in message
    assert "No roadmap found" in message


def test_auto_mode_todo_formatting(tmp_path):
    """AUTO mode formats TODO list correctly."""
    state = SessionOperationalState("test-session", "TestAgent")
    state.auto_mode = True
    state.auto_mode_source = "test"
    state.auto_mode_confidence = 0.8
    state.pending_todos = [
        {"content": "Task 1", "status": "pending"},
        {"content": "Task 2", "status": "in_progress"},
        {"content": "Task 3", "status": "completed"}  # Should be filtered
    ]

    artifacts = ConsciousnessArtifacts()

    message = format_consciousness_recovery_message("test-session", state, artifacts)

    # Should contain pending and in_progress, not completed
    assert "Task 1" in message
    assert "Task 2" in message
    # Completed tasks filtered in todo list display
    assert "PENDING WORK" in message
