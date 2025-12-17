#!/usr/bin/env python3
"""Tests for ConsciousnessArtifacts discovery."""

from pathlib import Path

import pytest

from macf.utils import ConsciousnessArtifacts, get_latest_consciousness_artifacts


def test_empty_artifacts_return_properly():
    """Empty artifacts return properly (no crash)."""
    artifacts = ConsciousnessArtifacts()

    assert artifacts.latest_checkpoint is None
    assert artifacts.latest_reflection is None
    assert artifacts.latest_roadmap is None
    assert len(artifacts.all_paths()) == 0
    assert not artifacts  # __bool__ returns False


def test_properties_work_with_data(tmp_path):
    """Properties work correctly with data."""
    # Create test files
    reflections_dir = tmp_path / "reflections"
    checkpoints_dir = tmp_path / "checkpoints"
    roadmaps_dir = tmp_path / "roadmaps"

    reflections_dir.mkdir()
    checkpoints_dir.mkdir()
    roadmaps_dir.mkdir()

    # Create files with different timestamps
    ref1 = reflections_dir / "reflection1.md"
    ref2 = reflections_dir / "reflection2.md"
    ckp1 = checkpoints_dir / "checkpoint1.md"
    rdm1 = roadmaps_dir / "roadmap1.md"

    ref1.write_text("Reflection 1")
    ref2.write_text("Reflection 2")  # Newer by mtime
    ckp1.write_text("Checkpoint 1")
    rdm1.write_text("Roadmap 1")

    artifacts = ConsciousnessArtifacts(
        reflections=[ref1, ref2],
        checkpoints=[ckp1],
        roadmaps=[rdm1]
    )

    # Latest should be ref2 (most recent mtime)
    assert artifacts.latest_reflection in [ref1, ref2]
    assert artifacts.latest_checkpoint == ckp1
    assert artifacts.latest_roadmap == rdm1


def test_all_paths_flattens_lists(tmp_path):
    """all_paths() flattens all artifacts into single list."""
    ref = tmp_path / "reflection.md"
    ckp = tmp_path / "checkpoint.md"
    rdm = tmp_path / "roadmap.md"

    ref.write_text("R")
    ckp.write_text("C")
    rdm.write_text("R")

    artifacts = ConsciousnessArtifacts(
        reflections=[ref],
        checkpoints=[ckp],
        roadmaps=[rdm]
    )

    all_paths = artifacts.all_paths()
    assert len(all_paths) == 3
    assert ref in all_paths
    assert ckp in all_paths
    assert rdm in all_paths


def test_bool_returns_false_for_empty_true_for_nonempty(tmp_path):
    """__bool__() returns False for empty, True for non-empty."""
    # Empty artifacts
    empty = ConsciousnessArtifacts()
    assert not empty

    # Non-empty artifacts
    ref = tmp_path / "reflection.md"
    ref.write_text("R")

    nonempty = ConsciousnessArtifacts(reflections=[ref])
    assert nonempty


def test_artifact_discovery_with_real_files(tmp_path):
    """Artifact discovery with real files."""
    # Create agent directory structure
    # agent_root IS the agent directory (ConsciousnessConfig.agent_root pattern)
    agent_root = tmp_path / "agent_root"
    private_dir = agent_root / "private"
    public_dir = agent_root / "public"
    # Reflections and checkpoints are private, roadmaps are public
    reflections_dir = private_dir / "reflections"
    checkpoints_dir = private_dir / "checkpoints"
    roadmaps_dir = public_dir / "roadmaps"

    reflections_dir.mkdir(parents=True)
    checkpoints_dir.mkdir(parents=True)
    roadmaps_dir.mkdir(parents=True)

    # Create test files
    (reflections_dir / "ref1.md").write_text("Reflection 1")
    (checkpoints_dir / "ckp1.md").write_text("Checkpoint 1")
    (roadmaps_dir / "rdm1.md").write_text("Roadmap 1")

    # Discover artifacts
    artifacts = get_latest_consciousness_artifacts(agent_root=agent_root, limit=5)

    assert len(artifacts.reflections) == 1
    assert len(artifacts.checkpoints) == 1
    assert len(artifacts.roadmaps) == 1
    assert artifacts.latest_reflection is not None
    assert artifacts.latest_checkpoint is not None
    assert artifacts.latest_roadmap is not None
