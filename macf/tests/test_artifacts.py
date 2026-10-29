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
    # A roadmap is a folder holding roadmap.md (roadmaps_drafting), never a
    # loose file: this test once built a loose rdm1.md, which is how discovery
    # could miss every real roadmap while its own test passed.
    (roadmaps_dir / "2026-01-01_Some_Mission").mkdir()
    (roadmaps_dir / "2026-01-01_Some_Mission" / "roadmap.md").write_text("Roadmap 1")

    # Discover artifacts
    artifacts = get_latest_consciousness_artifacts(agent_root=agent_root, limit=5)

    assert len(artifacts.reflections) == 1
    assert len(artifacts.checkpoints) == 1
    assert len(artifacts.roadmaps) == 1
    assert artifacts.latest_reflection is not None
    assert artifacts.latest_checkpoint is not None
    assert artifacts.latest_roadmap is not None


def _agent_root(tmp_path):
    root = tmp_path / "agent"
    for d in ("private/reflections", "private/checkpoints", "public/roadmaps"):
        (root / d).mkdir(parents=True)
    return root


def test_roadmap_folder_is_discovered_as_its_roadmap_md(tmp_path):
    """A roadmap on disk is found, and the path given is the readable roadmap.md."""
    root = _agent_root(tmp_path)
    folder = root / "public" / "roadmaps" / "2026-10-02_A_Mission"
    folder.mkdir()
    (folder / "roadmap.md").write_text("# Roadmap")
    (folder / "research").mkdir()
    (folder / "research" / "notes.md").write_text("not the roadmap")

    artifacts = get_latest_consciousness_artifacts(agent_root=root)

    assert artifacts.latest_roadmap == folder / "roadmap.md"
    assert artifacts.roadmaps == [folder / "roadmap.md"]


def test_latest_roadmap_is_the_newest_by_its_date(tmp_path):
    import os
    root = _agent_root(tmp_path)
    paths = []
    for i, name in enumerate(["2026-09-01_Old", "2026-10-01_New"]):
        f = root / "public" / "roadmaps" / name
        f.mkdir()
        (f / "roadmap.md").write_text(name)
        os.utime(f / "roadmap.md", (1_000_000 + i, 1_000_000 + i))
        paths.append(f / "roadmap.md")

    assert get_latest_consciousness_artifacts(agent_root=root).latest_roadmap == paths[1]


def test_a_failed_discovery_says_it_failed(tmp_path, monkeypatch):
    """An exception is not an empty tree: the result carries the error."""
    root = _agent_root(tmp_path)
    (root / "private" / "checkpoints" / "c.md").write_text("checkpoint")

    def boom(self, pattern):
        raise PermissionError("denied")
    monkeypatch.setattr(Path, "glob", boom)

    artifacts = get_latest_consciousness_artifacts(agent_root=root)

    assert not artifacts
    assert artifacts.error and "PermissionError" in artifacts.error


def test_an_empty_tree_is_not_an_error(tmp_path):
    assert get_latest_consciousness_artifacts(agent_root=_agent_root(tmp_path)).error is None


def test_recovery_text_never_claims_absence_after_a_failed_search():
    from macf.hooks.recovery import _format_artifacts_section

    text = _format_artifacts_section(ConsciousnessArtifacts(error="PermissionError: denied"))

    assert "No roadmap found" not in text and "No checkpoint found" not in text
    assert "discovery failed" in text.lower()
    assert "PermissionError: denied" in text


def test_recovery_text_still_reports_a_real_absence():
    from macf.hooks.recovery import _format_artifacts_section

    text = _format_artifacts_section(ConsciousnessArtifacts())

    assert "No roadmap found" in text


