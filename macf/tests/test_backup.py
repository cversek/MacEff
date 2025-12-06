"""
Tests for the MACF backup module.

Pragmatic TDD: 4-6 focused tests per feature, testing core functionality
and likely failure modes.
"""

import json
import tempfile
from pathlib import Path

import pytest

from macf.backup.paths import BackupPaths, BackupSource, collect_backup_sources
from macf.backup.manifest import compute_sha256, create_manifest, verify_manifest
from macf.backup.archive import create_archive, extract_archive, get_archive_manifest
from macf.backup.transplant import TransplantMapping, create_transplant_mapping, run_transplant
from macf.backup.integrity import (
    detect_existing_consciousness,
    has_existing_consciousness,
    create_recovery_checkpoint,
    cleanup_old_backups,
)


class TestBackupPaths:
    """Test path resolution for backups."""

    def test_backup_paths_from_project_root(self, tmp_path):
        """BackupPaths correctly derives paths from project root."""
        paths = BackupPaths(project_root=tmp_path, home_dir=Path.home())

        assert paths.maceff_dir == tmp_path / ".maceff"
        assert paths.agent_dir == tmp_path / "agent"
        assert paths.claude_config == tmp_path / ".claude"

    def test_backup_source_exists_check(self, tmp_path):
        """BackupSource.exists() returns correct value."""
        existing = tmp_path / "existing.txt"
        existing.write_text("test")

        source_exists = BackupSource(
            source_path=existing,
            archive_path="existing.txt",
            category="test",
        )
        source_missing = BackupSource(
            source_path=tmp_path / "missing.txt",
            archive_path="missing.txt",
            category="test",
        )

        assert source_exists.exists() is True
        assert source_missing.exists() is False

    def test_collect_backup_sources_includes_agent_tree(self, tmp_path):
        """collect_backup_sources includes entire agent/ tree."""
        # Setup minimal project structure
        (tmp_path / "agent" / "private" / "checkpoints").mkdir(parents=True)
        (tmp_path / "agent" / "private" / "checkpoints" / "test.md").write_text("checkpoint")

        paths = BackupPaths(project_root=tmp_path, home_dir=Path.home())
        sources = collect_backup_sources(paths, include_transcripts=False)

        # Should have agent/ as a source (category is "consciousness_artifacts")
        agent_sources = [s for s in sources if "agent" in str(s.source_path)]
        assert len(agent_sources) >= 1


