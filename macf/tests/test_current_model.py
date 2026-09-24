"""Tests for current_model(): the one place MACF answers which model the agent is running."""
import json

import pytest

from macf.utils import environment
from macf.utils.environment import current_model, model_display_name
from macf.utils.formatting import format_macf_footer


def write_transcript(path, models):
    with open(path, "w") as f:
        f.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
        for m in models:
            f.write(json.dumps({"type": "assistant", "message": {"model": m, "content": []}}) + "\n")
            f.write(json.dumps({"type": "user", "toolUseResult": "x" * 200_000}) + "\n")  # a large tool result after it


@pytest.fixture
def transcripts(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    here = tmp_path / "this-session.jsonl"
    monkeypatch.setattr("macf.utils.session.get_current_session_id", lambda: "this-session")
    monkeypatch.setattr("macf.utils.paths.get_session_transcript_path", lambda sid: str(tmp_path / f"{sid}.jsonl"))
    return tmp_path, here


@pytest.mark.parametrize("mid,name", [("claude-opus-5-5", "Opus 5.5"), ("claude-fable-5-1", "Fable 5.1"),
                                      ("claude-haiku-4-5-20251001", "Haiku 4.5"), ("claude-sonnet-5", "Sonnet 5"),
                                      ("claude-opus-5-5[1m]", "Opus 5.5"), ("some-other-model", "some-other-model")])
def test_display_names(mid, name):
    assert model_display_name(mid) == name


def test_newest_assistant_message_wins_past_large_tool_results(transcripts):
    """The scan runs backwards until it finds a reply; a 200 KB tool result after it does not hide it."""
    folder, here = transcripts
    write_transcript(here, ["claude-fable-5-1", "claude-opus-5-5"])
    assert current_model() == {"id": "claude-opus-5-5", "display": "Opus 5.5", "source": "transcript"}


def test_new_session_falls_back_to_the_last_seen_transcript(transcripts):
    """A session with no reply yet reports the newest model seen in the project's other transcripts, labelled so."""
    folder, here = transcripts
    here.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
    write_transcript(folder / "previous.jsonl", ["claude-fable-5-1"])
    m = current_model()
    assert m["id"] == "claude-fable-5-1" and m["source"] == "last seen"


def test_explicit_override_and_unknown(transcripts, monkeypatch):
    folder, here = transcripts
    assert current_model()["id"] == "unknown"
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    assert current_model() == {"id": "claude-sonnet-5", "display": "Sonnet 5", "source": "ANTHROPIC_MODEL"}


def test_footer_names_the_model_above_the_version_line(transcripts):
    folder, here = transcripts
    write_transcript(here, ["claude-opus-5-5"])
    lines = format_macf_footer().splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith("🏗️ MACF Tools"))
    assert lines[i - 1] == "Model: Opus 5.5 (claude-opus-5-5)"
