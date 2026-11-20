"""get_token_info says nothing about a token cache that doesn't exist yet, and still says so about one it can't read (#999).

A session has no token cache until the first write, so a missing file is the normal case on the
first hook calls of every session and a warning there is noise on each of them. A cache that is
there and can't be parsed is a real fault, and the warning stays.
"""
import json
from unittest.mock import patch

import pytest

from macf.utils import get_token_info
from test_get_token_info_compaction_lower_bound import _assistant_event, _write_jsonl

SESSION = "test-session-id-deadbeef"
WHEN = "2026-06-08T10:00:00.000Z"


@pytest.fixture
def session(tmp_path):
    sidecar = tmp_path / "sidecar"
    sidecar.mkdir()
    transcript = tmp_path / "session.jsonl"
    _write_jsonl(transcript, [_assistant_event(WHEN, 123_456)])
    with patch("macf.utils.tokens.get_current_session_id", return_value=SESSION), \
         patch("macf.utils.tokens.get_session_transcript_path", return_value=str(transcript)), \
         patch("macf.utils.tokens.get_session_dir", return_value=sidecar), \
         patch("macf.event_queries.get_latest_compaction_event", return_value=None):
        yield sidecar


def test_a_missing_cache_prints_nothing(session, capsys):
    assert get_token_info()["tokens_used"] == 123_456
    assert capsys.readouterr().err == ""


def test_an_unreadable_cache_is_still_said(session, capsys):
    (session / "token_cache.json").write_text("{not json")
    assert get_token_info()["tokens_used"] == 123_456
    assert "token_cache.json" in capsys.readouterr().err


def test_a_readable_cache_is_used_quietly(session, capsys):
    (session / "token_cache.json").write_text(json.dumps({"session_id": SESSION, "max_tokens_used": 5}))
    assert get_token_info()["tokens_used"] == 123_456
    assert capsys.readouterr().err == ""
