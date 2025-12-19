"""
State utilities.

NOTE: Mutable state APIs have been removed. Use event_queries.py functions.
Events (JSONL) are the sole source of truth.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from .paths import get_session_dir

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

# NOTE: State file path helpers DELETED - events are the sole source of truth.
# Removed: get_agent_state_path(), get_session_state_path(), set_state_root()
# See: event_queries.py for all state access
