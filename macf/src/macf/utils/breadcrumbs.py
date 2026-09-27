"""
Breadcrumbs utilities.
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from .paths import find_git_worktree, find_project_root, git_location_redirected
from .session import get_current_session_id
from .json_io import read_json


def get_current_dev_drv_prompt_uuid() -> Optional[str]:
    """
    Get prompt UUID from most recent DEV_DRV start event in JSONL log.

    This queries the append-only event log instead of mutable session_state.json,
    providing reliable forensic data that survives state synchronization issues.

    CRITICAL: Filters by current session_id to avoid picking up test data or
    events from other sessions that may have polluted the shared JSONL log.

    Returns:
        Prompt UUID string (8+ chars) or None if no DEV_DRV events found
    """
    try:
        # Import here to avoid circular dependency
        from ..agent_events_log import read_events

        # Get current session to filter events
        current_session = get_current_session_id()

        # Get most recent dev_drv_started event FOR THIS SESSION
        # limit=None: exits on the first match; bounded, a breadcrumb silently
        # lost its prompt uuid under load. See the compiled-false-absence trap in `empiricism`.
        for event in read_events(limit=None, reverse=True):
            if event.get("event") == "dev_drv_started":
                data = event.get("data", {})

                # Filter by current session - skip test data and other sessions
                event_session = data.get("session_id", "")
                if current_session and event_session and not event_session.startswith(current_session[:8]):
                    continue  # Skip events from other sessions

                prompt_uuid = data.get("prompt_uuid")
                if prompt_uuid and prompt_uuid != "unknown":
                    return prompt_uuid
                break  # Found event but no valid UUID

        return None
    except (OSError, IOError, ValueError) as e:
        print(f"⚠️ MACF: prompt UUID extraction failed: {e}", file=sys.stderr)
        return None

def format_breadcrumb(
    cycle: int,
    session_id: str,
    prompt_uuid: Optional[str] = None,
    completion_time: Optional[float] = None,
    git_hash: Optional[str] = None
) -> str:
    """
    Format enhanced breadcrumb with self-describing components.

    Full format (Cycle 42+): s_abc12345/c_42/g_c3ec870/p_b0377089/t_1730000000
    Minimal format: s_abc12345/c_42/p_b0377089

    Args:
        cycle: Cycle number (from event log)
        session_id: Full session ID
        prompt_uuid: DEV_DRV prompt UUID (optional, shows 'none' if missing)
        completion_time: Unix timestamp when TODO completed (optional)
        git_hash: Current git commit hash (optional)

    Returns:
        Self-describing breadcrumb string
    """
    # Session: first 8 chars
    session_short = session_id[:8] if session_id else "unknown"

    # Prompt: first 8 chars (easier searching, stable for entire DEV_DRV)
    if prompt_uuid:
        prompt_short = prompt_uuid[:8] if len(prompt_uuid) >= 8 else prompt_uuid
    else:
        prompt_short = "none"

    # Build breadcrumb with self-describing prefixes
    # Order: slow-changing → fast-changing (s/c/g/p/t)
    parts = [
        f"s_{session_short}",
        f"c_{cycle}",
    ]

    # Optional git hash (slow-changing, after cycle)
    if git_hash:
        parts.append(f"g_{git_hash}")

    # Prompt UUID (work trigger)
    parts.append(f"p_{prompt_short}")

    # Optional timestamp (fastest-changing, last)
    if completion_time is not None:
        parts.append(f"t_{int(completion_time)}")

    return "/".join(parts)

def parse_breadcrumb(breadcrumb: str) -> Optional[Dict[str, Any]]:
    """
    Parse enhanced breadcrumb into components.

    Supports both old (C60/session/prompt) and new (c_61/s_session/p_prompt/t_time/g_hash) formats.

    Args:
        breadcrumb: Breadcrumb string like "s_abc12345/c_42/g_c3ec870/p_ead030a5/t_1730000000"

    Returns:
        Dict with keys: cycle, session_id, prompt_uuid, timestamp, git_hash
        Returns None if parsing fails

    Example:
        >>> parse_breadcrumb("s_abc12345/c_42/g_c3ec870/p_ead030a5/t_1730000000")
        {
            'cycle': 42,
            'session_id': 'abc12345',
            'prompt_uuid': 'ead030a5',
            'timestamp': 1730000000,
            'git_hash': 'c3ec870'
        }
    """
    try:
        parts = breadcrumb.split('/')

        if len(parts) < 3:
            return None

        result = {}

        # Parse each component
        for part in parts:
            if not part:
                continue

            # New format with prefixes
            if '_' in part:
                prefix, value = part.split('_', 1)

                if prefix == 'c':
                    result['cycle'] = int(value)
                elif prefix == 's':
                    result['session_id'] = value
                elif prefix == 'p':
                    result['prompt_uuid'] = value if value != 'none' else None
                elif prefix == 't':
                    # Parse timestamp (YYYYMMDD_HHMM or unix epoch)
                    if len(value) == 13 and value[8] == '_':
                        # YYYYMMDD_HHMM format - convert to unix timestamp
                        dt = datetime.strptime(value, "%Y%m%d_%H%M")
                        result['timestamp'] = int(dt.timestamp())
                    else:
                        # Assume unix epoch
                        result['timestamp'] = int(value)
                elif prefix == 'g':
                    result['git_hash'] = value if value != 'none' else None

            # Old format without prefixes (C60/abc12345/ead030a or ead030a5)
            else:
                if part.startswith('C') and part[1:].isdigit():
                    result['cycle'] = int(part[1:])
                elif len(part) == 8 and not result.get('session_id'):
                    result['session_id'] = part
                elif len(part) in (7, 8) and not result.get('prompt_uuid'):
                    # Support both old 7-char and new 8-char formats
                    result['prompt_uuid'] = part

        # Validate required fields
        if 'cycle' not in result or 'session_id' not in result:
            return None

        # Set defaults for optional fields
        result.setdefault('prompt_uuid', None)
        result.setdefault('timestamp', None)
        result.setdefault('git_hash', None)

        return result

    except (OSError, IOError, ValueError, KeyError) as e:
        print(f"⚠️ MACF: breadcrumb parse failed: {e}", file=sys.stderr)
        return None

def _find_possible_agent_ids(session_id: str) -> list:
    """
    Find all possible agent_id values by scanning /tmp/macf/ for session directories.

    Args:
        session_id: Session ID to search for

    Returns:
        List of agent_id strings that have this session (most likely first)
    """
    try:
        tmp_macf = Path("/tmp/macf")
        if not tmp_macf.exists():
            return []

        possible_ids = []
        for agent_dir in tmp_macf.iterdir():
            if not agent_dir.is_dir():
                continue

            session_dir = agent_dir / session_id
            if session_dir.exists():
                possible_ids.append(agent_dir.name)

        return possible_ids
    except (OSError, IOError) as e:
        print(f"⚠️ MACF: agent ID scan failed: {e}", file=sys.stderr)
        return []

def _is_object_id(text: str) -> bool:
    return len(text) in (40, 64) and all(c in "0123456789abcdef" for c in text)


def _head_from_files(worktree: Path) -> Optional[str]:
    """HEAD's commit id read from the repository's own files, or None when they
    do not state it plainly: a reftable store, a symbolic ref naming another
    symbolic ref, an unborn branch, anything unrecognised. None sends the
    caller to git, and so does an OSError, which propagates.
    """
    dot_git = worktree / ".git"
    if dot_git.is_file():  # a linked worktree or submodule: "gitdir: <path>"
        text = dot_git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir:"):
            return None
        git_dir = Path(text[len("gitdir:"):].strip())
        git_dir = git_dir if git_dir.is_absolute() else worktree / git_dir
    else:
        git_dir = dot_git
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref:"):
        return head if _is_object_id(head) else None  # detached
    ref = head[len("ref:"):].strip()
    common = git_dir  # a linked worktree keeps its branches in the main repository
    if (git_dir / "commondir").is_file():
        named = Path((git_dir / "commondir").read_text(encoding="utf-8").strip())
        common = named if named.is_absolute() else git_dir / named
    for base in (git_dir, common):
        if (base / ref).is_file():
            value = (base / ref).read_text(encoding="utf-8").strip()
            return value if _is_object_id(value) else None
    if (common / "packed-refs").is_file():
        for line in (common / "packed-refs").read_text(encoding="utf-8").splitlines():
            fields = line.split(" ")  # "<id> <refname>"; ref names hold no spaces
            if len(fields) == 2 and fields[1] == ref and _is_object_id(fields[0]):
                return fields[0]
    return None


def extract_current_git_hash() -> Optional[str]:
    """
    Extract current git commit hash (short form).

    Read from the repository's files when they state HEAD plainly, which costs
    a few file reads where running git costs a process on every breadcrumb;
    otherwise git is asked. Always the first seven characters: git lengthens
    its abbreviation when seven are ambiguous in the repository, and a
    breadcrumb should not change with the path that computed it.

    Returns:
        Short git hash (7 chars) like "c3ec870" or None if not in git repo
    """
    root = find_project_root()
    if not git_location_redirected():
        try:
            worktree = find_git_worktree(root)
            if worktree is None:
                return None
            oid = _head_from_files(worktree)
        except (OSError, UnicodeDecodeError) as e:
            print(f"⚠️ MACF: could not read HEAD from the repository files ({e}); asking git",
                  file=sys.stderr)
            oid = None
        if oid:
            return oid[:7]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            cwd=root,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:7]
    except Exception as e:
        print(f"⚠️ MACF: Git command failed (fallback: no prompt_uuid): {e}", file=sys.stderr)

    return None

def get_breadcrumb() -> str:
    """
    Get current breadcrumb with all 5 components auto-gathered.

    Zero-argument convenience function for hooks - ultimate parse-don't-construct!
    Auto-gathers: cycle, session_id, prompt_uuid, current timestamp, git_hash.

    Note: prompt_uuid is now sourced from append-only JSONL event log instead of
    mutable session_state.json, ensuring forensic reliability.

    Returns:
        Formatted breadcrumb like "s_abc12345/c_42/g_abc1234/p_c7ad5830/t_1730000000"
        Returns minimal breadcrumb on any failure (never crashes)

    Example:
        >>> breadcrumb = get_breadcrumb()
        "s_abc12345/c_42/g_b231846/p_c7ad5830/t_1730000000"
    """
    try:
        # Auto-gather all 5 components
        session_id = get_current_session_id()

        # Get prompt UUID from JSONL event log (append-only truth source)
        # This replaces the old mutable session_state.json approach which could desync
        prompt_uuid = get_current_dev_drv_prompt_uuid()

        # Get cycle from event log (event-first architecture)
        from ..event_queries import get_cycle_number_from_events
        cycle_num = get_cycle_number_from_events()

        # Get current timestamp
        current_time = int(time.time())

        # Get git hash (can be None if not in repo)
        git_hash = extract_current_git_hash()

        # Format with all 5 components
        return format_breadcrumb(
            cycle=cycle_num,
            session_id=session_id,
            prompt_uuid=prompt_uuid,
            completion_time=current_time,
            git_hash=git_hash
        )
    except Exception as e:
        print(f"⚠️ MACF: breadcrumb generation failed: {e}", file=sys.stderr)
        return "s_unknown/c_1/p_none"
