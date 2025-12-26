"""
Session utilities.
"""

import json
import sys
from pathlib import Path
from typing import Optional
from .paths import find_project_root
# Events are sole source of truth - state file reads removed

def get_current_session_id() -> str:
    """Get current session ID.

    PRIMARY: Query event log for most recent session_started event (authoritative).
    FALLBACK: Use mtime-based JSONL file detection (for first run before events).

    The event-based approach is deterministic and consistent across all hooks,
    unlike mtime-based detection which can vary when multiple session files
    are being written concurrently (e.g., after `claude -c`).

    Returns:
        Session ID string or "unknown" if not found
    """
    # PRIMARY: Event-first approach - query session_started event
    try:
        from ..event_queries import get_current_session_id_from_events
        session_id = get_current_session_id_from_events()
        if session_id:
            return session_id
        # No session_started events yet - warn and fallback
        print("⚠️ MACF: No session_started events found, falling back to mtime-based detection", file=sys.stderr)
    except Exception as e:
        print(f"⚠️ MACF: Event query failed ({e}), falling back to mtime-based detection", file=sys.stderr)

    # FALLBACK: mtime-based detection (for first run before any events)
    return _get_session_id_from_mtime()


def _get_session_id_from_mtime() -> str:
    """Get session ID from newest JSONL file by modification time.

    This is the legacy approach, kept as fallback for first run
    before any session_started events exist.

    Returns:
        Session ID string or "unknown" if not found
    """
    projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.exists():
        return "unknown"

    # Find project directory using current working directory name
    project_name = find_project_root().name

    # Try exact match first
    for project_dir in projects_dir.glob(f"*{project_name}*"):
        jsonl_files = sorted(
            project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if jsonl_files:
            # Extract session ID from filename
            newest = jsonl_files[0]
            return newest.stem

    # Fallback: find newest JSONL across all projects
    all_jsonl = []
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            all_jsonl.extend(project_dir.glob("*.jsonl"))

    if all_jsonl:
        newest = max(all_jsonl, key=lambda p: p.stat().st_mtime)
        return newest.stem

    return "unknown"

def get_last_user_prompt_uuid(session_id: Optional[str] = None) -> Optional[str]:
    """
    Get UUID of the last user prompt in current session.

    Reads JSONL backwards to find most recent message with role='user'.

    Args:
        session_id: Session ID (auto-detected if None)

    Returns:
        Message UUID (message.id) or None if not found
    """
    if not session_id:
        session_id = get_current_session_id()

    if session_id == "unknown":
        return None

    # Find JSONL file
    jsonl_pattern = f"{session_id}.jsonl"
    project_dirs = [Path.home() / ".claude" / "projects"]

    jsonl_path = None
    for project_dir in project_dirs:
        if not project_dir.exists():
            continue
        for file_path in project_dir.rglob(jsonl_pattern):
            jsonl_path = file_path
            break
        if jsonl_path:
            break

    if not jsonl_path or not jsonl_path.exists():
        return None

    # Read backwards to find last user message
    try:
        with open(jsonl_path, 'r') as f:
            lines = f.readlines()

        # Iterate backwards
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                message = data.get('message', {})
                if message.get('role') == 'user':
                    content = message.get('content', '')

                    # Skip hook messages (post-tool-use-hook, user-prompt-submit-hook, etc.)
                    if isinstance(content, str) and '-hook>' in content:
                        continue

                    # Skip tool result messages (content is list of tool_result objects)
                    if isinstance(content, list):
                        continue

                    # Found actual user text prompt
                    return data.get('uuid')
            except json.JSONDecodeError:
                continue

    except Exception as e:
        print(f"⚠️ MACF: Session file read failed (fallback: no prompt_uuid): {e}", file=sys.stderr)

    return None

def detect_session_migration(current_session_id: str, agent_root: Optional[Path] = None) -> tuple[bool, str]:
    """
    Check if session ID changed since last run.

    Args:
        current_session_id: Current session identifier
        agent_root: Project root (auto-detected if None)

    Returns:
        Tuple of (is_migration: bool, old_session_id: str)
    """
    try:
        # Event-first: query last session from events
        from ..event_queries import get_last_session_id_from_events
        last_session_id = get_last_session_id_from_events()

        if not last_session_id:
            # First run - no migration
            return (False, "")

        # Migration if session IDs differ
        is_migration = (last_session_id != current_session_id)
        return (is_migration, last_session_id)
    except Exception:
        return (False, "")
