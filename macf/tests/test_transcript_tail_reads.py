"""Hooks read a transcript from its end.

A long-lived session's transcript runs to hundreds of megabytes. The prompt
hook read all of it on every prompt to find the last user message, which was
most of the hook's time; the SessionStart fallback read all of it, up to three
times, to look at its last hundred lines.
"""
import json
from unittest.mock import patch

import pytest

from macf.utils import session as session_mod
from macf.utils.session import get_last_user_prompt_uuid


def _line(**rec):
    return json.dumps(rec) + "\n"


@pytest.fixture
def transcript(tmp_path):
    """Filler, then the real prompt, then the entries that are not prompts."""
    p = tmp_path / "sess-1.jsonl"
    body = [_line(type="assistant", uuid=f"f{i}", message={"role": "assistant", "content": "x"})
            for i in range(2000)]
    body.append(_line(type="user", uuid="the-prompt", message={"role": "user", "content": "do it"}))
    body.append(_line(type="user", uuid="hook", message={"role": "user", "content": "<user-prompt-submit-hook>x"}))
    body.append(_line(type="user", uuid="tool", message={"role": "user", "content": [{"type": "tool_result"}]}))
    body.append(_line(type="assistant", uuid="a1", message={"role": "assistant", "content": "ok"}))
    p.write_text("".join(body))
    return p


def test_the_last_text_prompt_is_found_past_hook_and_tool_entries(transcript):
    assert get_last_user_prompt_uuid("sess-1", transcript_path=str(transcript)) == "the-prompt"


def test_a_given_path_is_used_without_searching(transcript):
    with patch.object(session_mod.Path, "rglob", side_effect=AssertionError("searched")):
        assert get_last_user_prompt_uuid("sess-1", transcript_path=str(transcript)) == "the-prompt"


def test_only_the_tail_is_read(transcript):
    """The prompt is five lines from the end; the 2,000 lines before it are never read."""
    from macf.utils import streaming
    consumed = []
    real = streaming.iter_lines_reverse

    def counting(path, *a, **k):
        for line in real(path, *a, **k):
            consumed.append(line)
            yield line

    with patch.object(streaming, "iter_lines_reverse", counting):
        assert get_last_user_prompt_uuid("sess-1", transcript_path=str(transcript)) == "the-prompt"
    assert 0 < len(consumed) < 10


@pytest.mark.parametrize("filler_after, found", [(99, True), (100, False)])
def test_sessionstart_sees_the_last_hundred_lines(tmp_path, filler_after, found):
    from macf.hooks.compaction import detect_compaction
    p = tmp_path / "t.jsonl"
    lines = [_line(type="system", subtype="compact_boundary")]
    lines += [_line(type="assistant", uuid=f"a{i}") for i in range(filler_after)]
    p.write_text("".join(lines))
    with patch("time.sleep"):
        assert detect_compaction(p) is found


def test_the_prompt_hook_passes_its_transcript_path(transcript):
    from macf.hooks import handle_user_prompt_submit as ups
    with patch("macf.utils.session.get_last_user_prompt_uuid", return_value="u") as spy, \
         patch.object(ups, "start_dev_drv"):
        ups.run(json.dumps({"session_id": "sess-1", "prompt": "", "transcript_path": str(transcript)}))
    assert spy.call_args.kwargs.get("transcript_path") == str(transcript)
