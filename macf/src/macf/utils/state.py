"""
State utilities.
"""

import json
import os
import time
from dataclasses import asdict, dataclass, field
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

def get_agent_state_path(agent_root: Optional[Path] = None) -> Path:
    """
    Get path to .maceff/agent_state.json.

    Args:
        agent_root: Project root (auto-detected if None)

    Returns:
        Path to project state file
    """
    if agent_root is None:
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

    Create .maceff/ directory if needed.

    Args:
        state: Project state dict to save
        agent_root: Project root (auto-detected if None)

    Returns:
        True if successful, False otherwise
    """
    try:
        state_path = get_agent_state_path(agent_root)

        # Create .maceff directory if needed
        state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)

        # Update timestamp
        state['last_updated'] = time.time()

        return write_json_safely(state_path, state)
    except Exception:
        return False

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
