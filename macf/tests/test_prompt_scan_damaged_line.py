"""The prompt scan stays quiet about a cut newest line and speaks about a damaged earlier one (#999).

A live transcript's newest line can be cut mid-write, so it is skipped without a word. A line
further back that does not parse was damaged some other way, and every scan used to skip it silently.
"""
import json

from macf.utils.session import get_last_user_prompt_uuid


def _line(**rec):
    return json.dumps(rec) + "\n"


def _prompt(uuid):
    return _line(type="user", uuid=uuid, message={"role": "user", "content": "do it"})


def _scan(path):
    return get_last_user_prompt_uuid("s", transcript_path=str(path))


def test_a_cut_newest_line_is_skipped_quietly(tmp_path, capsys):
    p = tmp_path / "t.jsonl"
    p.write_text(_prompt("the-prompt") + '{"type": "assistant", "uu')
    assert _scan(p) == "the-prompt"
    assert capsys.readouterr().err == ""


def test_a_damaged_earlier_line_is_said_and_the_search_goes_on(tmp_path, capsys):
    p = tmp_path / "t.jsonl"
    p.write_text(_prompt("the-prompt") + "{damaged\n" + _line(type="assistant", uuid="a", message={"role": "assistant", "content": "ok"}))
    assert _scan(p) == "the-prompt"
    err = capsys.readouterr().err
    assert "does not parse" in err and "t.jsonl" in err


def test_a_clean_transcript_says_nothing(tmp_path, capsys):
    p = tmp_path / "t.jsonl"
    p.write_text(_prompt("the-prompt"))
    assert _scan(p) == "the-prompt"
    assert capsys.readouterr().err == ""
