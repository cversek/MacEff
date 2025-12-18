#!/usr/bin/env python3
"""Tests for consciousness recovery message formatting."""

import pytest

from macf.hooks.recovery import format_consciousness_recovery_message
from macf.utils import ConsciousnessArtifacts


def test_auto_mode_includes_authorized():
    """AUTO mode includes 'AUTHORIZED' in message."""
    artifacts = ConsciousnessArtifacts()

    message = format_consciousness_recovery_message(
        session_id="test-session",
        auto_mode=True,
        compaction_count=1,
        artifacts=artifacts
    )

    assert "AUTHORIZED" in message
    assert "AUTO_MODE" in message


def test_manual_mode_includes_stop_warning():
    """MANUAL mode includes 'STOP' or 'DO NOT' warning."""
    artifacts = ConsciousnessArtifacts()

    message = format_consciousness_recovery_message(
        session_id="test-session",
        auto_mode=False,
        compaction_count=1,
        artifacts=artifacts
    )

    assert "STOP" in message or "DO NOT" in message
    assert "MANUAL MODE" in message


def test_message_contains_artifacts_section():
    """Message contains artifacts section."""
    artifacts = ConsciousnessArtifacts()

    message = format_consciousness_recovery_message(
        session_id="test-session",
        auto_mode=False,
        compaction_count=1,
        artifacts=artifacts
    )

    assert "CONSCIOUSNESS ARTIFACTS" in message


def test_message_handles_empty_artifacts_gracefully():
    """Message handles empty artifacts gracefully."""
    artifacts = ConsciousnessArtifacts()

    # Should not crash with empty artifacts
    message = format_consciousness_recovery_message(
        session_id="test-session",
        auto_mode=False,
        compaction_count=1,
        artifacts=artifacts
    )

    assert "No checkpoint found" in message
    assert "No reflection found" in message
    assert "No roadmap found" in message
