"""
Tests for manifest merging infrastructure (B.6 Phase 1.2).

Tests the 2-layer manifest merging: Framework base + Project overlay.
Validates merge strategy: lists append, scalars override, nested dicts recurse.
"""

import json
import tempfile
from pathlib import Path
import pytest

from macf.utils import load_merged_manifest, _deep_merge


class TestDeepMerge:
    """Test the _deep_merge helper function."""

    def test_scalar_override(self):
        """Scalars: Project overrides base."""
        base = {"version": "1.0.0", "active": False}
        overlay = {"active": True}

        result = _deep_merge(base, overlay)

        assert result["version"] == "1.0.0"  # Base preserved
        assert result["active"] is True  # Overlay overrides

    def test_list_append(self):
        """Lists: Append overlay items to base."""
        base = {"custom_policies": ["policy1.md", "policy2.md"]}
        overlay = {"custom_policies": ["policy3.md"]}

        result = _deep_merge(base, overlay)

        assert result["custom_policies"] == ["policy1.md", "policy2.md", "policy3.md"]

    def test_nested_dict_recurse(self):
        """Nested dicts: Recursive merge, not clobber."""
        base = {
            "consciousness_patterns": {
                "triggers": ["pattern1"],
                "metadata": {"version": "1.0"}
            }
        }
        overlay = {
            "consciousness_patterns": {
                "triggers": ["pattern2"],
                "metadata": {"author": "ClaudeTheBuilder"}
            }
        }

        result = _deep_merge(base, overlay)

        # Lists append
        assert result["consciousness_patterns"]["triggers"] == ["pattern1", "pattern2"]
        # Nested dicts merge
        assert result["consciousness_patterns"]["metadata"]["version"] == "1.0"
        assert result["consciousness_patterns"]["metadata"]["author"] == "ClaudeTheBuilder"

    def test_new_keys_from_overlay(self):
        """New keys from overlay are added."""
        base = {"existing": "value"}
        overlay = {"new_key": "new_value"}

        result = _deep_merge(base, overlay)

        assert result["existing"] == "value"
        assert result["new_key"] == "new_value"


