"""
Session utilities.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional
from .paths import find_project_root
# Events are sole source of truth - state file reads removed

def get_current_session_id(hook_input: Optional[dict] = None) -> str:
    """Get current session ID.

    Resolution order, most authoritative first:

    1. ``hook_input['session_id']`` — CC hands every hook its own session id;
       when the caller has it, nothing else can be more correct.
    2. ``MACF_SESSION_ID`` / ``CLAUDE_CODE_SESSION_ID`` env — covers CLI
       invocations made from inside a session (and test isolation).
    3. Most recent ``session_started`` event — out-of-band CLI with no env.
    4. mtime-based JSONL detection — first run, before any events exist.

    Tiers 1-2 exist because the event log is a *global* last-writer-wins
    singleton: the moment a second session starts under the same agent home,
    its ``session_started`` makes every hook in every session — including the
    original, still-live one — stamp the newcomer's id. Ordinary hooks never
    write ``session_started``, so the original could never reclaim its identity
    (cversek/MacEff#159's sibling, #158). The hook process already holds the
    right answer; prefer it over the shared log.

    Args:
        hook_input: Parsed hook stdin payload, when the caller is a hook.

    Returns:
        Session ID string or "unknown" if not found
    """
    # TIER 1: the caller's own session, straight from CC.
    if hook_input:
        sid = hook_input.get("session_id")
        if sid:
            return str(sid)

    # TIER 2: environment (session-scoped by construction).
    for var in ("MACF_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        sid = os.environ.get(var)
        if sid:
            return sid

    # TIER 3: Event-first approach - query session_started event
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

    Selection is order-independent: among the candidate JSONL files it picks
    the globally newest by mtime, with the filename as a tiebreaker, so the
    result does not depend on glob / iterdir ordering (which is
    filesystem-dependent and was a source of flaky behaviour).

    Returns:
        Session ID string or "unknown" if not found
    """
    projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.exists():
        return "unknown"

    def _newest_stem(dirs) -> Optional[str]:
        candidates = []
        for project_dir in dirs:
            if project_dir.is_dir():
                candidates.extend(project_dir.glob("*.jsonl"))
        if not candidates:
            return None
        # Global newest by mtime; filename tiebreaks equal mtimes so the
        # result is deterministic regardless of iteration order.
        newest = max(candidates, key=lambda p: (p.stat().st_mtime, p.name))
        return newest.stem

    # Prefer project directories matching the current project name; if none
    # of them contain a JSONL, fall back to all projects.
    project_name = find_project_root().name
    return (
        _newest_stem(projects_dir.glob(f"*{project_name}*"))
        or _newest_stem(projects_dir.iterdir())
        or "unknown"
    )

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
    except (OSError, IOError, ValueError) as e:
        print(f"⚠️ MACF: session migration detection failed: {e}", file=sys.stderr)
        return (False, "")
