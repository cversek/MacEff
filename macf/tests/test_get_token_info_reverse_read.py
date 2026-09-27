"""get_token_info reads the transcript backwards when its 200 KB tail has nothing usable.

The fallback used to be a forward scan of the whole transcript. It runs on the first
tool call or two after every compaction, when the tail holds only the preserved
segment and the `compact_boundary` marker sits further back (about 0.7 MB on a
long-lived deployment): about 3 s per call on a 660 MB transcript, twice per
PreToolUse. Read backwards, the answer is either the newest in-cycle reply or the
marker, whichever comes first, and both are near the end.
"""
import json
from unittest.mock import patch

import pytest

from macf.utils import get_token_info
from test_get_token_info_compaction_lower_bound import (
    _assistant_event, _compaction_event, _write_jsonl)

SESSION = "test-session-id-deadbeef"
BEFORE, COMPACTED, AFTER = "2026-06-08T10:00:00.000Z", "2026-06-08T10:05:00.000Z", "2026-06-08T10:06:00.000Z"
MARKER = json.dumps({"type": "system", "subtype": "compact_boundary", "timestamp": COMPACTED})


def _filler(kb):
    """A user line of about `kb` KB, the size of a preserved segment or a big tool result."""
    return json.dumps({"type": "user", "timestamp": BEFORE, "message": {"content": "x" * (kb * 1024)}})


@pytest.fixture
def transcript(tmp_path):
    path = tmp_path / "session.jsonl"
    with patch("macf.utils.tokens.get_current_session_id", return_value=SESSION), \
         patch("macf.utils.tokens.get_session_transcript_path", return_value=str(path)):
        yield path


def _info(compacted=True):
    event = _compaction_event(SESSION, COMPACTED) if compacted else None
    with patch("macf.event_queries.get_latest_compaction_event", return_value=event):
        return get_token_info()


def test_a_marker_beyond_the_tail_gives_the_post_compaction_estimate(transcript):
    """A preserved-segment replay after the marker keeps its old timestamp and is skipped."""
    replay = _assistant_event(BEFORE, 940_000)
    _write_jsonl(transcript, [_assistant_event(BEFORE, 950_000), MARKER, replay, _filler(400)])
    result = _info()
    assert result["source"] == "post_compaction_estimate", result
    assert result["tokens_used"] not in (950_000, 940_000)


def test_a_reply_pushed_out_of_the_tail_is_still_found(transcript):
    _write_jsonl(transcript, [_assistant_event(AFTER, 123_456), _filler(300)])
    assert _info(compacted=False)["tokens_used"] == 123_456


def test_the_read_stops_at_the_marker(transcript):
    """Counted, not timed: the work before the marker must not be parsed."""
    old_cycle = [_assistant_event(BEFORE, 500_000 + i) for i in range(5000)]
    _write_jsonl(transcript, old_cycle + [MARKER, _filler(300)])
    real = json.loads
    parses = {"n": 0}

    def counting(*a, **kw):
        parses["n"] += 1
        return real(*a, **kw)

    with patch("macf.utils.tokens.json.loads", side_effect=counting):
        result = _info()
    assert result["source"] == "post_compaction_estimate", result
    assert parses["n"] < 50, parses


def test_a_line_that_only_mentions_the_marker_does_not_stop_the_read(transcript):
    mention = json.dumps({"type": "user", "timestamp": AFTER, "message": {"content": "compact_boundary"}})
    _write_jsonl(transcript, [MARKER, _assistant_event(AFTER, 777_000), mention, _filler(300)])
    assert _info()["tokens_used"] == 777_000
