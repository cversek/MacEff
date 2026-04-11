"""
Task file reader for Claude Code native task storage.

Tasks are stored at: ~/.claude/tasks/{session_uuid}/*.json

Completed tasks may be dot-prefixed (.{id}.json) to hide them from CC's native
scanner while remaining fully accessible to MACF CLI commands.
"""

import json
import os
import stat
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Set

from .models import MacfTask
from ..utils.paths import find_project_root


class TaskReader:
    """
    Reads Claude Code native task JSON files.

    Task files location: ~/.claude/tasks/{session_uuid}/{id}.json

    Environment variable override:
        MACF_TASKS_DIR - If set, use this path instead of ~/.claude/tasks/
                         (useful for testing isolation)
    """

    @classmethod
    def _get_tasks_dir(cls) -> Path:
        """Get tasks directory, respecting MACF_TASKS_DIR env var for test isolation."""
        env_dir = os.environ.get("MACF_TASKS_DIR")
        if env_dir:
            return Path(env_dir)
        return Path.home() / ".claude" / "tasks"

    @property
    def tasks_dir(self) -> Path:
        """Tasks directory (may be overridden by MACF_TASKS_DIR env var)."""
        return self._get_tasks_dir()

    def __init__(self, session_uuid: Optional[str] = None):
        """
        Initialize reader for a specific session or current session.

        Args:
            session_uuid: Session UUID to read from. If None, auto-detect current session.
        """
        self.session_uuid = session_uuid or self._detect_current_session()

    @classmethod
    def _get_project_sessions(cls) -> Set[str]:
        """
        Get session UUIDs that belong to the current project.

        Claude Code stores session transcripts in:
            ~/.claude/projects/{path-encoded-project}/{session_uuid}.jsonl

        Path encoding: /Users/foo/bar -> -Users-foo-bar
        """
        try:
            project_root = find_project_root()
            from macf.utils.paths import encode_cc_project_path
            encoded_path = encode_cc_project_path(str(project_root))

            projects_dir = Path.home() / ".claude" / "projects" / encoded_path
            if not projects_dir.exists():
                return set()

            # Session UUIDs are JSONL filenames (without extension)
            return {f.stem for f in projects_dir.glob("*.jsonl")}
        except (OSError, IOError) as e:
            print(f"⚠️ MACF: session JSONL scan failed: {e}", file=sys.stderr)
            return set()

    @classmethod
    def _detect_current_session(cls) -> Optional[str]:
        """
        Detect current session UUID from environment or most recent PROJECT-SCOPED session.

        Priority:
        1. MACF_SESSION_ID env var (set by MACF hooks)
        2. Most recent session from current project (via Claude Code's project directories)
        3. Most recent session globally (legacy fallback)
        """
        # Priority 1: Check environment variable (set by MACF hooks)
        env_session = os.environ.get("MACF_SESSION_ID")
        if env_session:
            return env_session

        tasks_dir = cls._get_tasks_dir()
        if not tasks_dir.exists():
            return None

        sessions = [d for d in tasks_dir.iterdir() if d.is_dir()]
        if not sessions:
            return None

        # Priority 2: Filter to sessions belonging to current project
        project_sessions = cls._get_project_sessions()
        if project_sessions:
            # Only consider sessions that belong to this project AND have task dirs
            project_scoped = [d for d in sessions if d.name in project_sessions]
            if project_scoped:
                # Sort by modification time, most recent first
                project_scoped.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                return project_scoped[0].name
            else:
                # Project sessions exist but none have task dirs yet (first use).
                # Pick most recent project session by JSONL mtime so bootstrap/create
                # can make the directory. Without this, falls through to Priority 3
                # which picks a DIFFERENT agent's session (cross-agent leakage).
                try:
                    from macf.utils.paths import encode_cc_project_path
                    project_root = find_project_root()
                    encoded = encode_cc_project_path(str(project_root))
                    projects_dir = Path.home() / ".claude" / "projects" / encoded
                    jsonl_files = [
                        (f.stem, f.stat().st_mtime)
                        for f in projects_dir.glob("*.jsonl")
                        if f.stem in project_sessions
                    ]
                    if jsonl_files:
                        jsonl_files.sort(key=lambda x: x[1], reverse=True)
                        return jsonl_files[0][0]
                except OSError as e:
                    print(f"⚠️ MACF: session JSONL scan failed for encoded path '{encoded}': {e}", file=sys.stderr)
                    # Fall through to Priority 3

        # Priority 3: Legacy fallback - most recent globally (cross-project leakage risk)
        sessions.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        return sessions[0].name

    @property
    def session_path(self) -> Optional[Path]:
        """Path to current session's task folder."""
        if not self.session_uuid:
            return None
        return self.tasks_dir / self.session_uuid

    def list_task_files(self, include_hidden: bool = True) -> List[Path]:
        """List task JSON files in current session.

        Args:
            include_hidden: If True (default), include dot-prefixed completed task files.
                          Our CLI always uses True. False is useful for CC-perspective views.
        """
        if not self.session_path or not self.session_path.exists():
            return []

        # Python's Path.glob("*.json") matches hidden files (.*.json) unlike shell glob.
        # Explicitly filter to avoid double-counting when include_hidden=True.
        files = [f for f in self.session_path.glob("*.json") if not f.name.startswith(".")]
        if include_hidden:
            files.extend(self.session_path.glob(".*.json"))

        return sorted(
            files,
            key=lambda p: p.stem.lstrip('.').zfill(10)
        )

    def read_task(self, task_id: str) -> Optional[MacfTask]:
        """Read a single task by ID (supports int or string IDs like '000').

        Checks both visible ({id}.json) and hidden (.{id}.json) paths.
        """
        if not self.session_path:
            return None

        task_file = resolve_task_file(self.session_path, task_id)
        if not task_file:
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
        tasks_dir = cls._get_tasks_dir()
        if not tasks_dir.exists():
            return []

        return [
            d.name for d in tasks_dir.iterdir()
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


def resolve_task_file(session_path: Path, task_id: str) -> Optional[Path]:
    """Find task file whether visible ({id}.json) or hidden (.{id}.json).

    Args:
        session_path: Path to session task directory
        task_id: Task ID (string, e.g. "100" or "000")

    Returns:
        Path to task file, or None if not found in either location.
    """
    visible = session_path / f"{task_id}.json"
    if visible.exists():
        return visible
    hidden = session_path / f".{task_id}.json"
    if hidden.exists():
        return hidden
    return None


def _unprotect_dir(dir_path: Path):
    """Temporarily enable write on a chmod 555 protected directory."""
    os.chmod(dir_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 755


def _protect_dir(dir_path: Path):
    """Re-protect directory to chmod 555."""
    os.chmod(dir_path, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 555


def hide_task_file(session_path: Path, task_id: str) -> bool:
    """Rename {id}.json -> .{id}.json to hide from CC's native scanner.

    Idempotent: no-op if already hidden or file doesn't exist.
    Handles chmod 555 directory protection.
    """
    visible = session_path / f"{task_id}.json"
    hidden = session_path / f".{task_id}.json"

    if not visible.exists():
        return hidden.exists()  # Already hidden = success

    is_protected = not (session_path.stat().st_mode & stat.S_IWUSR)
    try:
        if is_protected:
            _unprotect_dir(session_path)
        visible.rename(hidden)
        return True
    except OSError as e:
        import sys
        print(f"⚠️ MACF: hide_task_file failed for #{task_id}: {e}", file=sys.stderr)
        return False
    finally:
        if session_path.exists():
            _protect_dir(session_path)


def unhide_task_file(session_path: Path, task_id: str) -> bool:
    """Rename .{id}.json -> {id}.json to show to CC's native scanner.

    Idempotent: no-op if already visible or file doesn't exist.
    Handles chmod 555 directory protection.
    """
    hidden = session_path / f".{task_id}.json"
    visible = session_path / f"{task_id}.json"

    if not hidden.exists():
        return visible.exists()  # Already visible = success

    is_protected = not (session_path.stat().st_mode & stat.S_IWUSR)
    try:
        if is_protected:
            _unprotect_dir(session_path)
        hidden.rename(visible)
        return True
    except OSError as e:
        import sys
        print(f"⚠️ MACF: unhide_task_file failed for #{task_id}: {e}", file=sys.stderr)
        return False
    finally:
        if session_path.exists():
            _protect_dir(session_path)


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

    task_file = resolve_task_file(reader.session_path, task_id)
    if not task_file:
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
