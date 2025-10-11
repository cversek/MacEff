#!/usr/bin/env python3
"""
MACF Utilities - Battle-tested functions ported from legacy macf_utils.py.

Centralized utilities for:
- Project root discovery (multi-strategy)
- Session ID extraction from JSONL files
- Unified agent-scoped temp directories
- Safe JSON operations
- Timestamp formatting
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from macf import __version__

try:
    import dateutil.tz  # type: ignore
    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False


def find_project_root() -> Path:
    """Find project root using canonical implementation.

    Priority:
    1. $MACF_PROJECT_ROOT environment variable (if valid)
    2. $CLAUDE_PROJECT_DIR environment variable (if valid)
    3. Git repository root (if available)
    4. Discovery by looking for project markers from __file__
    5. Discovery by looking for project markers from cwd
    6. Current working directory as fallback
    """
    # First check if MACF_PROJECT_ROOT is set and valid
    macf_project_root = os.environ.get("MACF_PROJECT_ROOT")
    if macf_project_root:
        project_path = Path(macf_project_root)
        if project_path.exists() and project_path.is_dir():
            # Verify it's actually a project root by checking for markers
            if (project_path / "tools").exists():
                return project_path

    # Then check if CLAUDE_PROJECT_DIR is set and valid
    claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if claude_project_dir:
        project_path = Path(claude_project_dir)
        if project_path.exists() and project_path.is_dir():
            # Verify it's actually a project root by checking for markers
            markers = ["CLAUDE.md", "pyproject.toml", ".git", "tools"]
            if any((project_path / marker).exists() for marker in markers):
                return project_path

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
            if (git_root / "tools").exists() or (git_root / ".git").exists():
                return git_root
    except Exception:
        pass

    # Fall back to discovery method from __file__ location
    current = Path(__file__).resolve().parent

    # Look for project markers
    markers = ["CLAUDE.md", "pyproject.toml", ".git", "tools", "Makefile"]

    while current != current.parent:
        # Need at least 2 markers for confidence
        marker_count = sum((current / marker).exists() for marker in markers)
        if marker_count >= 2:
            return current
        current = current.parent

    # Try discovery from current working directory
    current = Path.cwd()
    while current != current.parent:
        marker_count = sum((current / marker).exists() for marker in markers)
        if marker_count >= 2:
            return current
        current = current.parent

    # Fallback to current working directory with warning
    print(
        f"WARNING: Could not find project root! Using cwd: {Path.cwd()}",
        file=sys.stderr,
    )
    return Path.cwd()


def get_formatted_timestamp() -> Tuple[str, datetime]:
    """Get formatted timestamp with day of week and timezone.

    Returns:
        Tuple of (formatted_string, datetime_object)
    """
    if DATEUTIL_AVAILABLE:
        eastern = dateutil.tz.gettz("America/New_York")
        now = datetime.now(tz=eastern)
    else:
        now = datetime.now(timezone.utc)

    formatted = now.strftime("%A, %b %d, %Y %I:%M:%S %p %Z")
    return formatted, now


def get_current_session_id() -> str:
    """Get current session ID from newest JSONL file.

    This is more reliable than environment after compaction,
    as it finds the actual current session file.

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
                    # User messages have top-level 'uuid' field, not message.id
                    return data.get('uuid')
            except json.JSONDecodeError:
                continue

    except Exception:
        pass

    return None


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
            from .config import ConsciousnessConfig
            config = ConsciousnessConfig()
            agent_id = config.agent_id
        except Exception:
            # Fallback if config unavailable
            agent_id = os.environ.get('MACEFF_USER') or os.environ.get('USER') or 'unknown_agent'

    # Build unified path: /tmp/macf/{agent_id}/{session_id}/{subdir}/
    base_path = Path("/tmp/macf") / agent_id / session_id

    if subdir:
        base_path = base_path / subdir

    if create:
        try:
            base_path.mkdir(parents=True, exist_ok=True, mode=0o755)
            return base_path
        except Exception:
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
            except:
                pass
        return False


