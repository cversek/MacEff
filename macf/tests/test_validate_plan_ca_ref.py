"""
Unit tests for validate_plan_ca_ref() function.

Tests validation logic that rejects Claude Code native plan paths
(~/.claude/plans/*.md) which are not MacEff-compliant Consciousness Artifacts.
"""

import os
from pathlib import Path

import pytest

from macf.task.create import validate_plan_ca_ref


class TestValidatePlanCaRef:
    """Test suite for plan CA reference validation."""

    def test_none_input_passes(self):
        """None input should pass without error (no-op case)."""
        # Should not raise
        validate_plan_ca_ref(None)

    def test_valid_relative_ca_path_passes(self):
        """Valid MacEff CA paths should pass validation."""
        valid_paths = [
            "agent/public/roadmaps/2026-01-01_Foo/roadmap.md",
            "agent/public/experiments/2026-01-01_120000_001_Bar/protocol.md",
            "agent/public/roadmaps/2026-02-10_Test/subplan.md",
        ]

        for path in valid_paths:
            # Should not raise
            validate_plan_ca_ref(path)

    def test_cc_plan_path_with_tilde_fails(self):
        """CC plan path with tilde notation should raise ValueError."""
        cc_plan_path = "~/.claude/plans/enchanted-hopping-knuth.md"

        with pytest.raises(ValueError) as exc_info:
            validate_plan_ca_ref(cc_plan_path)

        # Verify error message mentions CC native plans
        assert "CC native plans" in str(exc_info.value)
        assert "~/.claude/plans/" in str(exc_info.value)

    def test_fully_expanded_cc_plan_path_fails(self):
        """Fully expanded CC plan path should raise ValueError."""
        # Simulate expanded path in user's home directory
        home = str(Path.home())
        cc_plan_path = os.path.join(home, ".claude", "plans", "some-plan.md")

        with pytest.raises(ValueError) as exc_info:
            validate_plan_ca_ref(cc_plan_path)

        # Verify error message
        assert "CC native plans" in str(exc_info.value)

    def test_substring_match_fails(self):
        """Path containing /.claude/plans/ substring should fail."""
        # Nested path that contains the pattern
        nested_path = "/some/path/.claude/plans/nested.md"

        with pytest.raises(ValueError) as exc_info:
            validate_plan_ca_ref(nested_path)

        assert "CC native plans" in str(exc_info.value)

    def test_similar_but_different_path_passes(self):
        """Similar paths that are not CC plans should pass."""
        similar_paths = [
            "~/.claude/commands/foo.md",  # commands, not plans
            "~/.claude/skills/bar.md",    # skills, not plans
            "agent/private/plans/my-plan.md",  # different location
        ]

        for path in similar_paths:
            # Should not raise
            validate_plan_ca_ref(path)
