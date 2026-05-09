"""Unit tests for recoverable-error pattern registry and transcript scanner.

Covers:
  - Each pattern in the registry produces a useful directive on a real
    error string sampled from CC tool-result transcripts.
  - The scanner correctly walks the JSONL backwards and identifies the
    most recent tool_result.
  - Self-gating behavior: if the most recent tool_result is a SUCCESS
    (agent already recovered), the scanner returns None even if there
    are older errors in the transcript.
  - Robustness: missing transcript, malformed JSON lines, unknown error
    text — none crash the scanner.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from macf.hooks.recoverable_errors import (
    PATTERNS,
    match_error_text,
    scan_last_tool_error,
)


# --- Per-pattern matching --------------------------------------------------

@pytest.mark.parametrize(
    "expected_name, error_text",
    [
        (
            "file_not_read",
            "<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>",
        ),
        (
            "file_modified_since_read",
            "<tool_use_error>File has been modified since read, either by the user or by a linter. Read it again before attempting to write it.</tool_use_error>",
        ),
        (
            "old_string_not_found",
            "<tool_use_error>String to replace not found in file.\nString: foo bar</tool_use_error>",
        ),
        (
            "replace_all_mismatch",
            "<tool_use_error>Found 5 matches of the string to replace, but expected 1 occurrence. Use replace_all=true or make old_string more specific.</tool_use_error>",
        ),
        (
            "tool_not_in_registry",
            "<tool_use_error>Error: No such tool available: WebFetch</tool_use_error>",
        ),
        (
            "input_validation_error",
            "<tool_use_error>InputValidationError: Read failed due to the following issue:\nThe parameter `offset` type is expected as `number` but provided as `string`</tool_use_error>",
        ),
        (
            "path_does_not_exist",
            "<tool_use_error>Path does not exist: /Users/cversek/gitwork/cversek/MacEff/macf_tools</tool_use_error>",
        ),
        (
            "file_does_not_exist",
            "<tool_use_error>File does not exist.</tool_use_error>",
        ),
        (
            "file_does_not_exist",  # variant with "Did you mean" suggestion
            "<tool_use_error>File does not exist. Did you mean utils?</tool_use_error>",
        ),
    ],
)
def test_pattern_matches_real_error(expected_name: str, error_text: str):
    """Each registered pattern matches a real error string sampled from
    CC transcripts and produces a non-empty directive.
    """
    result = match_error_text(error_text)
    assert result is not None, f"Pattern {expected_name!r} did not match: {error_text}"
    name, directive = result
    assert name == expected_name
    assert directive and len(directive) > 20  # non-trivial directive
    # Sanity: directive shouldn't contain raw {placeholder} markers
    assert "{" not in directive or "[template-render-error:" in directive


def test_replace_all_mismatch_extracts_counts():
    """replace_all_mismatch directive should mention the actual numbers."""
    text = "<tool_use_error>Found 7 matches of the string to replace, but expected 1 occurrence.</tool_use_error>"
    result = match_error_text(text)
    assert result is not None
    name, directive = result
    assert name == "replace_all_mismatch"
    assert "7" in directive and "1" in directive


def test_tool_not_in_registry_extracts_name():
    text = "<tool_use_error>Error: No such tool available: WebSearch</tool_use_error>"
    result = match_error_text(text)
    assert result is not None
    name, directive = result
    assert name == "tool_not_in_registry"
    assert "WebSearch" in directive
    assert "select:WebSearch" in directive


def test_path_suggestion_folded_into_directive():
    """When CC includes a 'Did you mean X?' suggestion, the directive
    surfaces it explicitly so the agent can act on it directly."""
    text = "<tool_use_error>File does not exist. Did you mean utils?</tool_use_error>"
    result = match_error_text(text)
    assert result is not None
    name, directive = result
    assert name == "file_does_not_exist"
    assert "Did you mean: utils" in directive


def test_path_does_not_exist_extracts_path():
    text = "<tool_use_error>Path does not exist: /Users/cversek/gitwork/cversek/MacEff/macf_tools</tool_use_error>"
    result = match_error_text(text)
    assert result is not None
    name, directive = result
    assert name == "path_does_not_exist"
    assert "/Users/cversek/gitwork/cversek/MacEff/macf_tools" in directive


# --- Non-matches (must return None) ----------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "",
        None,
        "<tool_use_error>Cannot create new file - file already exists.</tool_use_error>",
        "<tool_use_error>Cancelled: parallel tool call Bash(...) errored</tool_use_error>",
        "[Request interrupted by user for tool use]",
        "Some random non-error text",
    ],
)
def test_unknown_or_unrecoverable_returns_none(text):
    """Errors NOT in the registry must return None — the gate stays
    out of the way for unrecoverable or user-induced cancellations.
    """
    assert match_error_text(text) is None


# --- Pattern catalog integrity ---------------------------------------------

def test_pattern_names_unique():
    names = [p[0] for p in PATTERNS]
    assert len(names) == len(set(names)), f"Duplicate pattern names: {names}"


def test_all_patterns_compile():
    """Sanity: every pattern compiled at import time."""
    for name, regex, template in PATTERNS:
        assert regex is not None
        assert template


# --- Transcript scanner ----------------------------------------------------

def _write_transcript(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def _user_tool_result(error_text: str, is_error: bool = True) -> dict:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_test",
                    "content": error_text,
                    "is_error": is_error,
                }
            ],
        },
    }


def _user_text(text: str) -> dict:
    return {
        "type": "user",
        "message": {"role": "user", "content": text},
    }


def test_scanner_finds_most_recent_error(tmp_path: Path):
    """Most recent tool_result is an error → return matched directive."""
    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, [
        _user_text("hello"),
        _user_tool_result("<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>"),
    ])
    result = scan_last_tool_error(str(transcript))
    assert result is not None
    name, directive = result
    assert name == "file_not_read"
    assert "Read" in directive


def test_scanner_self_gates_on_successful_recovery(tmp_path: Path):
    """If the agent already recovered (most recent tool_result is success),
    the scanner returns None even when older errors exist."""
    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, [
        # Older error (agent saw, then fixed)
        _user_tool_result("<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>"),
        # More recent success
        _user_tool_result("File contents OK", is_error=False),
    ])
    assert scan_last_tool_error(str(transcript)) is None


def test_scanner_handles_missing_transcript():
    assert scan_last_tool_error("/nonexistent/path.jsonl") is None
    assert scan_last_tool_error("") is None


def test_scanner_skips_malformed_json(tmp_path: Path):
    """A malformed line in the middle should not crash the scanner."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "not valid json\n"
        + json.dumps(_user_tool_result("<tool_use_error>File has not been read yet. Read it.</tool_use_error>"))
        + "\n"
    )
    result = scan_last_tool_error(str(transcript))
    assert result is not None
    assert result[0] == "file_not_read"


def test_scanner_returns_none_when_no_match(tmp_path: Path):
    """Tool error that doesn't match any registry pattern → None."""
    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, [
        _user_tool_result("<tool_use_error>Some unrecognized error text</tool_use_error>"),
    ])
    assert scan_last_tool_error(str(transcript)) is None
