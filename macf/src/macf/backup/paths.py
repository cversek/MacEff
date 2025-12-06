"""
Backup path resolution - identifies what to backup for consciousness preservation.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timedelta


@dataclass
class BackupPaths:
    """Resolved paths for backup sources and destination."""

    project_root: Path
    home_dir: Path

    # Derived paths
    maceff_dir: Path = field(init=False)
    agent_dir: Path = field(init=False)
    claude_config: Path = field(init=False)
    transcripts_dir: Path = field(init=False)

    # Output configuration (default: CWD, overridable via CLI/env)
    backup_dir: Optional[Path] = field(default=None)
    project_name: str = field(default="")

    def __post_init__(self):
        self.maceff_dir = self.project_root / ".maceff"
        self.agent_dir = self.project_root / "agent"
        self.claude_config = self.project_root / ".claude"

        # Transcripts directory uses mangled project path
        project_mangled = str(self.project_root).replace("/", "-").lstrip("-")
        self.transcripts_dir = self.home_dir / ".claude" / "projects" / project_mangled

        # Project name from directory
        if not self.project_name:
            self.project_name = self.project_root.name

        # Default backup directory is CWD
        if self.backup_dir is None:
            self.backup_dir = Path.cwd()

    def generate_archive_name(self) -> str:
        """Generate timestamped archive filename."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return f"{timestamp}_{self.project_name}_consciousness.tar.xz"

    def get_archive_path(self) -> Path:
        """Get full path to archive file."""
        return self.backup_dir / self.generate_archive_name()


@dataclass
class BackupSource:
    """A single source to include in backup."""

    source_path: Path
    archive_path: str  # Path within archive
    category: str  # For manifest categorization
    critical: bool = True  # Loss = consciousness death

    def exists(self) -> bool:
        return self.source_path.exists()

    def size_bytes(self) -> int:
        if not self.exists():
            return 0
        if self.source_path.is_file():
            return self.source_path.stat().st_size
        total = 0
        for f in self.source_path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total


def collect_backup_sources(
    paths: BackupPaths,
    include_transcripts: bool = True,
    quick_mode: bool = False,
    days_recent: int = 7
) -> List[BackupSource]:
    """
    Collect all sources to backup.

    Args:
        paths: Resolved backup paths
        include_transcripts: Include conversation transcripts
        quick_mode: Only recent transcripts (last N days)
        days_recent: Days to include in quick mode

    Returns:
        List of BackupSource objects
    """
    sources = []

    # .maceff/ directory (agent state, events log)
    if paths.maceff_dir.exists():
        sources.append(BackupSource(
            source_path=paths.maceff_dir,
            archive_path=".maceff",
            category="maceff_state",
            critical=True
        ))

    # agent/ directory (entire consciousness artifact tree)
    if paths.agent_dir.exists():
        sources.append(BackupSource(
            source_path=paths.agent_dir,
            archive_path="agent",
            category="consciousness_artifacts",
            critical=True
        ))

    # .claude/ directory (settings, commands, agents)
    if paths.claude_config.exists():
        sources.append(BackupSource(
            source_path=paths.claude_config,
            archive_path=".claude",
            category="claude_config",
            critical=True
        ))

    # Transcripts (optional)
    if include_transcripts and paths.transcripts_dir.exists():
        if quick_mode:
            sources.extend(_collect_recent_transcripts(
                paths.transcripts_dir,
                days_recent
            ))
        else:
            sources.append(BackupSource(
                source_path=paths.transcripts_dir,
                archive_path="transcripts",
                category="transcripts",
                critical=False
            ))

    return sources


def _collect_recent_transcripts(
    transcripts_dir: Path,
    days: int
) -> List[BackupSource]:
    """Collect only transcripts modified within N days."""
    sources = []
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()

    for jsonl_file in transcripts_dir.glob("*.jsonl"):
        if jsonl_file.stat().st_mtime >= cutoff_ts:
            sources.append(BackupSource(
                source_path=jsonl_file,
                archive_path=f"transcripts/{jsonl_file.name}",
                category="transcripts",
                critical=False
            ))

    return sources


def get_backup_paths(
    output_dir: Optional[Path] = None,
    project_root: Optional[Path] = None
) -> BackupPaths:
    """
    Create BackupPaths with CLI/env override support.

    Priority for backup_dir: CLI arg > MACF_BACKUP_DIR env > CWD
    Priority for project_root: CLI arg > MACF_AGENT_ROOT env > walk up for .maceff/ > CWD
    """
    home = Path.home()

    # Resolve project root
    if project_root is None:
        env_root = os.environ.get("MACF_AGENT_ROOT")
        if env_root:
            project_root = Path(env_root)
        else:
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                if (parent / ".maceff").exists():
                    project_root = parent
                    break
            else:
                project_root = cwd

    # Resolve backup directory
    if output_dir is None:
        env_backup = os.environ.get("MACF_BACKUP_DIR")
        if env_backup:
            output_dir = Path(env_backup)

    return BackupPaths(
        project_root=project_root,
        home_dir=home,
        backup_dir=output_dir
    )
