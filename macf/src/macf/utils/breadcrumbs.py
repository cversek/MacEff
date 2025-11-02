"""
Breadcrumbs utilities.
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from .paths import find_project_root
from .session import get_current_session_id
from .state import SessionOperationalState, read_json_safely

def format_breadcrumb(
    cycle: int,
    session_id: str,
    prompt_uuid: Optional[str] = None,
    completion_time: Optional[float] = None,
    git_hash: Optional[str] = None
) -> str:
    """
    Format enhanced breadcrumb with self-describing components.

    Full format (Cycle 61+): c_61/s_4107604e/p_b0377089/t_1761360651/g_c3ec870
    Minimal format: c_61/s_4107604e/p_b0377089

    Args:
        cycle: Cycle number (from agent_state.json)
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
    parts = [
        f"c_{cycle}",
        f"s_{session_short}",
        f"p_{prompt_short}"
    ]

    # Optional timestamp (unix epoch for TODO completion)
    if completion_time is not None:
        parts.append(f"t_{int(completion_time)}")

    # Optional git hash
    if git_hash:
        parts.append(f"g_{git_hash}")

    return "/".join(parts)

def parse_breadcrumb(breadcrumb: str) -> Optional[Dict[str, Any]]:
    """
    Parse enhanced breadcrumb into components.

    Supports both old (C60/session/prompt) and new (c_61/s_session/p_prompt/t_time/g_hash) formats.

    Args:
        breadcrumb: Breadcrumb string like "c_61/s_4107604e/p_ead030a5/t_1761360651/g_c3ec870"

    Returns:
        Dict with keys: cycle, session_id, prompt_uuid, timestamp, git_hash
        Returns None if parsing fails

    Example:
        >>> parse_breadcrumb("c_61/s_4107604e/p_ead030a5/t_1761360651/g_c3ec870")
        {
            'cycle': 61,
            'session_id': '4107604e',
            'prompt_uuid': 'ead030a5',
            'timestamp': 1761360651,
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

            # Old format without prefixes (C60/4107604e/ead030a or ead030a5)
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

    except Exception:
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
    except Exception:
        return []

def extract_current_git_hash() -> Optional[str]:
    """
    Extract current git commit hash (short form).

    Returns:
        Short git hash (7 chars) like "c3ec870" or None if not in git repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            cwd=find_project_root(),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None

def get_breadcrumb() -> str:
    """
    Get current breadcrumb with all 5 components auto-gathered.

    Zero-argument convenience function for hooks - ultimate parse-don't-construct!
    Auto-gathers: cycle, session_id, prompt_uuid, current timestamp, git_hash.

    Returns:
        Formatted breadcrumb like "c_64/s_4107604e/p_c7ad5830/t_1761419389/g_abc1234"
        Returns minimal breadcrumb on any failure (never crashes)

    Example:
        >>> breadcrumb = get_breadcrumb()
        "c_64/s_4107604e/p_c7ad5830/t_1761419389/g_b231846"
    """
    try:
        # Auto-gather all 5 components
        session_id = get_current_session_id()

        # Try loading state from all possible agent_id directories
        # Hooks may run from different CWD, so try multiple possibilities
        state = None
        for agent_id_attempt in _find_possible_agent_ids(session_id):
            state_attempt = SessionOperationalState.load(session_id, agent_id=agent_id_attempt)
            # Check if this state has actual data (not default)
            if state_attempt.current_dev_drv_prompt_uuid is not None:
                state = state_attempt
                break

        # Fallback to auto-detection if no state found
        if state is None:
            try:
                from .config import ConsciousnessConfig
                agent_id = ConsciousnessConfig().agent_id
            except Exception:
                agent_id = None
            state = SessionOperationalState.load(session_id, agent_id=agent_id)

        # Get cycle from agent_state.json (project-scoped persistence)
        project_root = find_project_root()
        agent_state_path = project_root / ".maceff" / "agent_state.json"
        agent_state = read_json_safely(agent_state_path)
        cycle_num = agent_state.get("current_cycle_number", 1)

        # Get current timestamp
        current_time = int(time.time())

        # Get git hash (can be None if not in repo)
        git_hash = extract_current_git_hash()

        # Format with all 5 components
        return format_breadcrumb(
            cycle=cycle_num,
            session_id=session_id,
            prompt_uuid=state.current_dev_drv_prompt_uuid,
            completion_time=current_time,
            git_hash=git_hash
        )
    except Exception:
        # Safe fallback - never crash hooks
        return "c_1/s_unknown/p_none"
