"""
Claude Code settings utilities.

Functions for reading Claude Code configuration to adapt MACF behavior
to user's Claude Code settings (autocompact, etc.).
"""

import json
from pathlib import Path
from typing import Optional


def get_autocompact_setting(project_root: Optional[Path] = None) -> bool:
    """
    Detect if Claude Code autocompact is enabled.

    Checks multiple locations for autocompact setting:
    1. Project-specific .claude/settings.local.json
    2. Global ~/.claude/settings.json
    3. Environment variable CLAUDE_AUTOCOMPACT

    Args:
        project_root: Optional project root path. If None, attempts auto-detection.

    Returns:
        True if autocompact is enabled, False if disabled or not found.

    Note:
        Defaults to False (disabled) if setting not found anywhere.
        This is safe default for manual compaction workflows.
    """
    # Check environment variable first (highest priority)
    import os
    env_setting = os.environ.get('CLAUDE_AUTOCOMPACT', '').lower()
    if env_setting in ('true', '1', 'yes', 'on'):
        return True
    elif env_setting in ('false', '0', 'no', 'off'):
        return False

    # Try project-specific settings
    if project_root is None:
        # Auto-detect project root
        try:
            from .paths import find_project_root
            project_root = find_project_root()
        except Exception:
            project_root = None

    if project_root:
        project_settings = project_root / ".claude" / "settings.local.json"
        autocompact = _read_autocompact_from_file(project_settings)
        if autocompact is not None:
            return autocompact

    # Try global settings
    global_settings = Path.home() / ".claude" / "settings.json"
    autocompact = _read_autocompact_from_file(global_settings)
    if autocompact is not None:
        return autocompact

    # Default to False (autocompact disabled) if not found
    # This is safest default for users who manually compact
    return False


def _read_autocompact_from_file(settings_path: Path) -> Optional[bool]:
    """
    Read autocompact setting from a JSON settings file.

    Args:
        settings_path: Path to settings JSON file

    Returns:
        True if enabled, False if disabled, None if not found/error
    """
    try:
        if not settings_path.exists():
            return None

        with open(settings_path, 'r') as f:
            settings = json.load(f)

        # Look for autocompact setting (various possible keys)
        for key in ['autocompact', 'autoCompact', 'auto_compact']:
            if key in settings:
                return bool(settings[key])

        return None
    except Exception:
        return None
