"""
Task archival and restoration for MACF tasks.

Archives preserve full task JSON with MTMD for historical reference.
Archive location: agent/public/task_archives/

Archive vs Status:
- `task edit status archived` = "soft archive" (CC UI hiding only)
- `task archive #N` = "full archive" (disk preservation + status change)
"""

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from ..utils.paths import find_agent_home

from .reader import TaskReader, update_task_file
from .models import MacfTask


@dataclass
class ArchiveResult:
    """Result of an archive operation."""
    success: bool
    task_id: str
    archive_path: Optional[str] = None
    error: Optional[str] = None
    children_archived: List[str] = None

    def __post_init__(self):
        if self.children_archived is None:
            self.children_archived = []


@dataclass
class RestoreResult:
    """Result of a restore operation."""
    success: bool
    old_id: str
    new_id: Optional[str] = None
    error: Optional[str] = None


def get_archive_dir() -> Path:
    """
    Get the task archives directory.

    Uses find_agent_home() canonical path resolution.
    """
    return find_agent_home() / "agent" / "public" / "task_archives"


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """Sanitize text for use in filename."""
    # Remove ANSI codes
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    # Remove special characters except alphanumeric, space, dash, underscore
    text = re.sub(r'[^\w\s\-]', '', text)
    # Replace spaces with underscores
    text = text.replace(' ', '_')
    # Collapse multiple underscores
    text = re.sub(r'_+', '_', text)
    # Truncate
    return text[:max_length].strip('_')


def get_archive_filename(task: MacfTask) -> str:
    """Generate archive filename for a task."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject_safe = sanitize_filename(task.subject)
    return f"{date_str}_task_{task.id}_{subject_safe}.json"


def archive_task(
    task_id: str,
    cascade: bool = True,
    session_uuid: Optional[str] = None,
) -> ArchiveResult:
    """
    Archive a task to disk and set its status to 'archived'.

    Args:
        task_id: ID of task to archive
        cascade: If True (default), archive all children recursively
        session_uuid: Session UUID (auto-detect if None)

    Returns:
        ArchiveResult with success status and archive path
    """
    reader = TaskReader(session_uuid)
    task = reader.read_task(task_id)

    if not task:
        return ArchiveResult(
            success=False,
            task_id=task_id,
            error=f"Task #{task_id} not found"
        )

    # Create archive directory
    archive_dir = get_archive_dir()
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Build list of tasks to archive (task + children if cascade)
    tasks_to_archive = [task]
    children_archived = []

    if cascade:
        all_tasks = reader.read_all_tasks()
        children = _get_all_descendants(task_id, all_tasks)
        tasks_to_archive.extend(children)
        children_archived = [t.id for t in children]

    # Archive each task
    primary_archive_path = None
    for t in tasks_to_archive:
        # Read raw JSON for full preservation
        task_file = reader.session_path / f"{t.id}.json"
        if not task_file.exists():
            continue

        with open(task_file, "r") as f:
            task_data = json.load(f)

        # Add archive metadata
        task_data["_archive_metadata"] = {
            "archived_at": datetime.now().isoformat(),
            "original_session": reader.session_uuid,
            "original_file": str(task_file),
            "cascade_parent": task_id if t.id != task_id else None,
        }

        # Write to archive
        archive_filename = get_archive_filename(t)
        archive_path = archive_dir / archive_filename

        # Handle filename collision
        counter = 1
        while archive_path.exists():
            base = archive_filename.rsplit('.', 1)[0]
            archive_path = archive_dir / f"{base}_{counter}.json"
            counter += 1

        with open(archive_path, "w") as f:
            json.dump(task_data, f, indent=2)

        if t.id == task_id:
            primary_archive_path = str(archive_path)

        # Update original task status to 'archived'
        update_task_file(t.id, {"status": "archived"}, reader.session_uuid)

    return ArchiveResult(
        success=True,
        task_id=task_id,
        archive_path=primary_archive_path,
        children_archived=children_archived,
    )


def _get_all_descendants(parent_id: str, all_tasks: List[MacfTask]) -> List[MacfTask]:
    """Get all descendant tasks of a parent (recursive)."""
    descendants = []
    direct_children = [t for t in all_tasks if t.parent_id == parent_id]

    for child in direct_children:
        descendants.append(child)
        descendants.extend(_get_all_descendants(child.id, all_tasks))

    return descendants


def restore_task(
    archive_path_or_id: str,
    session_uuid: Optional[str] = None,
) -> RestoreResult:
    """
    Restore a task from archive.

    Creates a new task with a new ID but preserves MTMD history.

    Args:
        archive_path_or_id: Path to archive file OR original task ID to find in archives
        session_uuid: Session UUID for restoration (auto-detect if None)

    Returns:
        RestoreResult with new task ID
    """
    archive_dir = get_archive_dir()

    # Find archive file
    archive_path = None
    if os.path.exists(archive_path_or_id):
        archive_path = Path(archive_path_or_id)
    else:
        # Try to find by task ID in archive filenames
        try:
            search_id = archive_path_or_id.lstrip('#')
            pattern = f"*_task_{search_id}_*.json"
            matches = list(archive_dir.glob(pattern))
            if matches:
                # Use most recent
                matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                archive_path = matches[0]
        except ValueError:
            pass

    if not archive_path or not archive_path.exists():
        return RestoreResult(
            success=False,
            old_id="0",
            error=f"Archive not found: {archive_path_or_id}"
        )

    # Read archived task
    with open(archive_path, "r") as f:
        task_data = json.load(f)

    old_id = str(task_data.get("id", "0"))

    # Remove archive metadata before restoration
    task_data.pop("_archive_metadata", None)

    # Get reader to find next available ID
    reader = TaskReader(session_uuid)
    if not reader.session_path:
        return RestoreResult(
            success=False,
            old_id=old_id,
            error="Cannot determine session path for restoration"
        )

    # Find next available ID
    existing_ids = [p.stem for p in reader.list_task_files() if p.stem.isdigit()]
    new_id = str(max([int(id_str) for id_str in existing_ids], default=0) + 1)

    # Update task data with new ID
    task_data["id"] = str(new_id)  # CC uses string IDs
    task_data["status"] = "pending"  # Reset status

    # Add restoration note to description
    restoration_note = f"\n\n---\n_Restored from archive on {datetime.now().strftime('%Y-%m-%d %H:%M')}. Original ID: #{old_id}_"
    task_data["description"] = task_data.get("description", "") + restoration_note

    # Write new task file
    new_task_file = reader.session_path / f"{new_id}.json"
    with open(new_task_file, "w") as f:
        json.dump(task_data, f, indent=2)

    return RestoreResult(
        success=True,
        old_id=old_id,
        new_id=new_id,
    )


def list_archived_tasks() -> List[Dict[str, Any]]:
    """
    List all archived tasks.

    Returns:
        List of dicts with archive info (path, id, subject, archived_at)
    """
    archive_dir = get_archive_dir()
    if not archive_dir.exists():
        return []

    archives = []
    for archive_file in sorted(archive_dir.glob("*.json")):
        try:
            with open(archive_file, "r") as f:
                data = json.load(f)

            archive_meta = data.get("_archive_metadata", {})
            archives.append({
                "path": str(archive_file),
                "filename": archive_file.name,
                "id": data.get("id"),
                "subject": data.get("subject", ""),
                "archived_at": archive_meta.get("archived_at"),
                "original_session": archive_meta.get("original_session"),
            })
        except (json.JSONDecodeError, IOError):
            continue

    return archives
