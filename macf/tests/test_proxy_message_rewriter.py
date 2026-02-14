"""Tests for proxy message rewriter — stateless retraction with msg-index linked list."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from macf.proxy.message_rewriter import (
    FULL_INJECTION_PATTERN,
    MARKER_PATTERN,
    rewrite_messages,
    get_active_policies,
    make_marker,
)


def _make_injection(policy_name: str, content: str = "policy content here") -> str:
    """Helper to create a full policy injection tag."""
    return f'<macf-policy-injection policy="{policy_name}">{content}</macf-policy-injection>'


def _make_msg(role: str, content) -> dict:
    """Helper to create a message dict."""
    return {"role": role, "content": content}


def _mock_active(*policy_names: str):
    """Return a patch that makes get_active_policies return the given set."""
    return patch(
        "macf.proxy.message_rewriter.get_active_policies",
        return_value=set(policy_names),
    )


class TestMakeMarker:
    """Marker generation with message indices."""

    def test_replaced_at_marker(self):
        marker = make_marker("task_management", "replaced_at", 94)
        assert marker == '<macf-policy-injection policy="task_management" replaced_at="94" />'

    def test_retracted_at_marker(self):
        marker = make_marker("task_management", "retracted_at", 50)
        assert marker == '<macf-policy-injection policy="task_management" retracted_at="50" />'

    def test_marker_matches_pattern(self):
        marker = make_marker("coding_standards", "replaced_at", 12)
        assert MARKER_PATTERN.search(marker)


class TestDeduplication:
    """Active policies with duplicates: keep latest, replace earlier ones."""

    def test_replaces_earlier_duplicates(self):
        """Same policy in msg[1] and msg[3] (user role) — msg[1] gets marker."""
        inj = _make_injection("task_management", "x" * 5000)
        messages = [
            _make_msg("user", "hello"),
            _make_msg("user", f"context {inj} more"),
            _make_msg("assistant", "ok"),
            _make_msg("user", f"later {inj} end"),
        ]

        with _mock_active("task_management"):
            messages, stats = rewrite_messages(messages)
            assert stats["replacements_made"] == 1
            assert stats["bytes_saved"] > 4000
            assert "task_management" in stats["deduplicated"]
            # msg[1] should have marker pointing to msg[3]
            assert MARKER_PATTERN.search(messages[1]["content"])
            assert 'replaced_at="3"' in messages[1]["content"]
            # msg[3] should have full injection preserved
            assert FULL_INJECTION_PATTERN.search(messages[3]["content"])

    def test_preserves_different_policies(self):
        """Policy A in msg[1], Policy B in msg[2] — both preserved (no duplicates)."""
        messages = [
            _make_msg("user", "start"),
            _make_msg("user", _make_injection("policy_a", "content_a")),
            _make_msg("user", _make_injection("policy_b", "content_b")),
        ]

        with _mock_active("policy_a", "policy_b"):
            messages, stats = rewrite_messages(messages)
            assert stats["replacements_made"] == 0


class TestRetraction:
    """Cleared policies: replace ALL occurrences with linked-list markers."""

    def test_retracts_single_occurrence(self):
        """One cleared policy — gets retracted_at marker (self-referential)."""
        inj = _make_injection("task_management", "x" * 3000)
        messages = [
            _make_msg("user", "start"),
            _make_msg("user", f"has policy: {inj}"),
        ]

        with _mock_active():  # no active policies
            messages, stats = rewrite_messages(messages)
            assert stats["replacements_made"] == 1
            assert "task_management" in stats["retracted"]
            assert 'retracted_at="1"' in messages[1]["content"]
            assert not FULL_INJECTION_PATTERN.search(messages[1]["content"])

    def test_retracts_multiple_with_linked_list(self):
        """Cleared policy in msg[1] and msg[3] — forms forward-linked list."""
        inj = _make_injection("task_management", "x" * 3000)
        messages = [
            _make_msg("user", "start"),
            _make_msg("user", f"first: {inj}"),
            _make_msg("assistant", "ok"),
            _make_msg("user", f"second: {inj}"),
        ]

        with _mock_active():  # no active policies
            messages, stats = rewrite_messages(messages)
            assert stats["replacements_made"] == 2
            assert "task_management" in stats["retracted"]
            # msg[1] points forward to msg[3]
            assert 'replaced_at="3"' in messages[1]["content"]
            # msg[3] is chain terminator (self-referential)
            assert 'retracted_at="3"' in messages[3]["content"]

    def test_selective_retraction(self):
        """One active, one cleared — only cleared gets retracted."""
        messages = [
            _make_msg("user", "start"),
            _make_msg("user", _make_injection("active_policy", "a" * 2000)),
            _make_msg("user", _make_injection("cleared_policy", "b" * 2000)),
        ]

        with _mock_active("active_policy"):  # only active_policy is active
            messages, stats = rewrite_messages(messages)
            assert stats["replacements_made"] == 1
            assert "cleared_policy" in stats["retracted"]
            assert stats["deduplicated"] == []
            # active_policy preserved
            assert FULL_INJECTION_PATTERN.search(messages[1]["content"])
            # cleared_policy retracted
            assert not FULL_INJECTION_PATTERN.search(messages[2]["content"])
            assert MARKER_PATTERN.search(messages[2]["content"])


class TestEdgeCases:
    """Edge cases: no injections, list content blocks, missing event log."""

    def test_no_injections_is_noop(self):
        messages = [
            _make_msg("user", "hello"),
            _make_msg("assistant", "world"),
        ]
        original = json.dumps(messages)
        # get_active_policies not even called — no injections found
        messages, stats = rewrite_messages(messages)
        assert stats["replacements_made"] == 0
        assert json.dumps(messages) == original

    def test_handles_list_content_blocks(self):
        """Content as list of blocks — correctly finds and replaces."""
        inj = _make_injection("task_management", "x" * 2000)
        messages = [
            _make_msg("user", "start"),
            _make_msg("user", [
                {"type": "text", "text": f"before {inj} after"},
            ]),
            _make_msg("user", [
                {"type": "text", "text": f"second {inj} end"},
            ]),
        ]

        with _mock_active("task_management"):
            messages, stats = rewrite_messages(messages)
            assert stats["replacements_made"] == 1
            # msg[1] block[0] should have marker
            assert MARKER_PATTERN.search(messages[1]["content"][0]["text"])
            # msg[2] block[0] should have full injection
            assert FULL_INJECTION_PATTERN.search(messages[2]["content"][0]["text"])

    def test_no_active_tasks_retracts_all(self):
        """No active tasks — all policies retracted."""
        inj = _make_injection("task_management", "content")
        messages = [
            _make_msg("user", f"has policy: {inj}"),
        ]

        with _mock_active():  # empty set
            messages, stats = rewrite_messages(messages)
            assert stats["replacements_made"] == 1
            assert "task_management" in stats["retracted"]

    def test_skips_assistant_messages(self):
        """Injections in assistant messages are ignored (avoids FP from code output)."""
        inj = _make_injection("task_management", "content")
        messages = [
            _make_msg("user", "start"),
            _make_msg("assistant", f"here is the tag: {inj}"),
        ]

        with _mock_active():  # even with no active, assistant msg is skipped
            messages, stats = rewrite_messages(messages)
            assert stats["replacements_made"] == 0


class TestGetActivePolicies:
    """Task-state-based active policy determination via manifest lookup."""

    def test_active_bug_task_returns_bug_policies(self):
        """In_progress BUG task → coding_standards, debugging_and_validation, task_management."""
        with patch("macf.task.events.get_active_tasks_from_events", return_value={"127": "BUG"}), \
             patch("macf.utils.manifest.get_policies_for_task_type", return_value=["coding_standards", "debugging_and_validation", "task_management"]):
            result = get_active_policies()
            assert result == {"coding_standards", "debugging_and_validation", "task_management"}

    def test_no_active_tasks_returns_empty(self):
        """No in_progress tasks → empty set."""
        with patch("macf.proxy.message_rewriter.get_active_policies", wraps=get_active_policies):
            with patch("macf.task.events.get_active_tasks_from_events", return_value={}):
                result = get_active_policies()
                assert result == set()

    def test_multiple_tasks_union_policies(self):
        """Two active tasks — policies are union of both."""
        def mock_policies(task_type):
            return {
                "BUG": ["coding_standards", "task_management"],
                "MISSION": ["roadmaps_following", "task_management"],
            }.get(task_type, [])

        with patch("macf.task.events.get_active_tasks_from_events", return_value={"127": "BUG", "117": "MISSION"}), \
             patch("macf.utils.manifest.get_policies_for_task_type", side_effect=mock_policies):
            result = get_active_policies()
            assert result == {"coding_standards", "task_management", "roadmaps_following"}