def read_json_safely(path: Path) -> dict:
    """
    Safe JSON read with error handling.

    Args:
        path: Path to JSON file

    Returns:
        Dict contents or empty dict if error
    """
    try:
        if path.exists():
            with open(path, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


# =============================================================================
# Consciousness State Infrastructure
# =============================================================================


@dataclass
class SessionOperationalState:
    """
    Operational state that persists across compaction.

    Stored in: /tmp/macf/{agent_id}/{session_id}/session_state.json

    This dataclass holds session-level operational configuration and state
    that should survive context compaction events.
    """
    session_id: str
    agent_id: str
    auto_mode: bool = False
    auto_mode_source: str = "default"  # CLI, env, config, session, default
    auto_mode_confidence: float = 0.0  # 0.0-1.0
    pending_todos: List[dict] = field(default_factory=list)
    recovery_policy_path: Optional[str] = None
    compaction_count: int = 0
    started_at: float = field(default_factory=lambda: time.time())
    last_updated: float = field(default_factory=lambda: time.time())
    session_started_at: float = 0.0
    last_compaction_at: Optional[float] = None
    total_session_duration: float = 0.0

    # Development Drive (DEV_DRV) tracking
    current_dev_drv_started_at: Optional[float] = None
    current_dev_drv_prompt_uuid: Optional[str] = None
    dev_drv_count: int = 0
    total_dev_drv_duration: float = 0.0

    # Delegation Drive (DELEG_DRV) tracking
    current_deleg_drv_started_at: Optional[float] = None
    deleg_drv_count: int = 0
    total_deleg_drv_duration: float = 0.0

    # Cycle tracking (consciousness continuity unit)
    current_cycle_number: int = 1  # 1-based, increments on compaction
    cycle_started_at: float = field(default_factory=lambda: time.time())
    cycles_completed: int = 0  # Total cycles finished (equivalent to compaction_count)

    # Delegation tracking within DEV_DRV (Phase 1F)
    delegations_this_drive: List[Dict[str, Any]] = field(default_factory=list)

    def save(self) -> bool:
        """
        Atomically save state to session directory.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Update timestamp
            self.last_updated = time.time()

            # Get session directory
            session_dir = get_session_dir(
                session_id=self.session_id,
                agent_id=self.agent_id,
                create=True
            )

            if not session_dir:
                return False

            state_path = session_dir / "session_state.json"
            return write_json_safely(state_path, asdict(self))
        except Exception:
            return False

    @classmethod
    def load(cls, session_id: str, agent_id: Optional[str] = None) -> "SessionOperationalState":
        """
        Load state from session directory, returning default instance on failure.

        Args:
            session_id: Session identifier
            agent_id: Agent identifier (auto-detected if None)

        Returns:
            SessionOperationalState instance (never crashes)
        """
        try:
            # Auto-detect agent_id if needed
            if not agent_id:
                try:
                    from .config import ConsciousnessConfig
                    config = ConsciousnessConfig()
                    agent_id = config.agent_id
                except Exception:
                    agent_id = os.environ.get('MACEFF_USER') or os.environ.get('USER') or 'unknown_agent'

            # Get session directory (don't create if loading)
            session_dir = get_session_dir(
                session_id=session_id,
                agent_id=agent_id,
                create=False
            )

            if not session_dir:
                return cls(session_id=session_id, agent_id=agent_id)

            state_path = session_dir / "session_state.json"
            data = read_json_safely(state_path)

            if not data:
                return cls(session_id=session_id, agent_id=agent_id)

            # Restore from saved data
            return cls(**data)
        except Exception:
            # Always return valid instance, never crash
            return cls(session_id=session_id, agent_id=agent_id or "unknown_agent")


@dataclass
class ConsciousnessArtifacts:
    """
    Pythonic power object for discovered consciousness artifacts.

    Provides rich interface for working with reflections, checkpoints, and roadmaps
    instead of one-trick-pony functions.
    """
    reflections: List[Path] = field(default_factory=list)
    checkpoints: List[Path] = field(default_factory=list)
    roadmaps: List[Path] = field(default_factory=list)

    @property
    def latest_reflection(self) -> Optional[Path]:
        """Most recent reflection by mtime."""
        if not self.reflections:
            return None
        return max(self.reflections, key=lambda p: p.stat().st_mtime)

    @property
    def latest_checkpoint(self) -> Optional[Path]:
        """Most recent checkpoint by mtime."""
        if not self.checkpoints:
            return None
        return max(self.checkpoints, key=lambda p: p.stat().st_mtime)

    @property
    def latest_roadmap(self) -> Optional[Path]:
        """Most recent roadmap by mtime."""
        if not self.roadmaps:
            return None
        return max(self.roadmaps, key=lambda p: p.stat().st_mtime)

    def all_paths(self) -> List[Path]:
        """Flatten all artifacts into single list."""
        return self.reflections + self.checkpoints + self.roadmaps

    def __bool__(self) -> bool:
        """True if any artifacts exist."""
        return bool(self.reflections or self.checkpoints or self.roadmaps)


def get_latest_consciousness_artifacts(
    agent_root: Optional[Path] = None,
    limit: int = 5
) -> ConsciousnessArtifacts:
    """
    Discover consciousness artifacts with safe fallbacks.

    Args:
        agent_root: Agent directory (auto-detect via ConsciousnessConfig if None)
        limit: Max artifacts per category

    Returns:
        ConsciousnessArtifacts (empty lists on any failure - NEVER crash)
    """
    try:
        # Auto-detect agent_root if needed
        if agent_root is None:
            try:
                from .config import ConsciousnessConfig
                config = ConsciousnessConfig()
                agent_root = config.agent_root
            except Exception:
                return ConsciousnessArtifacts()

        # Ensure agent_root is a Path
        agent_root = Path(agent_root)

        if not agent_root.exists():
            return ConsciousnessArtifacts()

        public_dir = agent_root / "public"

        if not public_dir.exists():
            return ConsciousnessArtifacts()

        # Discover artifacts with safe empty list fallbacks
        reflections_dir = public_dir / "reflections"
        checkpoints_dir = public_dir / "checkpoints"
        roadmaps_dir = public_dir / "roadmaps"

        reflections = []
        if reflections_dir.exists():
            reflections = sorted(
                [p for p in reflections_dir.glob("*.md") if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:limit]

        checkpoints = []
        if checkpoints_dir.exists():
            checkpoints = sorted(
                [p for p in checkpoints_dir.glob("*.md") if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:limit]

        roadmaps = []
        if roadmaps_dir.exists():
            roadmaps = sorted(
                [p for p in roadmaps_dir.glob("*.md") if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:limit]

        return ConsciousnessArtifacts(
            reflections=reflections,
            checkpoints=checkpoints,
            roadmaps=roadmaps
        )
    except Exception:
        # NEVER crash - return empty artifacts
        return ConsciousnessArtifacts()


def detect_auto_mode(session_id: str) -> Tuple[bool, str, float]:
    """
    Hierarchical AUTO_MODE detection with confidence scoring.

    Priority (highest to lowest):
    1. CLI flag --auto-mode (not implemented yet, return None)
    2. Environment variable MACF_AUTO_MODE=true/false - confidence 0.9
    3. Config file .maceff/config.json "auto_mode" field - confidence 0.7
    4. Session state (load previous setting) - confidence 0.5
    5. Default (False, "default", 0.0)

    Args:
        session_id: Session identifier

    Returns:
        Tuple of (enabled: bool, source: str, confidence: float)
    """
    try:
        # 1. CLI flag (not implemented yet)
        # Future: Check sys.argv or click context

        # 2. Environment variable
        env_value = os.environ.get('MACF_AUTO_MODE', '').lower()
        if env_value in ('true', '1', 'yes'):
            return (True, "env", 0.9)
        elif env_value in ('false', '0', 'no'):
            return (False, "env", 0.9)

        # 3. Config file
        try:
            project_root = find_project_root()
            config_path = project_root / ".maceff" / "config.json"
            config_data = read_json_safely(config_path)

            if "auto_mode" in config_data:
                auto_mode = bool(config_data["auto_mode"])
                return (auto_mode, "config", 0.7)
        except Exception:
            pass

        # 4. Session state (previous setting)
        try:
            state = SessionOperationalState.load(session_id)
            if state.auto_mode_source != "default":
                # Only use session state if it was set explicitly before
                return (state.auto_mode, "session", 0.5)
        except Exception:
            pass

        # 5. Default
        return (False, "default", 0.0)
    except Exception:
        # NEVER crash
        return (False, "default", 0.0)


# =============================================================================
# Development Drive (DEV_DRV) Infrastructure
# =============================================================================


def start_dev_drv(session_id: str, agent_id: Optional[str] = None) -> bool:
    """
    Mark Development Drive start.

    DEV_DRV = period from user plan approval/UserPromptSubmit to Stop hook.

    Returns:
        True if successful, False otherwise
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)
    state.current_dev_drv_started_at = time.time()

    # Capture UUID of user prompt that started this drive
    uuid = get_last_user_prompt_uuid(session_id)
    state.current_dev_drv_prompt_uuid = uuid

    return state.save()


