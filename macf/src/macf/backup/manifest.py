"""
Manifest generation and verification for backup archives.
"""

import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from .paths import BackupSource, BackupPaths


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def create_manifest(
    sources: List[BackupSource],
    paths: BackupPaths,
    include_checksums: bool = True
) -> Dict[str, Any]:
    """
    Create manifest describing backup contents.

    Args:
        sources: List of backup sources
        paths: Backup path configuration
        include_checksums: Compute SHA256 for each file

    Returns:
        Manifest dictionary
    """
    manifest = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "project_name": paths.project_name,
        "source_paths": {
            "project_root": str(paths.project_root),
            "home_dir": str(paths.home_dir),
            "transcripts_dir": str(paths.transcripts_dir),
        },
        "categories": {},
        "files": [],
        "totals": {
            "file_count": 0,
            "total_bytes": 0,
            "critical_bytes": 0,
        }
    }

    for source in sources:
        if not source.exists():
            continue

        category = source.category
        if category not in manifest["categories"]:
            manifest["categories"][category] = {
                "critical": source.critical,
                "file_count": 0,
                "total_bytes": 0,
            }

        if source.source_path.is_file():
            _add_file_to_manifest(
                manifest, source, source.source_path,
                source.archive_path, include_checksums
            )
        else:
            # Directory: walk all files
            for file_path in source.source_path.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(source.source_path)
                    archive_path = f"{source.archive_path}/{rel_path}"
                    _add_file_to_manifest(
                        manifest, source, file_path,
                        archive_path, include_checksums
                    )

    return manifest


def _add_file_to_manifest(
    manifest: Dict[str, Any],
    source: BackupSource,
    file_path: Path,
    archive_path: str,
    include_checksums: bool
) -> None:
    """Add a single file to the manifest."""
    size = file_path.stat().st_size
    mtime = file_path.stat().st_mtime

    file_entry = {
        "archive_path": archive_path,
        "source_path": str(file_path),
        "size_bytes": size,
        "modified_at": datetime.fromtimestamp(mtime).isoformat(),
        "category": source.category,
        "critical": source.critical,
    }

    if include_checksums:
        file_entry["sha256"] = compute_sha256(file_path)

    manifest["files"].append(file_entry)
    manifest["categories"][source.category]["file_count"] += 1
    manifest["categories"][source.category]["total_bytes"] += size
    manifest["totals"]["file_count"] += 1
    manifest["totals"]["total_bytes"] += size
    if source.critical:
        manifest["totals"]["critical_bytes"] += size


def verify_manifest(
    manifest: Dict[str, Any],
    extract_dir: Path
) -> Dict[str, Any]:
    """
    Verify extracted files against manifest.

    Args:
        manifest: Manifest dictionary
        extract_dir: Directory where archive was extracted

    Returns:
        Verification result with any mismatches
    """
    result = {
        "valid": True,
        "checked": 0,
        "missing": [],
        "corrupted": [],
        "size_mismatch": [],
        "broken_symlinks": [],  # Symlinks that exist but point to non-existent targets
    }

    for file_entry in manifest.get("files", []):
        archive_path = file_entry["archive_path"]
        expected_size = file_entry["size_bytes"]
        expected_sha256 = file_entry.get("sha256")

        file_path = extract_dir / archive_path
        result["checked"] += 1

        # Check for broken symlinks separately
        if file_path.is_symlink():
            if not file_path.exists():  # Symlink target doesn't exist
                result["broken_symlinks"].append({
                    "path": archive_path,
                    "target": str(file_path.readlink()),
                })
            # Skip size/checksum validation for symlinks
            continue

        if not file_path.exists():
            result["missing"].append(archive_path)
            result["valid"] = False
            continue

        actual_size = file_path.stat().st_size
        if actual_size != expected_size:
            result["size_mismatch"].append({
                "path": archive_path,
                "expected": expected_size,
                "actual": actual_size,
            })
            result["valid"] = False

        if expected_sha256:
            actual_sha256 = compute_sha256(file_path)
            if actual_sha256 != expected_sha256:
                result["corrupted"].append({
                    "path": archive_path,
                    "expected": expected_sha256,
                    "actual": actual_sha256,
                })
                result["valid"] = False

    return result


def save_manifest(manifest: Dict[str, Any], path: Path) -> None:
    """Save manifest to JSON file."""
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)


def load_manifest(path: Path) -> Dict[str, Any]:
    """Load manifest from JSON file."""
    with open(path, "r") as f:
        return json.load(f)
