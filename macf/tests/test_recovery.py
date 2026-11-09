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


# What recovery depends on arrives in a preview (#802). Claude Code keeps a long hook context in a
# file and shows the model a short preview; the recovery message runs to about 35 KB, and the
# artifact list and the authorization used to sit past the preview, so they never arrived.
PREVIEW_BYTES = 1500


def _artifacts(tmp_path):
    files = {kind: tmp_path / f"{kind}.md" for kind in ("reflection", "checkpoint", "roadmap")}
    for f in files.values():
        f.write_text("x")
    return ConsciousnessArtifacts(reflections=[files["reflection"]], checkpoints=[files["checkpoint"]],
                                  roadmaps=[files["roadmap"]]), files


@pytest.mark.parametrize("auto_mode", [True, False])
def test_the_mode_and_the_artifacts_to_read_come_within_the_preview(tmp_path, auto_mode):
    artifacts, files = _artifacts(tmp_path)
    message = format_consciousness_recovery_message(
        session_id="test-session", auto_mode=auto_mode, compaction_count=1, artifacts=artifacts)
    preview = message.encode()[:PREVIEW_BYTES].decode(errors="ignore")
    assert ("AUTO_MODE" if auto_mode else "MANUAL MODE") in preview
    assert str(files["reflection"]) in preview and str(files["checkpoint"]) in preview
    assert "has not been read" in preview
    assert (str(files["roadmap"]) in preview) is auto_mode   # MANUAL reads the roadmap on the user's word


def test_a_failed_discovery_says_unknown_in_the_preview_too(tmp_path):
    artifacts = ConsciousnessArtifacts(error="permission denied")
    message = format_consciousness_recovery_message(
        session_id="test-session", auto_mode=True, compaction_count=1, artifacts=artifacts)
    preview = message.encode()[:PREVIEW_BYTES].decode(errors="ignore")
    assert "UNKNOWN: artifact discovery failed" in preview and "none found" not in preview
