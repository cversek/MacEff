"""Where the roles store lives, without loading the store.

The hooks ask where the store is on every tool call; the store module builds the pydantic
models on import, so the answer lives here, and ``store`` re-exports it.
"""
import os
from pathlib import Path

ROLES_DIR_ENV = "MACF_ROLES_DIR"


def roles_dir() -> Path:
    """``MACF_ROLES_DIR`` if set (tests, isolation), else the agent home's store."""
    env = os.environ.get(ROLES_DIR_ENV)
    if env:
        return Path(env)
    from ..utils.paths import find_agent_home
    return find_agent_home() / "agent" / "public" / "roles"
