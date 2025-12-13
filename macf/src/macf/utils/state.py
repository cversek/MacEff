"""
State utilities.

DEPRECATION NOTICE (Phase 6 - Mutable State Deprecation):
State file writes are deprecated in favor of append-only JSONL event sourcing.
- Reads: Use event_queries.py functions (event-first with state fallback)
- Writes: Will be removed in Phase 7; events are the source of truth
See: agent/public/roadmaps/2025-12-02_DETOUR_Mutable_State_Deprecation/roadmap.md
"""

import json
import os
import time
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from .paths import get_session_dir

# Deprecation flag - set to True to emit warnings on state writes
_DEPRECATION_WARNINGS_ENABLED = True

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
                import sys
                print(f"⚠️ MACF: Temp file cleanup failed: {e}", file=sys.stderr)
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
    except (OSError, json.JSONDecodeError) as e:
        import sys
        print(f"⚠️ MACF: JSON read failed ({path.name}): {e}", file=sys.stderr)
    return {}

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
    if agent_root is None:
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
    if agent_root is None:
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

def load_agent_state(agent_root: Optional[Path] = None) -> dict:
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
        state_path = get_agent_state_path(agent_root)
        return read_json_safely(state_path)
    except Exception:
        return {}

def save_agent_state(state: dict, agent_root: Optional[Path] = None) -> bool:
    """
    Save project state atomically (write-rename pattern).

    DEPRECATED: State file writes are deprecated. Events are now the source of truth.
    This function will be removed in Phase 7. Use emit_event() instead.

    Create .maceff/ directory if needed.

    Args:
        state: Project state dict to save
        agent_root: Project root (auto-detected if None)

    Returns:
        True if successful, False otherwise
    """
    if _DEPRECATION_WARNINGS_ENABLED:
        warnings.warn(
            "save_agent_state() is deprecated. Events are now the source of truth. "
            "This function will be removed in Phase 7.",
            DeprecationWarning,
            stacklevel=2
        )
    try:
        state_path = get_agent_state_path(agent_root)

        # Create .maceff directory if needed
        state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)

        # Update timestamp
        state['last_updated'] = time.time()

        return write_json_safely(state_path, state)
    except Exception:
        return False

@dataclass
class SessionOperationalState:
    """
    Operational state that persists across compaction.

    Stored in: .maceff/sessions/{session_id}/session_state.json
        Container: /home/{agent}/.maceff/sessions/{session_id}/session_state.json
        Host: {project_root}/.maceff/sessions/{session_id}/session_state.json

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

    # Delegation tracking within DEV_DRV (Phase 1F)
    delegations_this_drive: List[Dict[str, Any]] = field(default_factory=list)

    def save(self) -> bool:
        """
        Atomically save state to .maceff/sessions/{session_id}/ directory.

        DEPRECATED: State file writes are deprecated. Events are now the source of truth.
        This method will be removed in Phase 7. Use emit_event() instead.

        Returns:
            True if successful, False otherwise
        """
        if _DEPRECATION_WARNINGS_ENABLED:
            warnings.warn(
                "SessionOperationalState.save() is deprecated. Events are the source of truth. "
                "This method will be removed in Phase 7.",
                DeprecationWarning,
                stacklevel=2
            )
        try:
            # Update timestamp
            self.last_updated = time.time()

            # Get session state path (environment-aware)
            state_path = get_session_state_path(self.session_id)

            # Create directory if needed
            state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)

            return write_json_safely(state_path, asdict(self))
        except Exception:
            return False

    @classmethod
    def load(cls, session_id: str, agent_id: Optional[str] = None) -> "SessionOperationalState":
        """
        Load state from .maceff/sessions/{session_id}/, returning default instance on failure.

        Args:
            session_id: Session identifier
            agent_id: Agent identifier (auto-detected if None, used for default instance)

        Returns:
            SessionOperationalState instance (never crashes)
        """
        try:
            # Auto-detect agent_id if needed (for default instance)
            if not agent_id:
                try:
                    from .config import ConsciousnessConfig
                    config = ConsciousnessConfig()
                    agent_id = config.agent_id
                except Exception:
                    agent_id = os.environ.get('MACEFF_USER') or os.environ.get('USER') or 'unknown_agent'

            # Get session state path (environment-aware)
            state_path = get_session_state_path(session_id)

            # Read state if exists
            data = read_json_safely(state_path)

            if not data:
                # Return default instance if file doesn't exist
                return cls(session_id=session_id, agent_id=agent_id)

            # Restore from saved data
            return cls(**data)
        except Exception:
            # Always return valid instance, never crash
            return cls(session_id=session_id, agent_id=agent_id or "unknown_agent")
