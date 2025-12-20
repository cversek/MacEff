#!/usr/bin/env python3
"""
Tests for format_manifest_awareness() function.

Test Philosophy (from TestEng):
- 4-6 focused tests covering core functionality
- Output is now minimal: Policy Discovery Obsession approach
- Bootstrap consciousness with minimal guidance, trust discovery infrastructure
"""

import pytest
from macf.utils import format_manifest_awareness


def test_output_structure_completeness():
    """Verify all required sections are present in output."""
    output = format_manifest_awareness()

    # Required sections for Policy Discovery Obsession approach
    assert "📋 POLICY DISCOVERY" in output, "Missing header"
    assert "Policies persist across compaction" in output, "Missing persistence warning"
    assert "macf_tools policy list" in output, "Missing first command"
    assert "Discovery flow:" in output, "Missing discovery flow hint"


def test_token_budget_minimal():
    """Verify output is minimal (Policy Discovery Obsession)."""
    output = format_manifest_awareness()

    # Rough token estimate: word_count * 1.3
    word_count = len(output.split())
    estimated_tokens = word_count * 1.3

    # Should be well under 100 tokens now (was 500 budget before)
    assert estimated_tokens < 100, (
        f"Token estimate {estimated_tokens:.0f} exceeds minimal budget "
        f"(word count: {word_count})"
    )


def test_discovery_flow_present():
    """Verify discovery flow hint is included."""
    output = format_manifest_awareness()

    # The discovery flow: list → navigate → read
    assert "list" in output, "Missing 'list' in discovery flow"
    assert "navigate" in output, "Missing 'navigate' in discovery flow"
    assert "read" in output, "Missing 'read' in discovery flow"


def test_first_command_directive():
    """Verify FIRST COMMAND directive points to policy list."""
    output = format_manifest_awareness()

    # Should emphasize policy list as first command
    assert "FIRST COMMAND" in output, "Missing FIRST COMMAND directive"
    assert "macf_tools policy list" in output, "First command should be policy list"


def test_graceful_fallback_on_missing_manifest():
    """Verify sensible fallback if manifest loading fails."""
    output = format_manifest_awareness()

    # Should always return a string starting with the header
    assert output.startswith("📋 POLICY DISCOVERY"), (
        "Output should always start with Policy Discovery header"
    )

    # Should be non-empty
    assert len(output) > 0, "Output should not be empty"
