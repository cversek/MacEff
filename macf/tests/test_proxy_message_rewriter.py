"""Tests for proxy message rewriter — Phase 3 of MISSION #117."""

import json
import os
import re
import tempfile

import pytest

from macf.proxy.message_rewriter import (
    FULL_INJECTION_PATTERN,
    MARKER_PATTERN,
    detect_replacement_mode,
    rewrite_messages,
)


def _make_injection(policy_name: str, content: str = "policy content here") -> str:
    """Helper to create a full policy injection tag."""
    return f'<macf-policy-injection policy="{policy_name}">{content}</macf-policy-injection>'


def _make_msg(role: str, content) -> dict:
    """Helper to create a message dict."""
    return {"role": role, "content": content}


class TestRewriteMessagesDeduplicate:
    """Deduplicate mode: keep last occurrence per policy, replace earlier ones."""

    def test_replaces_earlier_duplicates(self):
        """Same policy in msg[1] and msg[3] — msg[1] gets marker, msg[3] kept."""
        inj = _make_injection("task_management", "x" * 5000)
        messages = [
            _make_msg("user", "hello"),
            _make_msg("assistant", f"context {inj} more"),
            _make_msg("user", "continue"),
            _make_msg("assistant", f"later {inj} end"),
        ]

        messages, stats = rewrite_messages(messages, mode="deduplicate")

        assert stats["replacements_made"] == 1
        assert stats["bytes_saved"] > 4000
        assert "task_management" in stats["policies_replaced"]
        # msg[1] should have marker, msg[3] should have full injection
        assert MARKER_PATTERN.search(messages[1]["content"])
        assert FULL_INJECTION_PATTERN.search(messages[3]["content"])

    def test_preserves_different_policies(self):
        """Policy A in msg[1], Policy B in msg[2] — both preserved (no duplicates)."""
        messages = [
            _make_msg("user", "start"),
            _make_msg("assistant", _make_injection("policy_a", "content_a")),
            _make_msg("assistant", _make_injection("policy_b", "content_b")),
        ]

        messages, stats = rewrite_messages(messages, mode="deduplicate")

        assert stats["replacements_made"] == 0
        assert FULL_INJECTION_PATTERN.search(messages[1]["content"])
        assert FULL_INJECTION_PATTERN.search(messages[2]["content"])


class TestRewriteMessagesCleanupAll:
    """Cleanup_all mode: replace ALL policy injections with markers."""

    def test_replaces_everything(self):
        """Two different policies — both replaced with markers."""
        messages = [
            _make_msg("user", "start"),
            _make_msg("assistant", _make_injection("policy_a", "a" * 3000)),
            _make_msg("assistant", _make_injection("policy_b", "b" * 3000)),
        ]

        messages, stats = rewrite_messages(messages, mode="cleanup_all")

        assert stats["replacements_made"] == 2
        assert stats["bytes_saved"] > 5000
        assert MARKER_PATTERN.search(messages[1]["content"])
        assert MARKER_PATTERN.search(messages[2]["content"])
        assert not FULL_INJECTION_PATTERN.search(messages[1]["content"])
        assert not FULL_INJECTION_PATTERN.search(messages[2]["content"])


class TestRewriteMessagesEdgeCases:
    """Edge cases: no injections, list content blocks, existing markers."""

    def test_no_injections_is_noop(self):
        """Messages with no injection tags — no modifications."""
        messages = [
            _make_msg("user", "hello"),
            _make_msg("assistant", "world"),
        ]
        original = json.dumps(messages)

        messages, stats = rewrite_messages(messages)

        assert stats["replacements_made"] == 0
        assert stats["bytes_saved"] == 0
        assert json.dumps(messages) == original

    def test_handles_list_content_blocks(self):
        """Content as list of blocks — correctly finds and replaces."""
        inj = _make_injection("task_management", "x" * 2000)
        messages = [
            _make_msg("user", "start"),
            _make_msg("assistant", [
                {"type": "text", "text": f"before {inj} after"},
                {"type": "image", "source": {"data": "base64..."}},
            ]),
            _make_msg("assistant", [
                {"type": "text", "text": f"second {inj} end"},
            ]),
        ]

        messages, stats = rewrite_messages(messages, mode="deduplicate")

        assert stats["replacements_made"] == 1
        # msg[1] block[0] should have marker
        assert MARKER_PATTERN.search(messages[1]["content"][0]["text"])
        # msg[2] block[0] should have full injection
        assert FULL_INJECTION_PATTERN.search(messages[2]["content"][0]["text"])

    def test_marker_not_double_replaced(self):
        """Existing markers (self-closing tags) are not modified again."""
        marker = '<macf-policy-injection name="old_policy" replaced_at="s_abc/c_1/g_xyz/p_123/t_999" />'
        messages = [
            _make_msg("user", "start"),
            _make_msg("assistant", f"has marker: {marker}"),
            _make_msg("assistant", _make_injection("new_policy", "content")),
        ]

        messages, stats = rewrite_messages(messages, mode="cleanup_all")

        # Only the full injection in msg[2] replaced, not the existing marker in msg[1]
        assert stats["replacements_made"] == 1
        assert marker in messages[1]["content"]  # original marker untouched


class TestDetectReplacementMode:
    """Mode detection from event log."""

    def test_returns_cleanup_all_on_task_completed(self):
        """Event log with task_completed after since_ts -> cleanup_all."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"timestamp": 100.0, "event": "task_started", "data": {}}) + "\n")
            f.write(json.dumps({"timestamp": 200.0, "event": "task_completed", "data": {}}) + "\n")
            f.flush()
            path = f.name

        try:
            assert detect_replacement_mode(path, since_ts=50.0) == "cleanup_all"
        finally:
            os.unlink(path)

    def test_returns_deduplicate_when_no_completion(self):
        """Event log without task_completed -> deduplicate."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"timestamp": 100.0, "event": "task_started", "data": {}}) + "\n")
            f.flush()
            path = f.name

        try:
            assert detect_replacement_mode(path, since_ts=50.0) == "deduplicate"
        finally:
            os.unlink(path)

    def test_missing_log_returns_deduplicate_with_warning(self, capsys):
        """Missing event log -> deduplicate with warning to stderr."""
        result = detect_replacement_mode("/nonexistent/path.jsonl", since_ts=0.0)

        assert result == "deduplicate"
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "not found" in captured.err
