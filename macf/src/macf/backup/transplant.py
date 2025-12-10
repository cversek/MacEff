"""
Transplant path rewriting for cross-system consciousness restore.

Handles rewriting paths when restoring a backup from one system to another
(e.g., macOS development machine to Linux deployment server).
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class TransplantMapping:
    """Path mapping for transplant operations."""

    # Original paths from source system (extracted from manifest)
    source_project_root: Path
    source_maceff_root: Path
    source_home: Path
    source_transcripts_dir: Path

    # Target paths on destination system
    target_project_root: Path
    target_maceff_root: Path
    target_home: Path
    target_transcripts_dir: Path = field(init=False)

    def __post_init__(self):
        """Derive transcripts directory from target paths."""
        # Claude stores transcripts in ~/.claude/projects/ with path-based naming
        # Convert project root to Claude's path-based directory name
        project_path_slug = str(self.target_project_root).replace("/", "-").lstrip("-")
        self.target_transcripts_dir = self.target_home / ".claude" / "projects" / project_path_slug

    def rewrite_path(self, path: str) -> str:
        """
        Rewrite a single path from source to target system.

        Args:
            path: Original path string from source system

        Returns:
            Rewritten path string for target system
        """
        # Order matters: more specific paths first
        mappings = [
            (str(self.source_transcripts_dir), str(self.target_transcripts_dir)),
            (str(self.source_project_root), str(self.target_project_root)),
            (str(self.source_maceff_root), str(self.target_maceff_root)),
            (str(self.source_home), str(self.target_home)),
        ]

        result = path
        for source, target in mappings:
            # Skip empty or trivial paths that would match too broadly
            if not source or source == "." or len(source) < 3:
                continue
            if source in result:
                result = result.replace(source, target)
                break  # Only apply first matching rule

        return result

    def rewrite_paths_in_text(self, text: str) -> str:
        """
        Rewrite all paths found in a text block.

        Args:
            text: Text content potentially containing paths

        Returns:
            Text with all paths rewritten
        """
        # Order matters: more specific paths first
        mappings = [
            (str(self.source_transcripts_dir), str(self.target_transcripts_dir)),
            (str(self.source_project_root), str(self.target_project_root)),
            (str(self.source_maceff_root), str(self.target_maceff_root)),
            (str(self.source_home), str(self.target_home)),
        ]

        result = text
        for source, target in mappings:
            # Skip empty or trivial paths that would match too broadly
            # Path("") becomes "." which would match every dot in text
            if not source or source == "." or len(source) < 3:
                continue
            result = result.replace(source, target)

        return result


def extract_source_paths(manifest: Dict) -> Dict[str, Path]:
    """
    Extract source system paths from backup manifest.

    Args:
        manifest: Parsed manifest.json from backup archive

    Returns:
        Dictionary with source path information
    """
    # Manifest stores paths under "source_paths", not "metadata"
    source_paths = manifest.get("source_paths", {})

    # Derive maceff_root from project_root if not stored
    # (typically sibling directory: /path/to/Project -> /path/to/MacEff)
    project_root = source_paths.get("project_root", "")
    maceff_root = source_paths.get("maceff_root", "")
    if not maceff_root and project_root:
        # Infer: /Users/x/gitwork/foo/Project -> /Users/x/gitwork/cversek/MacEff
        # This is a heuristic - may need adjustment
        maceff_root = str(Path(project_root).parent.parent / "cversek" / "MacEff")

    return {
        "project_root": Path(project_root) if project_root else Path(""),
        "home_dir": Path(source_paths.get("home_dir", "")),
        "maceff_root": Path(maceff_root) if maceff_root else Path(""),
        "transcripts_dir": Path(source_paths.get("transcripts_dir", "")),
    }


def create_transplant_mapping(
    manifest: Dict,
    target_project_root: Path,
    target_maceff_root: Optional[Path] = None,
) -> TransplantMapping:
    """
    Create transplant mapping from manifest and target paths.

    Args:
        manifest: Parsed manifest.json from backup archive
        target_project_root: Where to restore the agent project
        target_maceff_root: Where MacEff framework is installed (default: sibling of project)

    Returns:
        TransplantMapping configured for this transplant
    """
    source_paths = extract_source_paths(manifest)
    target_home = Path.home()

    # Default MacEff location: sibling directory of project
    if target_maceff_root is None:
        target_maceff_root = target_project_root.parent / "MacEff"

    return TransplantMapping(
        source_project_root=source_paths["project_root"],
        source_maceff_root=source_paths["maceff_root"],
        source_home=source_paths["home_dir"],
        source_transcripts_dir=source_paths["transcripts_dir"],
        target_project_root=target_project_root,
        target_maceff_root=target_maceff_root,
        target_home=target_home,
    )


def rewrite_settings_local(
    settings_path: Path,
    mapping: TransplantMapping,
    dry_run: bool = False,
) -> List[str]:
    """
    Rewrite paths in .claude/settings.local.json.

    Args:
        settings_path: Path to settings.local.json
        mapping: Transplant mapping to apply
        dry_run: If True, report changes without writing

    Returns:
        List of changes made (for logging)
    """
    changes = []

    if not settings_path.exists():
        return changes

    with open(settings_path) as f:
        content = f.read()
        settings = json.loads(content)

    # Rewrite permissions.allow paths
    if "permissions" in settings and "allow" in settings["permissions"]:
        new_allow = []
        for path in settings["permissions"]["allow"]:
            new_path = mapping.rewrite_path(path)
            if new_path != path:
                changes.append(f"permissions.allow: {path} -> {new_path}")
            new_allow.append(new_path)
        settings["permissions"]["allow"] = new_allow

    # Rewrite permissions.deny paths if present
    if "permissions" in settings and "deny" in settings["permissions"]:
        new_deny = []
        for path in settings["permissions"]["deny"]:
            new_path = mapping.rewrite_path(path)
            if new_path != path:
                changes.append(f"permissions.deny: {path} -> {new_path}")
            new_deny.append(new_path)
        settings["permissions"]["deny"] = new_deny

    if changes and not dry_run:
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)

    return changes


def recreate_symlinks(
    claude_dir: Path,
    mapping: TransplantMapping,
    dry_run: bool = False,
) -> List[str]:
    """
    Recreate symlinks in .claude/ pointing to new MacEff location.

    Args:
        claude_dir: Path to .claude/ directory
        mapping: Transplant mapping to apply
        dry_run: If True, report changes without creating symlinks

    Returns:
        List of symlinks recreated
    """
    changes = []

    # Directories containing symlinks to MacEff framework
    symlink_dirs = ["hooks", "commands", "skills", "agents"]

    for dir_name in symlink_dirs:
        dir_path = claude_dir / dir_name
        if not dir_path.exists():
            continue

        for item in dir_path.iterdir():
            if item.is_symlink():
                old_target = os.readlink(item)
                new_target = mapping.rewrite_path(old_target)

                if new_target != old_target:
                    changes.append(f"{item.name}: {old_target} -> {new_target}")

                    if not dry_run:
                        item.unlink()
                        item.symlink_to(new_target)

    return changes


def rewrite_file_contents(
    file_path: Path,
    mapping: TransplantMapping,
    dry_run: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Rewrite paths in a file's contents.

    Args:
        file_path: Path to file to rewrite
        mapping: Transplant mapping to apply
        dry_run: If True, report changes without writing

    Returns:
        Tuple of (was_modified, list of changes)
    """
    changes = []

    if not file_path.exists() or file_path.is_dir():
        return False, changes

    try:
        with open(file_path) as f:
            original = f.read()
    except (UnicodeDecodeError, PermissionError):
        # Skip binary files or inaccessible files
        return False, changes

    rewritten = mapping.rewrite_paths_in_text(original)

    if rewritten != original:
        # Find specific changes for logging
        for line_num, (old_line, new_line) in enumerate(
            zip(original.splitlines(), rewritten.splitlines()), 1
        ):
            if old_line != new_line:
                changes.append(f"Line {line_num}: path rewritten")

        if not dry_run:
            with open(file_path, "w") as f:
                f.write(rewritten)

        return True, changes

    return False, changes


