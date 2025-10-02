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