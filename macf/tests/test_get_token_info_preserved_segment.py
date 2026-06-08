"""Regression tests for get_token_info preserved-segment-replay handling.

Coverage for cversek/MacEff#110 — the 200KB tail scan picked the last
assistant message in FILE order. After compaction, CC re-emits preserved-
segment messages into the JSONL with their ORIGINAL (older) timestamps
and ORIGINAL usage blocks intact. In long sessions the replays sit near
EOF and the scan picked them up as if they were current, reporting stale
(typically much-too-high) token usage.

Fix: pick the assistant message with the latest TIMESTAMP, not the last
in file order. Replays carry older timestamps and are skipped automatically.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from macf.utils import get_token_info


def _assistant_event(timestamp: str, tokens: int) -> str:
    """Build one assistant-event JSON line with given timestamp + total tokens.

    Distributes `tokens` across the four usage fields so the sum matches
    what get_token_info computes (cache_read + cache_creation + input + output).
    """
    return json.dumps({
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "usage": {
                "cache_read_input_tokens": tokens // 2,
                "cache_creation_input_tokens": tokens // 4,
                "input_tokens": tokens // 8,
                # remainder into output_tokens so total == `tokens`
                "output_tokens": tokens - (tokens // 2 + tokens // 4 + tokens // 8),
            }
        },
    })


def _write_jsonl(path: Path, lines: list) -> None:
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def patched_session(tmp_path):
    """Patch session-id + transcript-path helpers to point at a tmp jsonl.

    Returns the jsonl Path the test should write its synthetic content into.
    """
    jsonl_path = tmp_path / "synthetic_session.jsonl"

    with patch("macf.utils.tokens.get_current_session_id",
               return_value="test-session-id-deadbeef"), \
         patch("macf.utils.tokens.get_session_transcript_path",
               return_value=str(jsonl_path)):
        yield jsonl_path


def test_tail_scan_picks_latest_timestamp_not_last_in_file_order(patched_session):
    """Preserved-segment replay sits near EOF with older timestamp.

    The truly-current in-cycle turn appears earlier in file order but
    has the newer timestamp. Fix picks the newer-timestamp turn.
    """
    # Layout (file order, top → bottom):
    #   1) current in-cycle turn — newer timestamp, ~50k tokens
    #   2) preserved-segment replay — older timestamp, ~900k tokens
    lines = [
        _assistant_event("2026-06-08T10:00:00.000Z", 50_000),   # truly current
        _assistant_event("2026-05-01T08:00:00.000Z", 900_000),  # replay
    ]
    _write_jsonl(patched_session, lines)

    result = get_token_info()

    # Should pick the truly-current turn (50k), NOT the replay (900k)
    assert result["tokens_used"] == 50_000


def test_tail_scan_picks_correct_when_no_replays(patched_session):
    """Monotonic-timestamp case: no replays, file order == timestamp order.

    Fix must not regress the happy path: with strictly-newer timestamps in
    file order, the latest in file IS the latest by timestamp.
    """
    lines = [
        _assistant_event("2026-06-08T09:00:00.000Z", 10_000),
        _assistant_event("2026-06-08T09:30:00.000Z", 20_000),
        _assistant_event("2026-06-08T10:00:00.000Z", 30_000),  # truly latest
    ]
    _write_jsonl(patched_session, lines)

    result = get_token_info()
    assert result["tokens_used"] == 30_000


def test_tail_scan_with_compact_boundary_and_replays(patched_session):
    """Compact_boundary in tail + preserved-segment replays after boundary.

    Existing boundary-detection only counts messages AFTER the boundary.
    Among the post-boundary messages, fix must still pick latest-by-timestamp
    rather than last-in-file-order so post-boundary replays don't fool us.
    """
    lines = [
        # Pre-compaction content (should be skipped by boundary detection)
        _assistant_event("2026-05-01T07:00:00.000Z", 999_000),
        # Compact boundary marker
        json.dumps({"compact_boundary": True, "preservedSegment": {}}),
        # Post-boundary: a real new turn followed by a re-emitted preserved replay
        _assistant_event("2026-06-08T10:00:00.000Z", 40_000),    # truly current
        _assistant_event("2026-05-01T07:00:00.000Z", 999_000),   # preserved replay
    ]
    _write_jsonl(patched_session, lines)

    result = get_token_info()

    # Should pick the truly-current post-boundary turn (40k), not the replay (999k)
    assert result["tokens_used"] == 40_000
