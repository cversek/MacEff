"""
Task file reader for Claude Code native task storage.

Tasks are stored at: ~/.claude/tasks/{session_uuid}/*.json
"""

import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

from .models import MacfTask


class TaskReader:
    """
    Reads Claude Code native task JSON files.

    Task files location: ~/.claude/tasks/{session_uuid}/{id}.json
    """

    CLAUDE_DIR = Path.home() / ".claude"
    TASKS_DIR = CLAUDE_DIR / "tasks"

    def __init__(self, session_uuid: Optional[str] = None):
        """
        Initialize reader for a specific session or current session.

        Args:
            session_uuid: Session UUID to read from. If None, auto-detect current session.
        """
        self.session_uuid = session_uuid or self._detect_current_session()

    @classmethod
    def _detect_current_session(cls) -> Optional[str]:
        """
        Detect current session UUID from environment or most recent session.

        Returns most recently modified session folder if not determinable.
        """
        # Check environment variable (set by MACF hooks)
        env_session = os.environ.get("MACF_SESSION_ID")
        if env_session:
            return env_session

        # Fall back to most recently modified session folder
        if not cls.TASKS_DIR.exists():
            return None

        sessions = [d for d in cls.TASKS_DIR.iterdir() if d.is_dir()]
        if not sessions:
            return None

        # Sort by modification time, most recent first
        sessions.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        return sessions[0].name

    @property
    def session_path(self) -> Optional[Path]:
        """Path to current session's task folder."""
        if not self.session_uuid:
            return None
        return self.TASKS_DIR / self.session_uuid

    def list_task_files(self) -> List[Path]:
        """List all task JSON files in current session."""
        if not self.session_path or not self.session_path.exists():
            return []

        return sorted(
            self.session_path.glob("*.json"),
            key=lambda p: p.stem.zfill(10)  # String-safe sorting with zero-padding
        )

    def read_task(self, task_id: str) -> Optional[MacfTask]:
        """Read a single task by ID (supports int or string IDs like '000')."""
        if not self.session_path:
            return None

        task_file = self.session_path / f"{task_id}.json"
        if not task_file.exists():
            return None

        try:
            with open(task_file, "r") as f:
                data = json.load(f)
            return MacfTask.from_json(
                data,
                session_uuid=self.session_uuid,
                file_path=str(task_file),
            )
        except (json.JSONDecodeError, IOError):
            return None

    def read_all_tasks(self) -> List[MacfTask]:
        """Read all tasks from current session."""
        tasks = []
        for task_file in self.list_task_files():
            try:
                with open(task_file, "r") as f:
                    data = json.load(f)
                task = MacfTask.from_json(
                    data,
                    session_uuid=self.session_uuid,
                    file_path=str(task_file),
                )
                tasks.append(task)
            except (json.JSONDecodeError, IOError):
                continue
        return tasks

    @classmethod
    def list_all_sessions(cls) -> List[str]:
        """List all available session UUIDs."""
        if not cls.TASKS_DIR.exists():
            return []

        return [
            d.name for d in cls.TASKS_DIR.iterdir()
            if d.is_dir() and (d / "*.json").parent.exists()
        ]

    @classmethod
    def read_all_sessions(cls) -> Dict[str, List[MacfTask]]:
        """Read tasks from all sessions."""
        result = {}
        for session_uuid in cls.list_all_sessions():
            reader = cls(session_uuid)
            tasks = reader.read_all_tasks()
            if tasks:
                result[session_uuid] = tasks
        return result


def get_current_session_tasks() -> List[MacfTask]:
    """Convenience function to get all tasks from current session."""
    reader = TaskReader()
    return reader.read_all_tasks()


def get_all_session_tasks() -> Dict[str, List[MacfTask]]:
    """Convenience function to get all tasks from all sessions."""
    return TaskReader.read_all_sessions()


def update_task_file(task_id: str, updates: Dict[str, Any], session_uuid: Optional[str] = None) -> bool:
    """
    Update a task JSON file with new field values.

    Args:
        task_id: Task ID to update
        updates: Dict of field names to new values
        session_uuid: Session UUID (auto-detect if None)

    Returns:
        True if successful, False otherwise
    """
    reader = TaskReader(session_uuid)
    if not reader.session_path:
        return False

    task_file = reader.session_path / f"{task_id}.json"
    if not task_file.exists():
        return False

    try:
        # Read current data
        with open(task_file, "r") as f:
            data = json.load(f)

        # Apply updates
        for key, value in updates.items():
            if key == "id":
                continue  # ID is immutable
            data[key] = value

        # Write back
        with open(task_file, "w") as f:
            json.dump(data, f, indent=2)

        return True
    except (json.JSONDecodeError, IOError):
        return False
