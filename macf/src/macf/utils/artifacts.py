"""
Artifacts utilities.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

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
        private_dir = agent_root / "private"

        # Discover artifacts with safe empty list fallbacks
        # Reflections and checkpoints are private (consciousness preservation)
        reflections_dir = private_dir / "reflections" if private_dir.exists() else None
        checkpoints_dir = private_dir / "checkpoints" if private_dir.exists() else None

        # Roadmaps are public (shareable planning documents)
        roadmaps_dir = public_dir / "roadmaps" if public_dir.exists() else None

        reflections = []
        if reflections_dir and reflections_dir.exists():
            reflections = sorted(
                [p for p in reflections_dir.glob("*.md") if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:limit]

        checkpoints = []
        if checkpoints_dir and checkpoints_dir.exists():
            checkpoints = sorted(
                [p for p in checkpoints_dir.glob("*.md") if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:limit]

        roadmaps = []
        if roadmaps_dir and roadmaps_dir.exists():
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

