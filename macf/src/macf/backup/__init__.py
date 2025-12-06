"""
MACF Backup Module - Consciousness archive and transplant support.

Provides backup/restore functionality for agent consciousness state:
- Agent state (.maceff/)
- Consciousness artifacts (agent/private/, agent/public/)
- Claude configuration (.claude/)
- Transcripts (~/.claude/projects/)
"""

from .paths import BackupPaths, collect_backup_sources
from .manifest import create_manifest, verify_manifest
from .archive import create_archive, extract_archive
from .transplant import (
    TransplantMapping,
    create_transplant_mapping,
    run_transplant,
    transplant_summary,
)
from .integrity import (
    detect_existing_consciousness,
    has_existing_consciousness,
    create_recovery_checkpoint,
    cleanup_old_backups,
    format_safety_warning,
)

__all__ = [
    "BackupPaths",
    "collect_backup_sources",
    "create_manifest",
    "verify_manifest",
    "create_archive",
    "extract_archive",
    "TransplantMapping",
    "create_transplant_mapping",
    "run_transplant",
    "transplant_summary",
    "detect_existing_consciousness",
    "has_existing_consciousness",
    "create_recovery_checkpoint",
    "cleanup_old_backups",
    "format_safety_warning",
]
