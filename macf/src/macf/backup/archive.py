"""
Archive creation and extraction for consciousness backups.
"""

import tarfile
import tempfile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from .paths import BackupSource, BackupPaths
from .manifest import create_manifest, save_manifest, load_manifest


def create_archive(
    sources: List[BackupSource],
    paths: BackupPaths,
    output_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Path:
    """
    Create tar.xz archive of consciousness state.

    Args:
        sources: List of backup sources to include
        paths: Backup path configuration
        output_path: Override output path (default: paths.get_archive_path())
        progress_callback: Optional callback(filename, current, total) for progress

    Returns:
        Path to created archive
    """
    if output_path is None:
        output_path = paths.get_archive_path()

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create manifest
    manifest = create_manifest(sources, paths, include_checksums=True)

    # Count total files for progress
    total_files = manifest["totals"]["file_count"] + 1  # +1 for manifest
    current_file = 0

    with tarfile.open(output_path, "w:xz") as tar:
        # Add each source
        for source in sources:
            if not source.exists():
                continue

            if source.source_path.is_file():
                current_file += 1
                if progress_callback:
                    progress_callback(source.archive_path, current_file, total_files)
                tar.add(source.source_path, arcname=source.archive_path)
            else:
                # Directory: add all files
                for file_path in source.source_path.rglob("*"):
                    if file_path.is_file():
                        rel_path = file_path.relative_to(source.source_path)
                        archive_path = f"{source.archive_path}/{rel_path}"
                        current_file += 1
                        if progress_callback:
                            progress_callback(archive_path, current_file, total_files)
                        tar.add(file_path, arcname=archive_path)

        # Add manifest as last entry
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            import json
            json.dump(manifest, f, indent=2)
            manifest_temp = Path(f.name)

        current_file += 1
        if progress_callback:
            progress_callback("manifest.json", current_file, total_files)
        tar.add(manifest_temp, arcname="manifest.json")
        manifest_temp.unlink()

    return output_path


def extract_archive(
    archive_path: Path,
    output_dir: Path,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Dict[str, Any]:
    """
    Extract archive to output directory.

    Uses pipeline extraction (xz -d | tar -xf) for cross-platform compatibility.
    Python's tarfile module has issues with BSD-created xz archives on Linux.

    Args:
        archive_path: Path to tar.xz archive
        output_dir: Directory to extract to
        progress_callback: Optional callback(filename, current, total) for progress

    Returns:
        Manifest from archive
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use pipeline extraction for cross-platform compatibility
    # Python's tarfile.open("r:xz") fails on Linux with BSD-created archives
    try:
        result = subprocess.run(
            f'xz -d < "{archive_path}" | tar -xf - -C "{output_dir}"',
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Pipeline extraction failed: {result.stderr}")

        if progress_callback:
            progress_callback("extraction complete", 1, 1)

    except FileNotFoundError:
        # Fallback to Python tarfile if xz/tar not available
        print("Warning: xz/tar not found, using Python tarfile (may fail cross-platform)",
              file=sys.stderr)
        with tarfile.open(archive_path, "r:xz") as tar:
            members = tar.getmembers()
            total = len(members)
            for i, member in enumerate(members):
                if progress_callback:
                    progress_callback(member.name, i + 1, total)
                tar.extract(member, output_dir)

    # Load and return manifest
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        return load_manifest(manifest_path)
    return {}


def list_archive(archive_path: Path) -> List[Dict[str, Any]]:
    """
    List contents of archive without extracting.

    Returns:
        List of file info dicts with name, size, mtime
    """
    contents = []
    with tarfile.open(archive_path, "r:xz") as tar:
        for member in tar.getmembers():
            contents.append({
                "name": member.name,
                "size": member.size,
                "is_dir": member.isdir(),
            })
    return contents


def get_archive_manifest(archive_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract and return manifest from archive without full extraction.
    """
    with tarfile.open(archive_path, "r:xz") as tar:
        try:
            manifest_member = tar.getmember("manifest.json")
            f = tar.extractfile(manifest_member)
            if f:
                import json
                return json.load(f)
        except KeyError:
            return None
    return None
