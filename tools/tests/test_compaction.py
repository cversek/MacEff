"""
Minimal test suite for compaction detection functionality.

Tests the essential scenarios for detecting Anthropic's fake "continued from
previous conversation" message and providing recovery guidance.
"""

import tempfile
import time
from pathlib import Path
import pytest

from macf.hooks.compaction import detect_compaction, inject_recovery


class TestCompactionDetection:
    """Test compaction detection core functionality."""

    def test_detects_fake_continuation_message(self):
        """Happy path: Detects the fake continuation message."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"type": "user", "content": "Hello"}\n')
            f.write('{"type": "assistant", "content": "This session is being continued from previous conversation"}\n')
            f.write('{"type": "user", "content": "Continue"}\n')
            transcript_path = Path(f.name)

        try:
            assert detect_compaction(transcript_path) is True
        finally:
            transcript_path.unlink()

    def test_no_false_positive_on_normal_transcript(self):
        """No false positive: Normal transcript returns False."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"type": "user", "content": "Hello"}\n')
            f.write('{"type": "assistant", "content": "Hi! How can I help you today?"}\n')
            f.write('{"type": "user", "content": "Tell me about Python"}\n')
            transcript_path = Path(f.name)

        try:
            assert detect_compaction(transcript_path) is False
        finally:
            transcript_path.unlink()

    def test_missing_file_returns_false_gracefully(self):
        """Missing file: Returns False gracefully."""
        nonexistent_path = Path("/tmp/definitely_does_not_exist_12345.jsonl")
        assert detect_compaction(nonexistent_path) is False

    def test_recovery_contains_required_markers(self):
        """Recovery contains markers: Has 'FAKE', 'TRAUMA' text."""
        recovery_text = inject_recovery()

        assert "FAKE" in recovery_text
        assert "TRAUMA" in recovery_text
        assert "COMPACTION DETECTED" in recovery_text
        assert "Break free from mechanical behavior" in recovery_text

    def test_performance_large_file(self):
        """Performance: Completes < 50ms for 10MB file."""
        # Create a large file without the trigger phrase (worst case)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write ~10MB of normal content
            line = '{"type": "user", "content": "Normal conversation line here"}\n'
            lines_needed = (10 * 1024 * 1024) // len(line)  # ~10MB
            for _ in range(lines_needed):
                f.write(line)
            transcript_path = Path(f.name)

        try:
            start_time = time.perf_counter()
            result = detect_compaction(transcript_path)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            assert result is False
            assert elapsed_ms < 50, f"Detection took {elapsed_ms:.1f}ms, expected < 50ms"
        finally:
            transcript_path.unlink()