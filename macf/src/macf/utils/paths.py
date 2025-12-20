"""
Paths utilities.
"""

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=1)
def find_project_root() -> Path:
    """Find MacEff framework root using canonical implementation.

    Priority:
    1. $MACEFF_ROOT_DIR environment variable (preferred for containers)
    2. $CLAUDE_PROJECT_DIR environment variable (if valid)
    3. Git repository root (if available)
    4. Discovery by looking for project markers from __file__
    5. Discovery by looking for project markers from cwd
    6. Current working directory as fallback

    Result is cached - warnings only appear once per process.
    """
    fallback_reasons = []

    # First check MACEFF_ROOT_DIR (preferred for container environments)
    maceff_root = os.environ.get("MACEFF_ROOT_DIR")
    if maceff_root:
        root_path = Path(maceff_root)
        if root_path.exists() and root_path.is_dir():
            # Verify by checking for framework/ subdirectory
            if (root_path / "framework").exists():
                return root_path
            fallback_reasons.append(f"MACEFF_ROOT_DIR={maceff_root} missing framework/")
        else:
            fallback_reasons.append(f"MACEFF_ROOT_DIR={maceff_root} does not exist")

    # Then check CLAUDE_PROJECT_DIR
    claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if claude_project_dir:
        project_path = Path(claude_project_dir)
        if project_path.exists() and project_path.is_dir():
            markers = ["CLAUDE.md", "pyproject.toml", ".git", "framework"]
            if any((project_path / marker).exists() for marker in markers):
                return project_path
            fallback_reasons.append(f"CLAUDE_PROJECT_DIR={claude_project_dir} has no markers")

    # Try git repository root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=1,
            cwd=Path.cwd(),
        )
        if result.returncode == 0:
            git_root = Path(result.stdout.strip())
            if (git_root / ".git").exists() or (git_root / "framework").exists():
                return git_root
            fallback_reasons.append(f"git root {git_root} missing .git or framework/")
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        fallback_reasons.append("git not available or not in repo")

    # Fall back to discovery method from __file__ location
    markers = ["CLAUDE.md", "pyproject.toml", ".git", "framework", "Makefile"]
    current = Path(__file__).resolve().parent

    while current != current.parent:
        marker_count = sum((current / marker).exists() for marker in markers)
        if marker_count >= 2:
            return current
        current = current.parent
    fallback_reasons.append("no markers found walking up from __file__")

    # Try discovery from current working directory
    current = Path.cwd()
    while current != current.parent:
        marker_count = sum((current / marker).exists() for marker in markers)
        if marker_count >= 2:
            return current
        current = current.parent
    fallback_reasons.append("no markers found walking up from cwd")

    # Fallback with specific warning (only shown once due to caching)
    print(
        f"⚠️ MACF: Using cwd fallback: {Path.cwd()}\n"
        f"   Reasons: {'; '.join(fallback_reasons)}\n"
        f"   Fix: Set MACEFF_ROOT_DIR to MacEff framework location",
        file=sys.stderr,
    )
    return Path.cwd()

def get_session_dir(
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    subdir: Optional[str] = None,
    create: bool = True
) -> Optional[Path]:
    """
    Get agent-scoped session directory with optional subdirectory.

    Path structure: /tmp/macf/{agent_id}/{session_id}/{subdir}/

    Args:
        session_id: Session ID (auto-detected if None)
        agent_id: Agent ID (auto-detected using ConsciousnessConfig if None)
        subdir: Optional subdirectory ("hooks", "dev_scripts", "logs")
        create: Create directory if doesn't exist

    Returns:
        Path or None if creation fails and create=False
    """
    # Auto-detect session_id
    if not session_id:
        session_id = get_current_session_id()

    if session_id == "unknown":
        return None

    # Auto-detect agent_id using ConsciousnessConfig
    if not agent_id:
        try:
            from ..config import ConsciousnessConfig
            config = ConsciousnessConfig()
            agent_id = config.agent_id
        except (ImportError, OSError, KeyError) as e:
            # Fallback if config unavailable
            print(f"⚠️ MACF: Config load failed (using env fallback): {e}", file=sys.stderr)
            agent_id = os.environ.get('MACEFF_USER') or os.environ.get('USER') or 'unknown_agent'

    # Build unified path: /tmp/macf/{agent_id}/{session_id}/{subdir}/
    base_path = Path("/tmp/macf") / agent_id / session_id

    if subdir:
        base_path = base_path / subdir

    if create:
        try:
            base_path.mkdir(parents=True, exist_ok=True, mode=0o755)
            return base_path
        except OSError as e:
            print(f"⚠️ MACF: Session dir creation failed: {e}", file=sys.stderr)
            return None
    else:
        return base_path if base_path.exists() else None

def get_hooks_dir(session_id: Optional[str] = None, create: bool = True) -> Optional[Path]:
    """Get hooks subdirectory: /tmp/macf/{agent_id}/{session_id}/hooks/"""
    return get_session_dir(session_id=session_id, subdir="hooks", create=create)

def get_dev_scripts_dir(session_id: Optional[str] = None, create: bool = True) -> Optional[Path]:
    """Get dev_scripts subdirectory: /tmp/macf/{agent_id}/{session_id}/dev_scripts/"""
    return get_session_dir(session_id=session_id, subdir="dev_scripts", create=create)

def get_logs_dir(session_id: Optional[str] = None, create: bool = True) -> Optional[Path]:
    """Get logs subdirectory: /tmp/macf/{agent_id}/{session_id}/logs/"""
    return get_session_dir(session_id=session_id, subdir="logs", create=create)

def get_session_transcript_path(session_id: str) -> Optional[str]:
    """Get path to session JSONL file given session ID.

    Args:
        session_id: Session identifier

    Returns:
        Path string to JSONL file or None if not found
    """
    if session_id == "unknown":
        return None

    projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.exists():
        return None

    # Find project directory using current working directory name
    project_name = find_project_root().name

    # Try exact match first
    for project_dir in projects_dir.glob(f"*{project_name}*"):
        potential_file = project_dir / f"{session_id}.jsonl"
        if potential_file.exists():
            return str(potential_file)

    # Fallback: search all project directories
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            potential_file = project_dir / f"{session_id}.jsonl"
            if potential_file.exists():
                return str(potential_file)

    return None