def test_an_older_loose_roadmap_still_counts_below_a_folder_one(tmp_path):
    """Roadmaps are folders now (roadmaps_drafting), but agents that predate the
    folder form keep loose files. They still count, and rank by their dates."""
    import os
    root = _agent_root(tmp_path)
    loose = root / "public/roadmaps/2025-12-10_Old_DRAFT_ROADMAP.md"
    loose.write_text("old")
    os.utime(loose, (2_000_000, 2_000_000))  # edited after the current one
    folder = root / "public/roadmaps/2026-08-28_Current"
    folder.mkdir()
    (folder / "roadmap.md").write_text("current")
    (folder / "notes.md").write_text("a working note, not the roadmap")
    os.utime(folder / "roadmap.md", (1_000_000, 1_000_000))

    artifacts = get_latest_consciousness_artifacts(agent_root=root, limit=5)

    assert artifacts.latest_roadmap == folder / "roadmap.md"
    assert loose in artifacts.roadmaps
    assert folder / "notes.md" not in artifacts.roadmaps


def test_a_tool_file_in_an_artifact_directory_is_not_an_artifact(tmp_path):
    """A memory tool can write CLAUDE.md into any directory; touched last, it
    would be named as the checkpoint or reflection to read first."""
    import os
    root = _agent_root(tmp_path)
    for kind in ("checkpoints", "reflections"):
        real = root / f"private/{kind}/2026-10-03_real.md"
        real.write_text("real")
        os.utime(real, (1_000_000, 1_000_000))
        (root / f"private/{kind}/CLAUDE.md").write_text("tool context")

    artifacts = get_latest_consciousness_artifacts(agent_root=root, limit=5)

    assert artifacts.latest_checkpoint.name == "2026-10-03_real.md"
    assert artifacts.latest_reflection.name == "2026-10-03_real.md"
    assert not [p for p in artifacts.all_paths() if p.name == "CLAUDE.md"]


def test_latest_follows_the_date_in_the_name_not_the_last_edit(tmp_path):
    """A curation pass that edits old artifacts in place (knowledge link adds
    wiki-links) moves their mtimes past the newest one. The date and time an
    artifact is named for do not move."""
    import os
    root = _agent_root(tmp_path)
    ckp = root / "private/checkpoints"
    newest = ckp / "2026-10-03_123758_Closing_CCP.md"
    morning = ckp / "2026-10-03_090000_Morning_CCP.md"
    old = ckp / "2026-04-13_090000_Old_CCP.md"
    for i, f in enumerate((newest, morning, old)):
        f.write_text(f.name)
        os.utime(f, (1_000_000 + i, 1_000_000 + i))  # the oldest name has the newest mtime
    current = root / "public/roadmaps/2026-08-28_Current"
    stale = root / "public/roadmaps/2026-04-13_Stale"
    for i, d in enumerate((current, stale)):
        d.mkdir()
        (d / "roadmap.md").write_text(d.name)
        os.utime(d / "roadmap.md", (1_000_000 + i, 1_000_000 + i))

    artifacts = get_latest_consciousness_artifacts(agent_root=root, limit=5)

    assert artifacts.latest_checkpoint == newest
    assert artifacts.checkpoints == [newest, morning, old]
    assert artifacts.latest_roadmap == current / "roadmap.md"


def test_a_missing_agent_directory_is_a_failed_search(tmp_path):
    """A root that does not exist cannot say the predecessor left nothing."""
    artifacts = get_latest_consciousness_artifacts(agent_root=tmp_path / "nowhere")

    assert not artifacts
    assert artifacts.error and "nowhere" in artifacts.error


def test_a_directory_without_public_or_private_is_a_failed_search(tmp_path):
    """Pointed at the repository root instead of agent/, discovery finds neither
    subtree; that is a wrong root, not an agent with no artifacts."""
    (tmp_path / "agent" / "private" / "checkpoints").mkdir(parents=True)
    (tmp_path / "agent" / "private" / "checkpoints" / "2026-10-03_c.md").write_text("checkpoint")

    artifacts = get_latest_consciousness_artifacts(agent_root=tmp_path)

    assert not artifacts
    assert artifacts.error and "public" in artifacts.error and "private" in artifacts.error
