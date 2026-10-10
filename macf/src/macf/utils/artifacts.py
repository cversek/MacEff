"""
Artifacts utilities.
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Files a tool may keep beside the artifacts; never an artifact themselves.
_NOT_ARTIFACTS = {"CLAUDE.md", "README.md", "INDEX.md"}

_NAME_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_(\d{6}))?")


def _artifact_files(directory: Path) -> List[Path]:
    return [p for p in directory.glob("*.md") if p.is_file() and p.name not in _NOT_ARTIFACTS]


@dataclass(frozen=True, kw_only=True, order=True)
class _Recency:
    """A sort key, compared field by field in this order."""
    date: str
    time: str
    mtime: float


def _recency(path: Path) -> _Recency:
    """How recent an artifact is: the date (and time) it is named for, then mtime.

    Curation edits old artifacts in place (`knowledge link` adds wiki-links), which
    moves their mtimes past the newest one; the date in the name does not move. A
    folder roadmap is named by its folder. An undated name sorts before every dated one.
    """
    name = path.parent.name if path.name == "roadmap.md" else path.name
    m = _NAME_DATE.match(name)
    return _Recency(date=m.group(1) if m else "", time=(m.group(2) or "") if m else "",
                    mtime=path.stat().st_mtime)


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
    # Set when discovery itself failed. An empty result and a failed search must not
    # read the same: the recovery message once told a successor its predecessor left
    # nothing to read, which is a claim about the tree only if the search ran.
    error: Optional[str] = None

    @property
    def latest_reflection(self) -> Optional[Path]:
        """Most recent reflection, by the date in its name, then mtime."""
        if not self.reflections:
            return None
        return max(self.reflections, key=_recency)

    @property
    def latest_checkpoint(self) -> Optional[Path]:
        """Most recent checkpoint, by the date in its name, then mtime."""
        if not self.checkpoints:
            return None
        return max(self.checkpoints, key=_recency)

    @property
    def latest_roadmap(self) -> Optional[Path]:
        """Most recent roadmap, by the date in its name, then mtime."""
        if not self.roadmaps:
            return None
        return max(self.roadmaps, key=_recency)

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
                from macf.config import ConsciousnessConfig
                config = ConsciousnessConfig()
                agent_root = config.agent_root
            except Exception as e:
                # Log error to stderr for debugging (hooks can see this)
                print(f"⚠️ artifact discovery: ConsciousnessConfig failed: {type(e).__name__}: {e}", file=sys.stderr)
                return ConsciousnessArtifacts(error=f"ConsciousnessConfig failed: {type(e).__name__}: {e}")

        # Ensure agent_root is a Path
        agent_root = Path(agent_root)

        # A root that is not there is a failed search, not an agent with nothing to read.
        if not agent_root.exists():
            return ConsciousnessArtifacts(error=f"agent directory not found: {agent_root}")

        # agent_root already points to agent/ directory from ConsciousnessConfig
        public_dir = agent_root / "public"
        private_dir = agent_root / "private"
        if not public_dir.exists() and not private_dir.exists():
            # Every agent tree has both; a root with neither is the wrong directory
            # (a repository root given for its agent/), not an empty agent.
            return ConsciousnessArtifacts(error=f"neither public/ nor private/ under {agent_root}")

        # Discover artifacts with safe empty list fallbacks
        # Reflections and checkpoints are private (consciousness preservation)
        reflections_dir = private_dir / "reflections" if private_dir.exists() else None
        checkpoints_dir = private_dir / "checkpoints" if private_dir.exists() else None

        # Roadmaps are public (shareable planning documents)
        roadmaps_dir = public_dir / "roadmaps" if public_dir.exists() else None

        reflections = []
        if reflections_dir and reflections_dir.exists():
            reflections = sorted(
                _artifact_files(reflections_dir),
                key=_recency,
                reverse=True
            )[:limit]

        checkpoints = []
        if checkpoints_dir and checkpoints_dir.exists():
            checkpoints = sorted(
                _artifact_files(checkpoints_dir),
                key=_recency,
                reverse=True
            )[:limit]

        roadmaps = []
        if roadmaps_dir and roadmaps_dir.exists():
            roadmaps = sorted(
                # A roadmap is a folder holding roadmap.md (roadmaps_drafting). Agents
                # that predate the folder form keep loose files, which still count.
                [p for p in roadmaps_dir.glob("*/roadmap.md") if p.is_file()]
                + _artifact_files(roadmaps_dir),
                key=_recency,
                reverse=True
            )[:limit]

        return ConsciousnessArtifacts(
            reflections=reflections,
            checkpoints=checkpoints,
            roadmaps=roadmaps
        )
    except Exception as e:
        # NEVER crash - return empty artifacts, but log the error
        print(f"⚠️ artifact discovery: unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        return ConsciousnessArtifacts(error=f"{type(e).__name__}: {e}")