def run_transplant(
    extract_dir: Path,
    mapping: TransplantMapping,
    dry_run: bool = False,
) -> Dict[str, List[str]]:
    """
    Run full transplant on extracted backup directory.

    Args:
        extract_dir: Directory where backup was extracted
        mapping: Transplant mapping to apply
        dry_run: If True, report changes without making them

    Returns:
        Dictionary of changes by category
    """
    all_changes = {
        "settings": [],
        "symlinks": [],
        "files": [],
    }

    # 1. Rewrite settings.local.json
    settings_path = extract_dir / ".claude" / "settings.local.json"
    all_changes["settings"] = rewrite_settings_local(settings_path, mapping, dry_run)

    # 2. Recreate symlinks
    claude_dir = extract_dir / ".claude"
    if claude_dir.exists():
        all_changes["symlinks"] = recreate_symlinks(claude_dir, mapping, dry_run)

    # 3. Rewrite paths in consciousness artifacts that might contain absolute paths
    # Focus on files that commonly contain path references
    artifact_patterns = [
        "agent/**/*.md",
        "agent/**/*.json",
        ".maceff/*.json",
        ".maceff/*.jsonl",
    ]

    files_changed = []
    for pattern in artifact_patterns:
        for file_path in extract_dir.glob(pattern):
            was_modified, changes = rewrite_file_contents(file_path, mapping, dry_run)
            if was_modified:
                files_changed.append(f"{file_path.relative_to(extract_dir)}: {len(changes)} changes")

    all_changes["files"] = files_changed

    return all_changes


def transplant_summary(changes: Dict[str, List[str]]) -> str:
    """
    Generate human-readable summary of transplant changes.

    Args:
        changes: Dictionary from run_transplant

    Returns:
        Formatted summary string
    """
    lines = ["Transplant Summary:", ""]

    if changes["settings"]:
        lines.append("Settings rewritten:")
        for change in changes["settings"]:
            lines.append(f"  - {change}")
        lines.append("")

    if changes["symlinks"]:
        lines.append("Symlinks recreated:")
        for change in changes["symlinks"]:
            lines.append(f"  - {change}")
        lines.append("")

    if changes["files"]:
        lines.append("Files with path rewrites:")
        for change in changes["files"]:
            lines.append(f"  - {change}")
        lines.append("")

    total = sum(len(v) for v in changes.values())
    lines.append(f"Total changes: {total}")

    return "\n".join(lines)
