"""
State utilities.

NOTE (Phase 7 Complete - Mutable State Removal):
State file read/write APIs have been removed. Use event_queries.py functions.
Events (JSONL) are the sole source of truth.
See: agent/public/roadmaps/2025-12-02_DETOUR_Mutable_State_Deprecation/roadmap.md
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from .paths import get_session_dir

# Test isolation: Override agent root for state file path resolution
# Set via set_state_root() to isolate tests from production state
_TEST_STATE_ROOT: Optional[Path] = None


def set_state_root(path: Optional[Path]) -> None:
    """
    Set test isolation path for state files.

    When set, all state file path resolution uses this path as agent_root
    instead of auto-detecting project root. Use in test fixtures.

    Args:
        path: Path to use as agent_root, or None to reset to auto-detection

    Example:
        @pytest.fixture(autouse=True)
        def isolate_state(tmp_path):
            from macf.utils.state import set_state_root
            set_state_root(tmp_path)
            yield
            set_state_root(None)
    """
    global _TEST_STATE_ROOT
    _TEST_STATE_ROOT = Path(path) if path else None

def write_json_safely(path: Path, data: dict) -> bool:
    """
    Atomic JSON write with error handling.

    Args:
        path: Path to JSON file
        data: Dict to write

    Returns:
        True if successful, False otherwise
    """
    try:
        # Write to temp file first
        temp_path = path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)

        # Atomic rename
        temp_path.replace(path)
        return True
    except Exception:
        # Clean up temp file if it exists
        temp_path = path.with_suffix('.tmp')
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError as e:
                print(f"⚠️ MACF: Temp file cleanup failed: {e}", file=sys.stderr)
        return False

def read_json(path: Path) -> dict:
    """
    JSON read with warn + reraise error handling.

    Warns to stderr on error, then re-raises for caller to handle.
    Caller decides fallback behavior; this function ensures visibility.

    Args:
        path: Path to JSON file

    Returns:
        Dict contents if successful

    Raises:
        FileNotFoundError: File doesn't exist (after warning to stderr)
        OSError: File access errors (after warning to stderr)
        json.JSONDecodeError: Invalid JSON (after warning to stderr)
    """
    try:
        if not path.exists():
            print(f"⚠️ MACF: JSON file not found ({path.name})", file=sys.stderr)
            raise FileNotFoundError(f"JSON file not found: {path}")
        with open(path, 'r') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ MACF: JSON read failed ({path.name}): {e}", file=sys.stderr)
        raise  # Caller decides fallback; we ensure visibility

def get_session_state_path(session_id: str, agent_root: Optional[Path] = None) -> Path:
    """
    Get path to .maceff/sessions/{session_id}/session_state.json.

    Co-locates session state with agent state in .maceff hierarchy.
    Uses same environment-aware detection as agent state.

    Args:
        session_id: Session identifier
        agent_root: Agent root path (auto-detected if None)

    Returns:
        Path to session state file
    """
    # Test isolation check - highest priority
    if _TEST_STATE_ROOT is not None:
        agent_root = _TEST_STATE_ROOT
    elif agent_root is None:
        # Environment-aware detection (same logic as agent state)
        if Path("/.dockerenv").exists():
            # Container: Agent-scoped
            agent_root = Path.home()
        else:
            # Host: Project-scoped
            from .paths import find_project_root
            agent_root = find_project_root()
    else:
        agent_root = Path(agent_root)

    return agent_root / ".maceff" / "sessions" / session_id / "session_state.json"

def get_agent_state_path(agent_root: Optional[Path] = None) -> Path:
    """
    Get path to .maceff/agent_state.json with environment-aware resolution.

    Environment Detection:
        Container (/.dockerenv exists): /home/{agent}/.maceff/agent_state.json
            - Agent-scoped: Persists across multiple projects
        Host (no /.dockerenv): {project_root}/.maceff/agent_state.json
            - Project-scoped: Tied to specific project

    Args:
        agent_root: Agent root path (auto-detected if None)
            Explicit path overrides environment detection

    Returns:
        Path to agent state file
    """
    # Test isolation check - highest priority
    if _TEST_STATE_ROOT is not None:
        agent_root = _TEST_STATE_ROOT
    elif agent_root is None:
        # Environment-aware detection
        if Path("/.dockerenv").exists():
            # Container: Agent-scoped (multi-project agent)
            agent_root = Path.home()
        else:
            # Host: Project-scoped (single-project agent)
            from .paths import find_project_root
            agent_root = find_project_root()
    else:
        agent_root = Path(agent_root)

    return agent_root / ".maceff" / "agent_state.json"

# NOTE: SessionOperationalState DELETED in Phase 7 (Radical State API Purge)
# Events are the sole source of truth. See: event_queries.py