class TestLoadMergedManifest:
    """Test the load_merged_manifest function with various scenarios."""

    def test_base_only_no_project_manifest(self, tmp_path, monkeypatch):
        """When no project manifest exists, should return framework base only."""
        # Create mock framework base manifest
        framework_dir = tmp_path / "framework" / "policies"
        framework_dir.mkdir(parents=True)

        base_manifest = {
            "version": "1.0.0",
            "mandatory_policies": {
                "description": "Foundation policies",
                "policies": ["policy1", "policy2"]
            },
            "discovery_index": {
                "compaction": ["context_management#compaction"]
            }
        }

        manifest_path = framework_dir / "manifest.json"
        manifest_path.write_text(json.dumps(base_manifest))

        # Mock find_project_root to return tmp_path
        monkeypatch.setattr("macf.utils.find_project_root", lambda: tmp_path)

        # No .maceff directory = no project manifest
        result = load_merged_manifest(agent_root=tmp_path)

        # Should return base manifest only
        assert result["version"] == "1.0.0"
        assert result["mandatory_policies"]["description"] == "Foundation policies"
        assert len(result["mandatory_policies"]["policies"]) == 2

    def test_project_extends_base(self, tmp_path, monkeypatch):
        """Project manifest should extend base with custom configuration."""
        # Create framework base
        framework_dir = tmp_path / "framework" / "policies"
        framework_dir.mkdir(parents=True)

        base_manifest = {
            "version": "1.0.0",
            "mandatory_policies": {
                "policies": ["base_policy.md"]
            }
        }

        (framework_dir / "manifest.json").write_text(json.dumps(base_manifest))

        # Create project overlay
        project_dir = tmp_path / ".maceff" / "policies"
        project_dir.mkdir(parents=True)

        project_overlay = {
            "active_layers": ["core", "consciousness"],
            "active_consciousness": ["checkpoints", "reflections"]
        }

        (project_dir / "manifest.json").write_text(json.dumps(project_overlay))

        # Mock find_project_root
        monkeypatch.setattr("macf.utils.find_project_root", lambda: tmp_path)

        result = load_merged_manifest(agent_root=tmp_path)

        # Should have base structure
        assert result["version"] == "1.0.0"
        assert "base_policy.md" in result["mandatory_policies"]["policies"]

        # Should have project config
        assert result["active_layers"] == ["core", "consciousness"]
        assert result["active_consciousness"] == ["checkpoints", "reflections"]

    def test_custom_policies_list_appends(self, tmp_path, monkeypatch):
        """Project custom_policies should append to base list, not replace."""
        # Framework base with some custom policies
        framework_dir = tmp_path / "framework" / "policies"
        framework_dir.mkdir(parents=True)

        base_manifest = {
            "custom_policies": ["framework_policy1.md", "framework_policy2.md"]
        }

        (framework_dir / "manifest.json").write_text(json.dumps(base_manifest))

        # Project overlay with additional custom policies
        project_dir = tmp_path / ".maceff" / "policies"
        project_dir.mkdir(parents=True)

        project_overlay = {
            "custom_policies": ["project_policy.md"]
        }

        (project_dir / "manifest.json").write_text(json.dumps(project_overlay))

        monkeypatch.setattr("macf.utils.find_project_root", lambda: tmp_path)

        result = load_merged_manifest(agent_root=tmp_path)

        # Lists should append
        assert len(result["custom_policies"]) == 3
        assert "framework_policy1.md" in result["custom_policies"]
        assert "framework_policy2.md" in result["custom_policies"]
        assert "project_policy.md" in result["custom_policies"]

    def test_deep_merge_nested_dicts(self, tmp_path, monkeypatch):
        """Nested dict structures should merge recursively, not clobber."""
        # Framework base with nested structure
        framework_dir = tmp_path / "framework" / "policies"
        framework_dir.mkdir(parents=True)

        base_manifest = {
            "consciousness_patterns": {
                "triggers": ["trigger1", "trigger2"],
                "metadata": {
                    "version": "1.0",
                    "base_setting": True
                }
            }
        }

        (framework_dir / "manifest.json").write_text(json.dumps(base_manifest))

        # Project overlay extending nested structure
        project_dir = tmp_path / ".maceff" / "policies"
        project_dir.mkdir(parents=True)

        project_overlay = {
            "consciousness_patterns": {
                "triggers": ["trigger3"],
                "metadata": {
                    "project_name": "ClaudeTheBuilder"
                }
            }
        }

        (project_dir / "manifest.json").write_text(json.dumps(project_overlay))

        monkeypatch.setattr("macf.utils.find_project_root", lambda: tmp_path)

        result = load_merged_manifest(agent_root=tmp_path)

        # Triggers list should append
        triggers = result["consciousness_patterns"]["triggers"]
        assert len(triggers) == 3
        assert "trigger1" in triggers
        assert "trigger3" in triggers

        # Nested metadata should merge (not clobber)
        metadata = result["consciousness_patterns"]["metadata"]
        assert metadata["version"] == "1.0"
        assert metadata["base_setting"] is True
        assert metadata["project_name"] == "ClaudeTheBuilder"

    def test_missing_project_manifest_graceful(self, tmp_path, monkeypatch):
        """Missing project manifest should fall back to base without crashing."""
        # Create framework base
        framework_dir = tmp_path / "framework" / "policies"
        framework_dir.mkdir(parents=True)

        base_manifest = {
            "version": "1.0.0",
            "base_key": "base_value"
        }

        (framework_dir / "manifest.json").write_text(json.dumps(base_manifest))

        monkeypatch.setattr("macf.utils.find_project_root", lambda: tmp_path)

        # .maceff directory doesn't exist at all
        result = load_merged_manifest(agent_root=tmp_path)

        # Should return base manifest
        assert result["version"] == "1.0.0"
        assert result["base_key"] == "base_value"

    def test_malformed_project_manifest_graceful(self, tmp_path, monkeypatch):
        """Invalid JSON in project manifest should fall back to base."""
        # Create framework base
        framework_dir = tmp_path / "framework" / "policies"
        framework_dir.mkdir(parents=True)

        base_manifest = {
            "version": "1.0.0",
            "safe_key": "safe_value"
        }

        (framework_dir / "manifest.json").write_text(json.dumps(base_manifest))

        # Create malformed project manifest
        project_dir = tmp_path / ".maceff" / "policies"
        project_dir.mkdir(parents=True)

        # Write invalid JSON
        (project_dir / "manifest.json").write_text("{ invalid json }")

        monkeypatch.setattr("macf.utils.find_project_root", lambda: tmp_path)

        result = load_merged_manifest(agent_root=tmp_path)

        # Should return base manifest (graceful fallback)
        assert result["version"] == "1.0.0"
        assert result["safe_key"] == "safe_value"

    def test_explicit_agent_root_parameter(self, tmp_path):
        """Explicit agent_root parameter should override auto-detection."""
        # Create framework base at specific path
        framework_dir = tmp_path / "framework" / "policies"
        framework_dir.mkdir(parents=True)

        base_manifest = {"explicit_test": True}
        (framework_dir / "manifest.json").write_text(json.dumps(base_manifest))

        # Call with explicit agent_root (no monkeypatch needed)
        result = load_merged_manifest(agent_root=tmp_path)

        assert result["explicit_test"] is True
