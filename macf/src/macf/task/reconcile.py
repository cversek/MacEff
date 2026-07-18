"""Reconcile forked CC per-session task DBs into the project-scoped home store.

Claude Code stores tasks at ~/.claude/tasks/{session_uuid}/ and copies the whole
set into a new directory whenever a session forks (continue / rewind / child).
The copies then diverge. This merges every project-scoped session directory into
the configured home store using newest-mtime-per-id, so no task that was ever
worked on is dropped. Completed tasks keep their status (it lives in the JSON);
everything lands as plain {id}.json.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Any

from .reader import TaskReader
from ..utils.paths import find_project_root, encode_cc_project_path


def _project_session_dirs() -> List[Path]:
    """CC task directories whose UUID has a transcript JSONL for this project."""
    tasks_root = Path.home() / ".claude" / "tasks"
    if not tasks_root.exists():
        return []
    encoded = encode_cc_project_path(str(find_project_root()))
    projects_dir = Path.home() / ".claude" / "projects" / encoded
    project_uuids = {f.stem for f in projects_dir.glob("*.jsonl")} if projects_dir.exists() else set()
    dirs = [d for d in tasks_root.iterdir()
            if d.is_dir() and d.name in project_uuids and any(d.glob("*.json"))]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs


def reconcile(apply: bool = False, dest: Optional[Path] = None) -> Dict[str, Any]:
    """Union-merge project session task DBs into the home store.

    Args:
        apply: when False (default), report only; when True, write the merged files.
        dest: override destination store; defaults to the configured home store.

    Returns:
        A report dict: sources, merged id->(status, source_uuid), missing-status ids,
        destination, and whether it was applied.
    """
    if dest is None:
        dest = TaskReader._resolve_home_store()
    if dest is None:
        raise RuntimeError(
            "No home store configured. Set task_store.mode=home in "
            "{agent_home}/.maceff/config.json or MACF_TASK_STORE_DIR."
        )

    sources = _project_session_dirs()

    # id -> (mtime, path), scanning visible and CC-hidden files
    best: Dict[str, Any] = {}
    for d in sources:
        for f in list(d.glob("*.json")) + list(d.glob(".*.json")):
            tid = f.stem.lstrip(".")
            m = f.stat().st_mtime
            if tid not in best or m > best[tid][0]:
                best[tid] = (m, f)

    merged = {}
    missing_status = []
    for tid, (_m, f) in best.items():
        try:
            data = json.loads(f.read_text())
            status = data.get("status", "")
        except (OSError, ValueError):
            status = ""
        merged[tid] = (status, f.parent.name)
        if not status:
            missing_status.append(tid)

    report = {
        "sources": [d.name for d in sources],
        "merged_count": len(best),
        "missing_status": sorted(missing_status),
        "dest": str(dest),
        "applied": False,
    }

    if not apply:
        return report

    dest.mkdir(parents=True, exist_ok=True)
    os.chmod(dest, 0o755)  # tolerate a prior chmod 555 dir protection
    for tid, (_m, f) in best.items():
        target = dest / f"{tid}.json"
        # Task files may be read-only (copied from CC's protected dirs); make the
        # target writable before overwriting so a re-reconcile doesn't fail midway.
        if target.exists():
            os.chmod(target, 0o644)
        shutil.copy2(f, target)
        os.chmod(target, 0o644)
    report["applied"] = True
    return report
