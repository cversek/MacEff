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


# --- an agent's own recovery banner (.maceff/recovery_header.md) ---------------------------------

def _message(monkeypatch, home, auto_mode=True):
    monkeypatch.setattr("macf.hooks.recovery.find_agent_home", lambda: home)
    return format_consciousness_recovery_message(session_id="s", auto_mode=auto_mode, compaction_count=1,
                                                 artifacts=ConsciousnessArtifacts())


def test_without_a_header_file_the_framework_banner_is_used(monkeypatch, tmp_path):
    assert "COMPACTION TRAUMA DETECTED" in _message(monkeypatch, tmp_path)


def test_an_agents_own_header_replaces_the_banner_and_keeps_the_essentials_first(monkeypatch, tmp_path):
    (tmp_path / ".maceff").mkdir()
    (tmp_path / ".maceff" / "recovery_header.md").write_text("A compaction happened. Read the record.\n")
    message = _message(monkeypatch, tmp_path)
    assert "A compaction happened. Read the record." in message
    assert "COMPACTION TRAUMA DETECTED" not in message
    # The essentials still open the message (#802), and the mode's section still follows.
    assert message.index("RECOVERY ESSENTIALS") < message.index("A compaction happened")
    assert "AUTHORIZED" in message
    assert "MANUAL MODE" in _message(monkeypatch, tmp_path, auto_mode=False)


def test_an_empty_or_unreadable_header_file_falls_back_and_an_unreadable_one_says_so(monkeypatch, tmp_path, capsys):
    (tmp_path / ".maceff").mkdir()
    header = tmp_path / ".maceff" / "recovery_header.md"
    header.write_text("  \n")
    assert "COMPACTION TRAUMA DETECTED" in _message(monkeypatch, tmp_path)
    header.write_bytes(b"\xff\xfe not utf-8 \xff")
    assert "COMPACTION TRAUMA DETECTED" in _message(monkeypatch, tmp_path)
    assert "could not read" in capsys.readouterr().err
