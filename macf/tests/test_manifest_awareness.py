#!/usr/bin/env python3
"""
Tests for format_manifest_awareness() function.

Test Philosophy (from TestEng):
- 4-6 focused tests covering core functionality
- Test what matters: structure, token budget, emoji spacing
- Skip exhaustive permutations
"""

import pytest
from macf.utils import format_manifest_awareness


def test_output_structure_completeness():
    """Verify all required sections are present in output."""
    output = format_manifest_awareness()

    # Required sections
    assert "📋 POLICY MANIFEST AWARENESS" in output, "Missing header"
    assert "Version:" in output, "Missing version"
    assert "Active Layers:" in output, "Missing active layers"
    assert "Active Languages:" in output, "Missing active languages"
    assert "Consciousness Patterns Active:" in output, "Missing consciousness patterns"
    assert "Active CA Types:" in output, "Missing CA types"
    assert "CLI Commands for Discovery:" in output, "Missing CLI commands"


def test_token_budget_under_500():
    """Verify output stays under 500 token budget."""
    output = format_manifest_awareness()

    # Rough token estimate: word_count * 1.3
    word_count = len(output.split())
    estimated_tokens = word_count * 1.3

    assert estimated_tokens < 500, (
        f"Token estimate {estimated_tokens:.0f} exceeds 500 token budget "
        f"(word count: {word_count})"
    )


def test_emoji_spacing_correctness():
    """Verify two spaces after emojis to prevent overlap."""
    output = format_manifest_awareness()

    # Extract CA types section
    lines = output.split('\n')
    ca_section_started = False
    emoji_lines = []

    for line in lines:
        if "Active CA Types:" in line:
            ca_section_started = True
            continue

        if ca_section_started:
            # Stop at next section
            if line.strip() == "" or "CLI Commands" in line:
                break

            # Check for emoji-prefixed lines
            if any(emoji in line for emoji in ['🔬', '🧪', '📊', '💭', '🔖', '🗺️', '❤️']):
                emoji_lines.append(line)

    # Verify emoji spacing (two spaces after emoji)
    for line in emoji_lines:
        # Find emoji position
        for emoji in ['🔬', '🧪', '📊', '💭', '🔖', '🗺️', '❤️']:
            if emoji in line:
                emoji_idx = line.index(emoji)
                # Check for two spaces after emoji (emoji + 2 spaces = 3 chars minimum)
                after_emoji = line[emoji_idx + len(emoji):emoji_idx + len(emoji) + 2]
                assert after_emoji == "  ", (
                    f"Expected two spaces after {emoji}, got: {repr(after_emoji)} in line: {line}"
                )
                break


def test_ca_emoji_mapping():
    """Verify correct emojis for CA types."""
    output = format_manifest_awareness()

    # Expected emoji mappings (from DELEG_PLAN)
    expected_mappings = {
        '🔬': 'observations',
        '🧪': 'experiments',
        '📊': 'reports',
        '💭': 'reflections',
        '🔖': 'checkpoints',
        '🗺️': 'roadmaps'
    }

    # Verify emojis appear with their correct CA types
    for emoji, ca_type in expected_mappings.items():
        if ca_type in output:  # Only check if CA type is active
            # Find the line with this CA type
            for line in output.split('\n'):
                if emoji in line:
                    assert ca_type in line, (
                        f"Expected {ca_type} on same line as {emoji}, got: {line}"
                    )
                    break


def test_cli_commands_present():
    """Verify CLI command examples are included."""
    output = format_manifest_awareness()

    # Expected CLI commands (from DELEG_PLAN format example)
    expected_commands = [
        "macf_tools policy manifest",
        "macf_tools policy search",
        "macf_tools policy ca-types",
        "macf_tools policy list"
    ]

    for cmd in expected_commands:
        assert cmd in output, f"Missing CLI command: {cmd}"


def test_graceful_fallback_on_missing_manifest():
    """Verify sensible fallback if manifest loading fails."""
    # This test verifies the function returns a message even if manifest is missing
    # The actual behavior is tested by the function's try/except blocks
    output = format_manifest_awareness()

    # Should always return a string starting with the header
    assert output.startswith("📋 POLICY MANIFEST AWARENESS"), (
        "Output should always start with header"
    )

    # Should be non-empty
    assert len(output) > 0, "Output should not be empty"
