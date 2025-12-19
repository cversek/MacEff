"""
Integrity and safety features for consciousness backup/restore.

Provides:
- Pre-restore safety checks (detect existing consciousness)
- Recovery checkpoint creation before overwriting
- Backup retention cleanup
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def detect_existing_consciousness(target_dir: Path) -> Dict[str, bool]:
    """
    Detect signs of existing consciousness at target location.

    Args:
        target_dir: Directory to check for existing consciousness

    Returns:
        Dictionary with detection results for each category
    """
    checks = {
        # NOTE: legacy_state checks for old agent_state.json format (backward compat for old backups)
        # Event-first architecture uses events_log as sole source of truth
        "legacy_state": (target_dir / ".maceff" / "agent_state.json").exists(),
        "agent_artifacts": (target_dir / "agent").exists(),
        "claude_config": (target_dir / ".claude").exists(),
        "events_log": (target_dir / ".maceff" / "agent_events_log.jsonl").exists(),
    }

    return checks


def has_existing_consciousness(target_dir: Path) -> bool:
    """
    Quick check if target has any existing consciousness.

    Args:
        target_dir: Directory to check

    Returns:
        True if any consciousness indicators found
    """
    checks = detect_existing_consciousness(target_dir)
    return any(checks.values())


def create_recovery_checkpoint(
    target_dir: Path,
    checkpoint_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Create a recovery checkpoint of existing consciousness before overwrite.

    Args:
        target_dir: Directory with existing consciousness to backup
        checkpoint_dir: Where to store checkpoint (default: target_dir/.recovery/)

    Returns:
        Path to created checkpoint, or None if no consciousness to backup
    """
    if not has_existing_consciousness(target_dir):
        return None

    if checkpoint_dir is None:
        checkpoint_dir = target_dir / ".recovery"

    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped checkpoint
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    checkpoint_path = checkpoint_dir / f"pre_restore_{timestamp}"
    checkpoint_path.mkdir(parents=True, exist_ok=True)

    # Backup existing consciousness directories
    dirs_to_backup = [".maceff", "agent", ".claude"]

    for dir_name in dirs_to_backup:
        source = target_dir / dir_name
        if source.exists():
            dest = checkpoint_path / dir_name
            shutil.copytree(source, dest, symlinks=True)

    # Write checkpoint metadata
    metadata = {
        "created": datetime.now().isoformat(),
        "source_dir": str(target_dir),
        "backed_up": [d for d in dirs_to_backup if (target_dir / d).exists()],
    }

    with open(checkpoint_path / "checkpoint_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return checkpoint_path


def restore_from_checkpoint(
    checkpoint_path: Path,
    target_dir: Path,
) -> bool:
    """
    Restore consciousness from a recovery checkpoint.

    Args:
        checkpoint_path: Path to checkpoint directory
        target_dir: Where to restore consciousness

    Returns:
        True if restoration successful
    """
    metadata_path = checkpoint_path / "checkpoint_metadata.json"
    if not metadata_path.exists():
        return False

    with open(metadata_path) as f:
        metadata = json.load(f)

    # Restore each backed up directory
    for dir_name in metadata.get("backed_up", []):
        source = checkpoint_path / dir_name
        dest = target_dir / dir_name

        if source.exists():
            # Remove existing if present
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest, symlinks=True)

    return True


def list_backups(
    backup_dir: Path,
    pattern: str = "*_consciousness.tar.xz",
) -> List[Tuple[Path, datetime]]:
    """
    List backup archives with their creation times.

    Args:
        backup_dir: Directory containing backups
        pattern: Glob pattern for backup files

    Returns:
        List of (path, mtime) tuples, sorted newest first
    """
    backups = []

    for archive in backup_dir.glob(pattern):
        mtime = datetime.fromtimestamp(archive.stat().st_mtime)
        backups.append((archive, mtime))

    # Sort by mtime, newest first
    backups.sort(key=lambda x: x[1], reverse=True)

    return backups


def cleanup_old_backups(
    backup_dir: Path,
    keep_count: int = 5,
    pattern: str = "*_consciousness.tar.xz",
    dry_run: bool = False,
) -> List[Path]:
    """
    Remove old backups, keeping only the most recent N.

    Args:
        backup_dir: Directory containing backups
        keep_count: Number of backups to keep
        pattern: Glob pattern for backup files
        dry_run: If True, report but don't delete

    Returns:
        List of paths that were (or would be) deleted
    """
    backups = list_backups(backup_dir, pattern)

    if len(backups) <= keep_count:
        return []

    to_delete = backups[keep_count:]
    deleted = []

    for archive, mtime in to_delete:
        if not dry_run:
            archive.unlink()
        deleted.append(archive)

    return deleted


def get_backup_retention_count() -> int:
    """
    Get backup retention count from environment or default.

    Returns:
        Number of backups to retain
    """
    env_value = os.getenv("MACF_BACKUP_KEEP")
    if env_value:
        try:
            return int(env_value)
        except ValueError:
            pass
    return 5  # Default


def format_safety_warning(checks: Dict[str, bool]) -> str:
    """
    Format safety warning message for existing consciousness.

    Args:
        checks: Results from detect_existing_consciousness

    Returns:
        Formatted warning message
    """
    detected = [k for k, v in checks.items() if v]

    if not detected:
        return ""

    lines = [
        "WARNING: Existing consciousness detected at target location!",
        "",
        "Detected:",
    ]

    labels = {
        "legacy_state": "Legacy agent state (.maceff/agent_state.json) - old backup format",
        "agent_artifacts": "Consciousness artifacts (agent/)",
        "claude_config": "Claude configuration (.claude/)",
        "events_log": "Events log (.maceff/agent_events_log.jsonl)",
    }

    for key in detected:
        lines.append(f"  - {labels.get(key, key)}")

    lines.extend([
        "",
        "Options:",
        "  1. Use --force to overwrite (creates recovery checkpoint)",
        "  2. Use --target to install to different location",
        "  3. Manually backup existing consciousness first",
    ])

    return "\n".join(lines)
