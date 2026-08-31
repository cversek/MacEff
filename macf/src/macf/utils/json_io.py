"""
State utilities.

NOTE: Mutable state APIs have been removed. Use event_queries.py functions.
Events (JSONL) are the sole source of truth.
"""

import json
import os
import stat
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from .paths import get_session_dir

def write_json_safely(path: Path, data: dict) -> bool:
    """Replace *path* with *data* as JSON, atomically, preserving its mode.

    A reader either sees the whole previous file or the whole new one, never a
    truncated write in progress. That property is what lets a supervisor read a
    heartbeat, or a broker read an authorization file, while the writer is
    running -- without it a torn read is indistinguishable from a corrupt file,
    and the safe interpretation of a corrupt authorization file is to refuse
    every request.

    Three things this does that the obvious version does not:

    * **The temp name is unique**, not derived from the target. A shared
      predictable name means two writers of the same path truncate each other's
      temp file and the rename publishes the wreckage -- reintroducing the tear
      the temp file exists to prevent.
    * **The mode is carried over.** ``os.replace`` installs the temp file's
      permissions, so a helper that creates its temp at the default umask
      SILENTLY WIDENS every file it rewrites. In this codebase 0600 files
      decide who may read a credential and 0644-vs-0600 is load-bearing, so a
      rewrite that quietly publishes one is a security regression with no
      symptom.
    * **The bytes are flushed before the rename.** ``os.replace`` orders the
      rename, not the data behind it; without the fsync a crash can leave the
      new name pointing at an empty file. Atomic and durable are different
      claims and the docstring used to make only one of them while saying both.

    Returns True on success, False on any failure, having removed the temp.
    """
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Same directory as the target: os.replace is only atomic within one
        # filesystem, and /tmp is frequently a different one.
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent),
                                        prefix=f".{path.name}.", suffix=".tmp")
        tmp = Path(tmp_name)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        except FileNotFoundError:
            # First write of a new file: no prior mode to carry, so the
            # caller's umask decides. Deliberate, and distinguished from a
            # failed stat on an existing file, which is a real error.
            pass
        os.replace(tmp, path)
        return True
    except (OSError, IOError, TypeError, ValueError) as e:
        print(f"⚠️ MACF: JSON write failed for {path}: {e}", file=sys.stderr)
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError as e2:
                print(f"⚠️ MACF: Temp file cleanup failed: {e2}", file=sys.stderr)
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