class TestManifest:
    """Test manifest generation and verification."""

    def test_compute_sha256_produces_valid_hash(self, tmp_path):
        """SHA256 hash has correct format and is deterministic."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        hash1 = compute_sha256(test_file)
        hash2 = compute_sha256(test_file)

        assert len(hash1) == 64  # SHA256 hex string length
        assert hash1 == hash2  # Deterministic

    def test_create_manifest_includes_metadata(self, tmp_path):
        """Manifest includes required metadata fields."""
        paths = BackupPaths(project_root=tmp_path, home_dir=Path.home())
        sources = []

        manifest = create_manifest(sources, paths, include_checksums=False)

        assert "source_paths" in manifest
        assert "project_root" in manifest["source_paths"]
        assert "created_at" in manifest
        assert "totals" in manifest

    def test_verify_manifest_detects_missing_files(self, tmp_path):
        """verify_manifest correctly identifies missing files."""
        manifest = {
            "files": [
                {"archive_path": "missing.txt", "checksum": "abc123", "size_bytes": 100},
            ]
        }

        result = verify_manifest(manifest, tmp_path)

        assert result["valid"] is False
        assert "missing.txt" in result["missing"]


class TestArchive:
    """Test archive creation and extraction."""

    def test_create_and_extract_archive_roundtrip(self, tmp_path):
        """Archive roundtrip preserves file contents."""
        # Setup source
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "test.txt").write_text("test content")

        # Create paths and sources
        paths = BackupPaths(project_root=source_dir, home_dir=Path.home())
        sources = [
            BackupSource(
                source_path=source_dir / "test.txt",
                archive_path="test.txt",
                category="test",
            )
        ]

        # Create archive
        archive_path = tmp_path / "test.tar.xz"
        create_archive(sources, paths, output_path=archive_path)

        assert archive_path.exists()

        # Extract and verify
        extract_dir = tmp_path / "extracted"
        extract_archive(archive_path, extract_dir)

        assert (extract_dir / "test.txt").read_text() == "test content"

    def test_get_archive_manifest_extracts_manifest(self, tmp_path):
        """get_archive_manifest retrieves manifest without full extraction."""
        # Setup and create archive with manifest
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        paths = BackupPaths(project_root=source_dir, home_dir=Path.home())
        sources = []

        archive_path = tmp_path / "test.tar.xz"
        create_archive(sources, paths, output_path=archive_path)

        # Extract manifest only
        manifest = get_archive_manifest(archive_path)

        assert manifest is not None
        assert "source_paths" in manifest


class TestTransplant:
    """Test path rewriting for cross-system restore."""

    def test_transplant_mapping_rewrites_paths(self):
        """TransplantMapping correctly rewrites source to target paths."""
        mapping = TransplantMapping(
            source_project_root=Path("/old/project"),
            source_maceff_root=Path("/old/MacEff"),
            source_home=Path("/old/home"),
            source_transcripts_dir=Path("/old/home/.claude/projects/old-project"),
            target_project_root=Path("/new/project"),
            target_maceff_root=Path("/new/MacEff"),
            target_home=Path("/new/home"),
        )

        result = mapping.rewrite_path("/old/project/agent/test.md")

        assert result == "/new/project/agent/test.md"

    def test_transplant_mapping_handles_multiple_paths_in_text(self):
        """rewrite_paths_in_text handles multiple paths."""
        mapping = TransplantMapping(
            source_project_root=Path("/old/project"),
            source_maceff_root=Path("/old/MacEff"),
            source_home=Path("/old/home"),
            source_transcripts_dir=Path("/old/home/.claude/projects/old-project"),
            target_project_root=Path("/new/project"),
            target_maceff_root=Path("/new/MacEff"),
            target_home=Path("/new/home"),
        )

        text = "Path1: /old/project/a, Path2: /old/MacEff/b"
        result = mapping.rewrite_paths_in_text(text)

        assert "/new/project/a" in result
        assert "/new/MacEff/b" in result


class TestIntegrity:
    """Test integrity and safety features."""

    def test_detect_existing_consciousness_finds_artifacts(self, tmp_path):
        """detect_existing_consciousness identifies consciousness indicators."""
        # Create some consciousness indicators
        (tmp_path / ".maceff").mkdir()
        (tmp_path / ".maceff" / "agent_state.json").write_text("{}")
        (tmp_path / "agent").mkdir()

        checks = detect_existing_consciousness(tmp_path)

        assert checks["maceff_state"] is True
        assert checks["agent_artifacts"] is True
        assert checks["claude_config"] is False

    def test_has_existing_consciousness_returns_true_when_present(self, tmp_path):
        """has_existing_consciousness returns True if any indicator found."""
        (tmp_path / "agent").mkdir()

        assert has_existing_consciousness(tmp_path) is True
        assert has_existing_consciousness(tmp_path / "empty") is False

    def test_create_recovery_checkpoint_backs_up_consciousness(self, tmp_path):
        """create_recovery_checkpoint creates backup of existing state."""
        # Setup existing consciousness
        (tmp_path / ".maceff").mkdir()
        (tmp_path / ".maceff" / "agent_state.json").write_text('{"cycle": 42}')
        (tmp_path / "agent").mkdir()
        (tmp_path / "agent" / "test.md").write_text("test")

        checkpoint = create_recovery_checkpoint(tmp_path)

        assert checkpoint is not None
        assert (checkpoint / ".maceff" / "agent_state.json").exists()
        assert (checkpoint / "agent" / "test.md").exists()

    def test_cleanup_old_backups_keeps_recent(self, tmp_path):
        """cleanup_old_backups retains specified number of recent backups."""
        # Create mock backup files
        for i in range(7):
            backup = tmp_path / f"backup_{i}_consciousness.tar.xz"
            backup.write_text(f"backup {i}")
            # Touch with different mtimes
            import time
            time.sleep(0.01)

        deleted = cleanup_old_backups(tmp_path, keep_count=3, dry_run=True)

        assert len(deleted) == 4  # 7 - 3 = 4 to delete
