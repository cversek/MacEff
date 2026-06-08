"""Regression tests for get_token_info compaction-event lower-bound filter.

Coverage for cversek/MacEff#111 — the 200KB tail scan can't reliably find
the ``compact_boundary`` line in long-running transcripts (it sits >200KB
from EOF), so post-compaction reads were returning the pre-compaction
final turn's token usage. Fix queries the most recent ``compaction_detected``
event for this session via ``event_queries.get_latest_compaction_event`` and
uses that event's epoch timestamp as a lower bound on accepted assistant-
message timestamps. The bound is converted to Claude Code's transcript ISO
format (``YYYY-MM-DDTHH:MM:SS.mmmZ``) so it sorts lexicographically against
the assistant-message ``timestamp`` strings, matching the cycle-518
timestamp-priority selector's comparator.

This filter also subsumes the cycle-518 #110 fix because preserved-segment
replays carry their ORIGINAL (older) timestamps — they're rejected by the
same lower-bound check.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from macf.utils import get_token_info


def _assistant_event(timestamp: str, tokens: int) -> str:
    """One assistant-event JSON line with given timestamp + total tokens."""
    return json.dumps({
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "usage": {
                "cache_read_input_tokens": tokens // 2,
                "cache_creation_input_tokens": tokens // 4,
                "input_tokens": tokens // 8,
                "output_tokens": tokens - (tokens // 2 + tokens // 4 + tokens // 8),
            }
        },
    })


def _write_jsonl(path: Path, lines: list) -> None:
    path.write_text("\n".join(lines) + "\n")


def _epoch_for(iso: str) -> float:
    """ISO-8601 (with trailing Z) → epoch float."""
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    return datetime.fromisoformat(iso).timestamp()


def _compaction_event(session_id: str, iso: str) -> dict:
    """Fake event-record shape that get_latest_compaction_event would return."""
    return {
        "event": "compaction_detected",
        "timestamp": _epoch_for(iso),
        "breadcrumb": "s_test/c_test/g_test/p_test/t_test",
        "data": {
            "session_id": session_id,
            "cycle": 100,
            "detection_method": "source_field",
            "compaction_count": 1,
        },
        "hook_input": {},
    }


@pytest.fixture
def patched_session(tmp_path):
    """Patch session-id + transcript-path helpers to point at a tmp jsonl."""
    jsonl_path = tmp_path / "synthetic_session.jsonl"

    with patch("macf.utils.tokens.get_current_session_id",
               return_value="test-session-id-deadbeef"), \
         patch("macf.utils.tokens.get_session_transcript_path",
               return_value=str(jsonl_path)):
        yield jsonl_path


def test_lower_bound_filters_pre_compaction_messages(patched_session):
    """Compaction event timestamp filters out pre-compaction final turn.

    Repro of the #111 bug: a long-running session has its `compact_boundary`
    line >200KB from EOF. The tail scan finds the pre-compaction final
    assistant message (latest in file order) and treats it as current.
    With the lower-bound filter, that message is rejected because its
    timestamp is older than the recorded compaction.
    """
    pre_compaction_iso = "2026-06-08T10:00:00.000Z"
    compaction_iso = "2026-06-08T10:05:00.000Z"
    post_compaction_iso = "2026-06-08T10:10:00.000Z"

    lines = [
        _assistant_event(pre_compaction_iso, 950_000),  # pre-compaction final
        _assistant_event(post_compaction_iso, 40_000),  # truly current
    ]
    _write_jsonl(patched_session, lines)

    fake_event = _compaction_event("test-session-id-deadbeef", compaction_iso)
    with patch("macf.event_queries.get_latest_compaction_event",
               return_value=fake_event):
        result = get_token_info()

    # Truly current value, not the pre-compaction stale 950k
    assert result["tokens_used"] == 40_000


def test_lower_bound_with_only_pre_compaction_messages(patched_session):
    """All assistant messages are pre-compaction → filter rejects everything.

    This is the "compaction just happened, no in-cycle assistant message yet"
    case. The function falls through to the default fallback (CL 100 / 0
    tokens) — not to the pre-compaction stale value. Confirms the filter
    fails CLOSED, not OPEN.
    """
    pre_compaction_iso = "2026-06-08T10:00:00.000Z"
    compaction_iso = "2026-06-08T10:05:00.000Z"

    lines = [_assistant_event(pre_compaction_iso, 950_000)]
    _write_jsonl(patched_session, lines)

    fake_event = _compaction_event("test-session-id-deadbeef", compaction_iso)
    with patch("macf.event_queries.get_latest_compaction_event",
               return_value=fake_event):
        result = get_token_info()

    # No eligible message → default fallback (0 tokens used, source="default")
    # NOT 950k pre-compaction stale.
    assert result["tokens_used"] != 950_000
    assert result["tokens_used"] == 0


def test_no_compaction_event_preserves_legacy_behavior(patched_session):
    """No compaction event for this session → bound is "" → no filtering.

    Backward-compat: fresh sessions and legacy sessions with no recorded
    compaction must read tokens exactly as the cycle-518 timestamp-priority
    selector does.
    """
    lines = [
        _assistant_event("2026-06-08T09:00:00.000Z", 10_000),
        _assistant_event("2026-06-08T09:30:00.000Z", 20_000),
        _assistant_event("2026-06-08T10:00:00.000Z", 30_000),
    ]
    _write_jsonl(patched_session, lines)

    with patch("macf.event_queries.get_latest_compaction_event",
               return_value=None):
        result = get_token_info()

    assert result["tokens_used"] == 30_000


def test_lower_bound_also_filters_preserved_segment_replays(patched_session):
    """Subsumes #110: preserved-segment replays carry pre-compaction timestamps.

    Layout (file order): truly-current turn (latest timestamp) + replay
    near EOF (older timestamp). Cycle-518 fix relied on timestamp-priority
    alone; this fix additionally filters via the compaction-event bound.
    Both mechanisms agree on rejecting the replay.
    """
    compaction_iso = "2026-06-08T09:30:00.000Z"
    current_iso = "2026-06-08T10:00:00.000Z"
    replay_iso = "2026-05-01T08:00:00.000Z"  # original pre-compaction timestamp

    lines = [
        _assistant_event(current_iso, 50_000),    # truly current
        _assistant_event(replay_iso, 900_000),    # preserved-segment replay
    ]
    _write_jsonl(patched_session, lines)

    fake_event = _compaction_event("test-session-id-deadbeef", compaction_iso)
    with patch("macf.event_queries.get_latest_compaction_event",
               return_value=fake_event):
        result = get_token_info()

    assert result["tokens_used"] == 50_000


def test_helper_returns_iso_format_matching_cc_transcript_style():
    """_compaction_lower_bound_iso must produce a string that lex-sorts
    against CC's transcript timestamps. CC uses
    ``YYYY-MM-DDTHH:MM:SS.mmmZ`` with trailing Z (NOT ``+00:00``).
    Lex-sort works because the Z literal appears in the same character
    position in both strings.
    """
    from macf.utils.tokens import _compaction_lower_bound_iso
    fake_event = _compaction_event(
        "test-session-id-deadbeef",
        "2026-06-08T12:34:56.789Z",
    )
    with patch("macf.event_queries.get_latest_compaction_event",
               return_value=fake_event):
        bound = _compaction_lower_bound_iso("test-session-id-deadbeef")

    # Must end with Z (not +00:00) and be lexicographically comparable
    assert bound.endswith("Z")
    # The bound must sort BELOW any later assistant-message timestamp
    assert bound < "2026-06-08T13:00:00.000Z"
    # And ABOVE any earlier one
    assert bound > "2026-06-08T12:00:00.000Z"


def test_helper_returns_empty_when_no_session_id():
    """No session_id → empty bound (no filtering, no event-log scan)."""
    from macf.utils.tokens import _compaction_lower_bound_iso
    assert _compaction_lower_bound_iso("") == ""


def test_helper_returns_empty_when_no_compaction_event():
    """No matching event → empty bound, function still returns cleanly."""
    from macf.utils.tokens import _compaction_lower_bound_iso
    with patch("macf.event_queries.get_latest_compaction_event",
               return_value=None):
        assert _compaction_lower_bound_iso("test-session-id-deadbeef") == ""
