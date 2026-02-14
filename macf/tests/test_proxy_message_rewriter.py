"""Tests for proxy message rewriter — stateless retraction with msg-index linked list."""

import json
import os
import tempfile

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


def _write_event_log(events: list[dict]) -> str:
    """Write events to a temp JSONL file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for event in events:
        f.write(json.dumps(event) + "\n")
    f.flush()
    f.close()
    return f.name


def _event_log_with_active(*policy_names: str) -> str:
    """Create event log where listed policies are activated (not cleared)."""
    events = []
    for name in policy_names:
        events.append({
            "event": "policy_injection_activated",
            "data": {"policy_name": name},
        })
    return _write_event_log(events)


def _event_log_with_cleared(*policy_names: str) -> str:
    """Create event log where listed policies were activated then cleared."""
    events = []
    for name in policy_names:
        events.append({
            "event": "policy_injection_activated",
            "data": {"policy_name": name},
        })
        events.append({
            "event": "policy_injection_cleared",
            "data": {"policy_name": name},
        })
    return _write_event_log(events)


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
        log = _event_log_with_active("task_management")

        try:
            messages, stats = rewrite_messages(messages, log)
            assert stats["replacements_made"] == 1
            assert stats["bytes_saved"] > 4000
            assert "task_management" in stats["deduplicated"]
            # msg[1] should have marker pointing to msg[3]
            assert MARKER_PATTERN.search(messages[1]["content"])
            assert 'replaced_at="3"' in messages[1]["content"]
            # msg[3] should have full injection preserved
            assert FULL_INJECTION_PATTERN.search(messages[3]["content"])
        finally:
            os.unlink(log)

    def test_preserves_different_policies(self):
        """Policy A in msg[1], Policy B in msg[2] — both preserved (no duplicates)."""
        messages = [
            _make_msg("user", "start"),
            _make_msg("user", _make_injection("policy_a", "content_a")),
            _make_msg("user", _make_injection("policy_b", "content_b")),
        ]
        log = _event_log_with_active("policy_a", "policy_b")

        try:
            messages, stats = rewrite_messages(messages, log)
            assert stats["replacements_made"] == 0
        finally:
            os.unlink(log)


class TestRetraction:
    """Cleared policies: replace ALL occurrences with linked-list markers."""

    def test_retracts_single_occurrence(self):
        """One cleared policy — gets retracted_at marker (self-referential)."""
        inj = _make_injection("task_management", "x" * 3000)
        messages = [
            _make_msg("user", "start"),
            _make_msg("user", f"has policy: {inj}"),
        ]
        log = _event_log_with_cleared("task_management")

        try:
            messages, stats = rewrite_messages(messages, log)
            assert stats["replacements_made"] == 1
            assert "task_management" in stats["retracted"]
            assert 'retracted_at="1"' in messages[1]["content"]
            assert not FULL_INJECTION_PATTERN.search(messages[1]["content"])
        finally:
            os.unlink(log)

    def test_retracts_multiple_with_linked_list(self):
        """Cleared policy in msg[1] and msg[3] — forms forward-linked list."""
        inj = _make_injection("task_management", "x" * 3000)
        messages = [
            _make_msg("user", "start"),
            _make_msg("user", f"first: {inj}"),
            _make_msg("assistant", "ok"),
            _make_msg("user", f"second: {inj}"),
        ]
        log = _event_log_with_cleared("task_management")

        try:
            messages, stats = rewrite_messages(messages, log)
            assert stats["replacements_made"] == 2
            assert "task_management" in stats["retracted"]
            # msg[1] points forward to msg[3]
            assert 'replaced_at="3"' in messages[1]["content"]
            # msg[3] is chain terminator (self-referential)
            assert 'retracted_at="3"' in messages[3]["content"]
        finally:
            os.unlink(log)

    def test_selective_retraction(self):
        """One active, one cleared — only cleared gets retracted."""
        messages = [
            _make_msg("user", "start"),
            _make_msg("user", _make_injection("active_policy", "a" * 2000)),
            _make_msg("user", _make_injection("cleared_policy", "b" * 2000)),
        ]
        # active_policy is activated, cleared_policy is cleared
        events = [
            {"event": "policy_injection_activated", "data": {"policy_name": "active_policy"}},
            {"event": "policy_injection_activated", "data": {"policy_name": "cleared_policy"}},
            {"event": "policy_injection_cleared", "data": {"policy_name": "cleared_policy"}},
        ]
        log = _write_event_log(events)

        try:
            messages, stats = rewrite_messages(messages, log)
            assert stats["replacements_made"] == 1
            assert "cleared_policy" in stats["retracted"]
            assert stats["deduplicated"] == []
            # active_policy preserved
            assert FULL_INJECTION_PATTERN.search(messages[1]["content"])
            # cleared_policy retracted
            assert not FULL_INJECTION_PATTERN.search(messages[2]["content"])
            assert MARKER_PATTERN.search(messages[2]["content"])
        finally:
            os.unlink(log)


class TestEdgeCases:
    """Edge cases: no injections, list content blocks, missing event log."""

    def test_no_injections_is_noop(self):
        messages = [
            _make_msg("user", "hello"),
            _make_msg("assistant", "world"),
        ]
        original = json.dumps(messages)
        log = _event_log_with_active()

        try:
            messages, stats = rewrite_messages(messages, log)
            assert stats["replacements_made"] == 0
            assert json.dumps(messages) == original
        finally:
            os.unlink(log)

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
        log = _event_log_with_active("task_management")

        try:
            messages, stats = rewrite_messages(messages, log)
            assert stats["replacements_made"] == 1
            # msg[1] block[0] should have marker
            assert MARKER_PATTERN.search(messages[1]["content"][0]["text"])
            # msg[2] block[0] should have full injection
            assert FULL_INJECTION_PATTERN.search(messages[2]["content"][0]["text"])
        finally:
            os.unlink(log)

    def test_missing_event_log_no_retraction(self):
        """Missing event log — all policies treated as active (no retraction)."""
        inj = _make_injection("task_management", "content")
        messages = [
            _make_msg("user", f"has policy: {inj}"),
        ]

        messages, stats = rewrite_messages(messages, "/nonexistent/path.jsonl")
        assert stats["replacements_made"] == 0

    def test_skips_assistant_messages(self):
        """Injections in assistant messages are ignored (avoids FP from code output)."""
        inj = _make_injection("task_management", "content")
        messages = [
            _make_msg("user", "start"),
            _make_msg("assistant", f"here is the tag: {inj}"),
        ]
        log = _event_log_with_cleared("task_management")

        try:
            messages, stats = rewrite_messages(messages, log)
            assert stats["replacements_made"] == 0
        finally:
            os.unlink(log)


class TestGetActivePolicies:
    """Event log scanning for active policy determination."""

    def test_activated_is_active(self):
        log = _event_log_with_active("policy_a", "policy_b")
        try:
            assert get_active_policies(log) == {"policy_a", "policy_b"}
        finally:
            os.unlink(log)

    def test_cleared_is_not_active(self):
        log = _event_log_with_cleared("policy_a")
        try:
            assert get_active_policies(log) == set()
        finally:
            os.unlink(log)

    def test_reactivated_is_active(self):
        """Activated → cleared → activated again = active."""
        events = [
            {"event": "policy_injection_activated", "data": {"policy_name": "p"}},
            {"event": "policy_injection_cleared", "data": {"policy_name": "p"}},
            {"event": "policy_injection_activated", "data": {"policy_name": "p"}},
        ]
        log = _write_event_log(events)
        try:
            assert get_active_policies(log) == {"p"}
        finally:
            os.unlink(log)

    def test_missing_log_returns_empty(self):
        assert get_active_policies("/nonexistent/log.jsonl") == set()