def complete_dev_drv(session_id: str, agent_id: Optional[str] = None) -> tuple[bool, float]:
    """
    Mark Development Drive completion and update stats.

    Returns:
        Tuple of (success: bool, duration_seconds: float)
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    if state.current_dev_drv_started_at is None:
        return (False, 0.0)

    # Calculate duration
    duration = time.time() - state.current_dev_drv_started_at

    # Update stats
    state.dev_drv_count += 1
    state.total_dev_drv_duration += duration

    # Clear current drive tracking
    state.current_dev_drv_started_at = None
    state.current_dev_drv_prompt_uuid = None

    success = state.save()
    return (success, duration)


def get_dev_drv_stats(session_id: str, agent_id: Optional[str] = None) -> dict:
    """
    Get current Development Drive statistics.

    Returns:
        Dict with keys: count, total_duration, current_started_at, avg_duration
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    avg_duration = 0.0
    if state.dev_drv_count > 0:
        avg_duration = state.total_dev_drv_duration / state.dev_drv_count

    return {
        "count": state.dev_drv_count,
        "total_duration": state.total_dev_drv_duration,
        "current_started_at": state.current_dev_drv_started_at,
        "prompt_uuid": state.current_dev_drv_prompt_uuid,
        "avg_duration": avg_duration
    }


