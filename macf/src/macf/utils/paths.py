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
def find_maceff_root() -> Path:
    """Find MacEff installation root.

    Priority:
    1. MACEFF_ROOT_DIR env var (explicit configuration)
    2. Git root with framework/ subdirectory (development checkout)
    3. Discovery via framework/ marker from __file__
    4. Current working directory as fallback

    This is where MacEff repo is checked out (host) or installed (container).
    The framework/ subdirectory contains policies and templates.

    Result is cached - warnings only appear once per process.
    """
    fallback_reasons = []

    # 1. Check MACEFF_ROOT_DIR (preferred for container environments)
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

    # 2. Try git repository root with framework/ marker
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
            if (git_root / "framework").exists():
                return git_root
            fallback_reasons.append(f"git root {git_root} missing framework/")
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        fallback_reasons.append("git not available or not in repo")

    # 3. Discovery by walking up from __file__ looking for framework/
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "framework").exists():
            return current
        current = current.parent
    fallback_reasons.append("no framework/ found walking up from __file__")

    # 4. Fallback with warning
    print(
        f"⚠️ MACF: MacEff root not found, using cwd fallback: {Path.cwd()}\n"
        f"   Reasons: {'; '.join(fallback_reasons)}\n"
        f"   Fix: Set MACEFF_ROOT_DIR to MacEff installation location",
        file=sys.stderr,
    )
    return Path.cwd()


@lru_cache(maxsize=1)
def find_project_root() -> Path:
    """Find user's project/workspace root.

    Priority:
    1. CLAUDE_PROJECT_DIR env var (set by Claude Code)
    2. Git root with .claude/ or CLAUDE.md marker
    3. Current working directory

    This is where `claude` was launched - the user's workspace.
    Contains project-specific CLAUDE.md and .claude/ configuration.

    Result is cached - warnings only appear once per process.
    """
    # 1. Check CLAUDE_PROJECT_DIR (set by Claude Code)
    claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if claude_project_dir:
        project_path = Path(claude_project_dir)
        if project_path.exists() and project_path.is_dir():
            return project_path

    # 2. Try git repository root with Claude markers
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
            # Check for Claude project markers
            if (git_root / ".claude").exists() or (git_root / "CLAUDE.md").exists():
                return git_root
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        pass

    # 3. Fallback to current working directory
    return Path.cwd()


@lru_cache(maxsize=1)
def find_agent_home() -> Path:
    """Find agent's persistent home directory root.

    Priority:
    1. MACEFF_AGENT_HOME_DIR env var (explicit configuration)
    2. ~ (user home directory, default)

    Directory structure under agent_home:
    - {agent_home}/.maceff/config.json - agent configuration
    - {agent_home}/.maceff/agent_events_log.jsonl - event log
    - {agent_home}/agent/ - consciousness artifacts (CAs)

    This is SACRED - agent continuity persists across project reassignments.

    Result is cached.
    """
    # 1. Check MACEFF_AGENT_HOME_DIR
    agent_home = os.environ.get("MACEFF_AGENT_HOME_DIR")
    if agent_home:
        home_path = Path(agent_home)
        if home_path.exists() and home_path.is_dir():
            return home_path
        # Create if doesn't exist but env var is set
        try:
            home_path.mkdir(parents=True, exist_ok=True, mode=0o755)
            return home_path
        except OSError:
            pass  # Fall through to default

    # 2. Default to user home directory
    return Path.home()

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