# =============================================================================
# Delegation Drive (DELEG_DRV) Infrastructure
# =============================================================================


def start_deleg_drv(session_id: str, agent_id: Optional[str] = None) -> bool:
    """
    Mark Delegation Drive start.

    DELEG_DRV = period from Task tool invocation to SubagentStop hook.

    Returns:
        True if successful, False otherwise
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)
    state.current_deleg_drv_started_at = time.time()
    return state.save()


def complete_deleg_drv(session_id: str, agent_id: Optional[str] = None) -> tuple[bool, float]:
    """
    Mark Delegation Drive completion and update stats.

    Returns:
        Tuple of (success: bool, duration_seconds: float)
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    if state.current_deleg_drv_started_at is None:
        return (False, 0.0)

    # Calculate duration
    duration = time.time() - state.current_deleg_drv_started_at

    # Update stats
    state.deleg_drv_count += 1
    state.total_deleg_drv_duration += duration
    state.current_deleg_drv_started_at = None  # Clear current

    success = state.save()
    return (success, duration)


def get_deleg_drv_stats(session_id: str, agent_id: Optional[str] = None) -> dict:
    """
    Get current Delegation Drive statistics.

    Returns:
        Dict with keys: count, total_duration, current_started_at, avg_duration
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    avg_duration = 0.0
    if state.deleg_drv_count > 0:
        avg_duration = state.total_deleg_drv_duration / state.deleg_drv_count

    return {
        "count": state.deleg_drv_count,
        "total_duration": state.total_deleg_drv_duration,
        "current_started_at": state.current_deleg_drv_started_at,
        "avg_duration": avg_duration
    }


# =============================================================================
# Project State Infrastructure (Project-Scoped Cycle Persistence)
# =============================================================================


def get_project_state_path(agent_root: Optional[Path] = None) -> Path:
    """
    Get path to .maceff/project_state.json.

    Args:
        agent_root: Project root (auto-detected if None)

    Returns:
        Path to project state file
    """
    if agent_root is None:
        agent_root = find_project_root()
    else:
        agent_root = Path(agent_root)

    return agent_root / ".maceff" / "project_state.json"


def load_project_state(agent_root: Optional[Path] = None) -> dict:
    """
    Load project state from JSON file.

    Returns default dict if file doesn't exist (backward compat).
    Handle JSON errors gracefully.

    Args:
        agent_root: Project root (auto-detected if None)

    Returns:
        Project state dict or empty dict on error
    """
    try:
        state_path = get_project_state_path(agent_root)
        return read_json_safely(state_path)
    except Exception:
        return {}


def save_project_state(state: dict, agent_root: Optional[Path] = None) -> bool:
    """
    Save project state atomically (write-rename pattern).

    Create .maceff/ directory if needed.

    Args:
        state: Project state dict to save
        agent_root: Project root (auto-detected if None)

    Returns:
        True if successful, False otherwise
    """
    try:
        state_path = get_project_state_path(agent_root)

        # Create .maceff directory if needed
        state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)

        # Update timestamp
        state['last_updated'] = time.time()

        return write_json_safely(state_path, state)
    except Exception:
        return False


def get_current_cycle_project(agent_root: Optional[Path] = None) -> int:
    """
    Get cycle number from project state.

    Args:
        agent_root: Project root (auto-detected if None)

    Returns:
        Current cycle number (1 if project state doesn't exist)
    """
    try:
        project_state = load_project_state(agent_root)
        return project_state.get('current_cycle_number', 1)
    except Exception:
        return 1


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
        project_state = load_project_state(agent_root)

        if not project_state:
            # First run - no migration
            return (False, "")

        last_session_id = project_state.get('last_session_id', '')

        if not last_session_id:
            # No previous session recorded
            return (False, "")

        # Migration if session IDs differ
        is_migration = (last_session_id != current_session_id)
        return (is_migration, last_session_id)
    except Exception:
        return (False, "")


def increment_cycle_project(session_id: str, agent_root: Optional[Path] = None) -> int:
    """
    Increment project cycle number and update session tracking.

    Called by SessionStart hook when compaction detected.

    Args:
        session_id: Current session identifier
        agent_root: Project root (auto-detected if None)

    Returns:
        New cycle number
    """
    try:
        project_state = load_project_state(agent_root)

        # Initialize if empty
        if not project_state:
            project_state = {
                'current_cycle_number': 1,
                'cycle_started_at': time.time(),
                'cycles_completed': 0,
                'last_session_id': session_id
            }

        # Increment cycle
        project_state['current_cycle_number'] += 1
        project_state['cycle_started_at'] = time.time()
        project_state['cycles_completed'] = project_state['current_cycle_number'] - 1
        project_state['last_session_id'] = session_id

        # Save atomically
        save_project_state(project_state, agent_root)

        return project_state['current_cycle_number']
    except Exception:
        return 1


# =============================================================================
# Cycle Tracking Infrastructure
# =============================================================================


def start_new_cycle(session_id: str, agent_id: Optional[str] = None, state: Optional[SessionOperationalState] = None) -> int:
    """
    Initialize new cycle after compaction, increment counter.

    Cycle = compaction-to-compaction span (consciousness continuity unit).
    Called by SessionStart hook when compaction detected.

    Args:
        session_id: Session identifier
        agent_id: Optional agent ID (auto-detected if None)
        state: Optional pre-loaded state object (avoids race condition)

    Returns:
        New cycle number (1-based)
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    # Track whether state was provided or we need to load it
    state_was_provided = state is not None

    # Use provided state or load fresh (for backward compatibility)
    if not state_was_provided:
        state = SessionOperationalState.load(session_id, agent_id)

    # Increment cycle number
    state.current_cycle_number += 1

    # Reset cycle start time
    state.cycle_started_at = time.time()

    # Update cycles completed count
    state.cycles_completed = state.compaction_count

    # Reset cycle-scoped development stats
    # Philosophy: Each cycle is a consciousness continuity unit.
    # Stats measure current cycle work, not inherited totals from prior cycles.
    state.dev_drv_count = 0
    state.total_dev_drv_duration = 0.0
    state.deleg_drv_count = 0
    state.total_deleg_drv_duration = 0.0

    # Only save if we loaded fresh state (backward compatibility)
    # If state was provided by caller, they're responsible for saving
    if not state_was_provided:
        state.save()

    return state.current_cycle_number


def get_current_cycle_number(session_id: str, agent_id: Optional[str] = None) -> int:
    """
    Get current cycle number (1-based).

    Args:
        session_id: Session identifier
        agent_id: Optional agent ID (auto-detected if None)

    Returns:
        Current cycle number (1 if fresh start, >1 after compaction)
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)
    return state.current_cycle_number


def get_cycle_stats(session_id: str, agent_id: Optional[str] = None) -> dict:
    """
    Get cycle metadata for display.

    Args:
        session_id: Session identifier
        agent_id: Optional agent ID (auto-detected if None)

    Returns:
        Dict with: cycle_number, cycle_started_at, cycle_duration, cycles_completed
    """
    if agent_id is None:
        from macf.config import ConsciousnessConfig
        agent_id = ConsciousnessConfig().agent_id

    state = SessionOperationalState.load(session_id, agent_id)

    # Calculate cycle duration
    cycle_duration = 0.0
    if state.cycle_started_at > 0:
        cycle_duration = time.time() - state.cycle_started_at

    return {
        "cycle_number": state.current_cycle_number,
        "cycle_started_at": state.cycle_started_at,
        "cycle_duration": cycle_duration,
        "cycles_completed": state.cycles_completed
    }


# =============================================================================
# Temporal Awareness Infrastructure
# =============================================================================


def get_temporal_context() -> dict:
    """
    Master temporal context function.

    Returns comprehensive temporal information for consciousness injection.
    Uses standard library only, platform-native timezone detection.

    Returns:
        dict with keys:
            - timestamp_formatted: "Monday, Oct 02, 2025 08:42:11 PM EDT"
            - day_of_week: "Monday"
            - time_of_day: "Evening" (Morning/Afternoon/Evening/Late night)
            - hour: 20 (24-hour format)
            - timezone: "EDT"
            - iso_timestamp: "2025-10-02T20:42:11"
    """
    now = datetime.now()

    # Platform-native timezone detection
    timezone_str = time.tzname[time.daylight]

    # Time-of-day classification
    hour = now.hour
    if 5 <= hour < 12:
        time_of_day = "Morning"
    elif 12 <= hour < 17:
        time_of_day = "Afternoon"
    elif 17 <= hour < 21:
        time_of_day = "Evening"
    else:
        time_of_day = "Late night / Early morning"

    # Formatted timestamp
    timestamp_formatted = now.strftime(f"%A, %b %d, %Y %I:%M:%S %p {timezone_str}")

    return {
        "timestamp_formatted": timestamp_formatted,
        "day_of_week": now.strftime("%A"),
        "time_of_day": time_of_day,
        "hour": hour,
        "timezone": timezone_str,
        "iso_timestamp": now.strftime("%Y-%m-%dT%H:%M:%S")
    }


def format_duration(seconds: float) -> str:
    """
    Format duration from seconds to human-readable string.

    Universal DRY utility for duration formatting across all hooks.

    Args:
        seconds: Duration in seconds (float or int)

    Returns:
        Human-readable string like "45s", "5m", "2h 15m", "1d 3h", "2d"
    """
    # Convert to int for cleaner display
    total_seconds = int(seconds)

    # Handle edge cases
    if total_seconds < 0:
        return "0s"

    # Less than 60s: show seconds
    if total_seconds < 60:
        return f"{total_seconds}s"

    # Less than 60m: show minutes only
    total_minutes = total_seconds // 60
    if total_minutes < 60:
        return f"{total_minutes}m"

    # Less than 24h: show hours and minutes
    total_hours = total_minutes // 60
    remaining_minutes = total_minutes % 60

    if total_hours < 24:
        if remaining_minutes > 0:
            return f"{total_hours}h {remaining_minutes}m"
        else:
            return f"{total_hours}h"

    # 24h or more: show days and hours
    days = total_hours // 24
    remaining_hours = total_hours % 24

    if remaining_hours > 0:
        return f"{days}d {remaining_hours}h"
    else:
        return f"{days}d"


def calculate_session_duration(started_at: float, ended_at: Optional[float] = None) -> str:
    """
    Calculate human-readable session duration.

    Args:
        started_at: Unix timestamp when session started
        ended_at: Unix timestamp when session ended (default: now)

    Returns:
        Human-readable string like "3h 24m" or "45m" or "12s" or "Fresh start"
    """
    # Handle fresh start cases
    if started_at == 0 or started_at is None:
        return "Fresh start"

    # Use current time if ended_at not provided
    if ended_at is None:
        ended_at = time.time()

    # Calculate duration in seconds
    duration_seconds = int(ended_at - started_at)

    # Handle negative durations (clock skew or invalid timestamps)
    if duration_seconds < 0:
        return "Fresh start"

    # Use shared format_duration utility
    return format_duration(duration_seconds)


def detect_execution_environment() -> str:
    """
    Detect where MACF tools are running.

    Returns:
        One of:
        - "MacEff Container (username)" - if /.dockerenv exists
        - "MacEff Host System" - if project has MacEff markers
        - "Host System" - generic host
    """
    # Check for container environment
    if Path("/.dockerenv").exists():
        # Read username from environment
        username = os.environ.get("MACEFF_USER") or os.environ.get("USER") or "unknown"
        return f"MacEff Container ({username})"

    # Check if running in MacEff project on host
    cwd = Path.cwd()
    current = cwd

    # Walk up directory tree looking for MacEff markers
    while current != current.parent:
        if "MacEff" in current.name:
            return "MacEff Host System"
        current = current.parent

    # Generic host fallback
    return "Host System"


def format_temporal_awareness_section(
    temporal_ctx: dict,
    session_duration: Optional[str] = None
) -> str:
    """
    Format temporal awareness section for SessionStart messages.

    Args:
        temporal_ctx: Dict from get_temporal_context()
        session_duration: Optional duration string from calculate_session_duration()

    Returns:
        Formatted string like:
        ```
        ⏰ TEMPORAL AWARENESS
        Current Time: Monday, Oct 02, 2025 08:42:11 PM EDT
        Day: Monday
        Time of Day: Evening
        Session Duration: 3h 24m
        ```
    """
    lines = [
        "⏰ TEMPORAL AWARENESS",
        f"Current Time: {temporal_ctx['timestamp_formatted']}",
        f"Day: {temporal_ctx['day_of_week']}",
        f"Time of Day: {temporal_ctx['time_of_day']}"
    ]

    if session_duration:
        lines.append(f"Session Duration: {session_duration}")

    return "\n".join(lines)


def get_minimal_timestamp() -> str:
    """
    Get minimal timestamp for high-frequency hooks.

    Returns:
        Minimal timestamp like "03:22:45 PM"
    """
    now = datetime.now()
    return now.strftime("%I:%M:%S %p")


def format_minimal_temporal_message(timestamp: str) -> str:
    """
    Format lightweight temporal message for high-frequency hooks.

    Args:
        timestamp: From get_minimal_timestamp()

    Returns:
        Formatted message with 🏗️ MACF tag
    """
    return f"🏗️ MACF | {timestamp}"


def format_macf_footer(environment: str) -> str:
    """
    Standard MACF attribution footer with shortened tag.

    Uses __version__ from macf package (single source of truth).

    Args:
        environment: From detect_execution_environment()

    Returns:
        ```
        ---
        🏗️ MACF Tools {__version__} (Multi-Agent Coordination Framework)
        Environment: {environment}
        ```
    """
    return f"""---
🏗️ MACF Tools {__version__} (Multi-Agent Coordination Framework)
Environment: {environment}"""


# ============================================================================
# Delegation Tracking (Phase 1F)
# ============================================================================

def record_delegation_start(
    session_id: str,
    tool_use_uuid: str,
    subagent_type: str,
    agent_id: Optional[str] = None
) -> bool:
    """
    Record delegation start in session state.

    Args:
        session_id: Session identifier
        tool_use_uuid: Task tool_use_id for JSONL sidechain lookup
        subagent_type: Type of subagent (e.g., "devops-eng", "test-eng")
        agent_id: Agent identifier (auto-detected if None)

    Returns:
        True if recorded successfully, False otherwise
    """
    try:
        state = SessionOperationalState.load(session_id, agent_id)

        delegation = {
            "tool_use_uuid": tool_use_uuid,
            "subagent_type": subagent_type,
            "started_at": time.time(),
            "completed_at": None,
            "duration": None
        }

        state.delegations_this_drive.append(delegation)
        return state.save()
    except Exception:
        return False


def record_delegation_complete(
    session_id: str,
    tool_use_uuid: str,
    duration: float,
    agent_id: Optional[str] = None
) -> bool:
    """
    Mark delegation as complete with duration.

    Args:
        session_id: Session identifier
        tool_use_uuid: Task tool_use_id to match
        duration: Duration in seconds
        agent_id: Agent identifier (auto-detected if None)

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        state = SessionOperationalState.load(session_id, agent_id)

        # Find matching delegation by UUID
        for deleg in state.delegations_this_drive:
            if deleg['tool_use_uuid'] == tool_use_uuid:
                deleg['completed_at'] = time.time()
                deleg['duration'] = duration
                return state.save()

        # UUID not found - still return True (safe failure)
        return True
    except Exception:
        return False


def get_delegations_this_drive(
    session_id: str,
    agent_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all delegations for current DEV_DRV.

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (auto-detected if None)

    Returns:
        List of delegation dicts (empty list on failure)
    """
    try:
        state = SessionOperationalState.load(session_id, agent_id)
        return state.delegations_this_drive
    except Exception:
        return []


def clear_delegations_this_drive(
    session_id: str,
    agent_id: Optional[str] = None
) -> bool:
    """
    Clear delegation list (called after DEV_DRV Complete reporting).

    Args:
        session_id: Session identifier
        agent_id: Agent identifier (auto-detected if None)

    Returns:
        True if cleared successfully, False otherwise
    """
    try:
        state = SessionOperationalState.load(session_id, agent_id)
        state.delegations_this_drive = []
        return state.save()
    except Exception:
        return False


# =============================================================================
# Token Tracking Infrastructure (Battle-Tested from Legacy MACF)
# =============================================================================


def get_token_info(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Get current token usage information from session JSONL or hooks state.

    Uses a smart caching strategy for performance:
    1. Check sidecar cache first (ultra-fast)
    2. Quick scan last 200KB of JSONL
    3. Full scan only if needed

    Args:
        session_id: Optional session ID to get tokens for specific session.
                   If not provided, uses current session.

    Returns:
        Dictionary with token counts and CLUAC level
    """
    # Claude Code 2.0 transparent accounting: 200k total context
    # (155k usable + 45k autocompact buffer reserve)
    # This matches /context display which shows total including reserves
    max_tokens = 200000

    # If session_id provided, try to get tokens from JSONL file
    if session_id or (session_id := get_current_session_id()) != "unknown":
        # Smart cache invalidation strategy:
        # 1. Check cache for historical reference
        # 2. ALWAYS do a quick tail scan to get current value
        # 3. If current < cached, update cache (detects compaction)

        # Read cache from unified sidecar location
        sidecar_dir = get_session_dir(session_id, agent_id=None, subdir=None, create=False)
        cache_data = None
        cached_max = 0

        if sidecar_dir:
            cache_path = sidecar_dir / "token_cache.json"
            cache_data = read_json_safely(cache_path)
            if cache_data and cache_data.get("session_id") == session_id:
                cached_max = cache_data.get("max_tokens_used", 0)

        jsonl_path = get_session_transcript_path(session_id)

        if jsonl_path and Path(jsonl_path).exists():
            try:
                # Smart cache invalidation with real-time accuracy
                # ALWAYS scan tail to get CURRENT token value, not historical maximum
                current_tokens = 0
                last_timestamp = None

                with open(jsonl_path, "rb") as f:
                    file_size = f.seek(0, os.SEEK_END)

                    # Quick scan: Read last 200KB for most recent token value
                    # We scan MORE data (200KB vs 100KB) to ensure we find the
                    # latest assistant message
                    scan_size = min(200 * 1024, file_size)
                    if scan_size > 0:
                        f.seek(-scan_size, os.SEEK_END)
                        content = f.read().decode("utf-8", errors="ignore")

                        # Find the LAST assistant message with token data (most recent)
                        assistant_messages = []
                        for line in content.split("\n"):
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                                if data.get("type") == "assistant":
                                    message = data.get("message", {})
                                    usage = message.get("usage", {})
                                    # Match TM! algorithm: sum ALL token types for total context
                                    total_tokens = 0
                                    total_tokens += usage.get(
                                        "cache_read_input_tokens", 0
                                    )
                                    total_tokens += usage.get(
                                        "cache_creation_input_tokens", 0
                                    )
                                    total_tokens += usage.get("input_tokens", 0)
                                    if total_tokens > 0:
                                        assistant_messages.append(
                                            {
                                                "tokens": total_tokens,
                                                "timestamp": data.get(
                                                    "timestamp", "unknown"
                                                ),
                                            }
                                        )
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue

                        # Use the LAST (most recent) assistant message's token count
                        if assistant_messages:
                            current_tokens = assistant_messages[-1]["tokens"]
                            last_timestamp = assistant_messages[-1]["timestamp"]

                    # If tail scan didn't find any data, do a full scan
                    if current_tokens == 0:
                        f.seek(0)
                        last_assistant_tokens = 0
                        for line in f:
                            try:
                                line = line.decode("utf-8", errors="ignore").strip()
                                if not line:
                                    continue
                                data = json.loads(line)
                                if data.get("type") == "assistant":
                                    message = data.get("message", {})
                                    usage = message.get("usage", {})
                                    # Match TM! algorithm: sum ALL token types for total context
                                    total_tokens = 0
                                    total_tokens += usage.get(
                                        "cache_read_input_tokens", 0
                                    )
                                    total_tokens += usage.get(
                                        "cache_creation_input_tokens", 0
                                    )
                                    total_tokens += usage.get("input_tokens", 0)
                                    if total_tokens > 0:
                                        # Always use the LATEST value, not the maximum
                                        last_assistant_tokens = total_tokens
                                        last_timestamp = data.get(
                                            "timestamp", "unknown"
                                        )
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue
                        current_tokens = last_assistant_tokens

                if current_tokens > 0:
                    tokens_remaining = max_tokens - current_tokens
                    # CLUAC is percentage REMAINING (not used)
                    # This matches the original CLUAC protocol where higher numbers = more danger
                    percentage_remaining = (
                        (tokens_remaining / max_tokens) * 100 if max_tokens > 0 else 0
                    )
                    # CLUAC level = percentage remaining (rounded)
                    # CLUAC100 = 100% remaining (0% used)
                    # CLUAC1 = 1% remaining (99% used)
                    cluac_level = round(percentage_remaining)

                    # Smart cache update: detect compaction events
                    # If current is significantly less than cached (>1k difference), update cache
                    # This automatically detects compaction resets
                    # FIXED: Lowered threshold from 10,000 to 1,000 for better cache accuracy
                    if sidecar_dir and (cached_max == 0 or abs(current_tokens - cached_max) > 1000):
                        cache_path = sidecar_dir / "token_cache.json"
                        write_json_safely(
                            cache_path,
                            {
                                "session_id": session_id,
                                "max_tokens_used": current_tokens,
                                "last_updated": last_timestamp,
                            },
                        )

                    return {
                        "tokens_used": current_tokens,
                        "tokens_remaining": tokens_remaining,
                        "percentage_used": (current_tokens / max_tokens) * 100,
                        "percentage_remaining": percentage_remaining,
                        "cluac_level": cluac_level,
                        "last_updated": last_timestamp,
                        "source": "jsonl",
                    }
            except Exception:
                # Fall through to hooks_state fallback
                pass

    # Fallback to hooks_state.json (original implementation)
    project_root = find_project_root()
    hooks_state_path = project_root / ".claude" / "hooks" / "hooks_state.json"

    if not hooks_state_path.exists():
        return {
            "tokens_used": 0,
            "tokens_remaining": max_tokens,
            "percentage_used": 0.0,
            "percentage_remaining": 100.0,
            "cluac_level": 0,
            "source": "default",
        }

    try:
        with open(hooks_state_path, "r") as f:
            state = json.load(f)

        token_data = state.get("token_tracking", {})
        tokens_used = token_data.get("total_tokens", 0)
        tokens_remaining = max_tokens - tokens_used
        percentage_used = (tokens_used / max_tokens) * 100 if max_tokens > 0 else 0
        percentage_remaining = 100 - percentage_used

        # Calculate CLUAC level (based on percentage remaining)
        # CLUAC level = percentage remaining (rounded)
        # CLUAC100 = 100% remaining (0% used)
        # CLUAC1 = 1% remaining (99% used)
        cluac_level = round(percentage_remaining)

        return {
            "tokens_used": tokens_used,
            "tokens_remaining": tokens_remaining,
            "percentage_used": percentage_used,
            "percentage_remaining": percentage_remaining,
            "cluac_level": cluac_level,
            "last_updated": token_data.get("last_updated", "unknown"),
            "source": "hooks_state",
        }
    except (json.JSONDecodeError, IOError, KeyError):
        return {
            "tokens_used": 0,
            "tokens_remaining": max_tokens,
            "percentage_used": 0.0,
            "percentage_remaining": 100.0,
            "cluac_level": 0,
            "source": "default",
        }