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
        except (ImportError, OSError) as e:
            import sys
            print(f"⚠️ MACF: Project root detection failed (using None): {e}", file=sys.stderr)
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
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError) as e:
        import sys
        print(f"⚠️ MACF: Settings read failed (returning None): {e}", file=sys.stderr)
        return None


def set_autocompact_enabled(enabled: bool) -> bool:
    """
    Set Claude Code autocompact setting in ~/.claude.json.

    This modifies the global Claude Code UI settings file to enable or
    disable automatic compaction. Required for AUTO_MODE operation.

    Args:
        enabled: True to enable autocompact, False to disable

    Returns:
        True if successfully updated, False on error

    Note:
        Modifies ~/.claude.json (Claude Code UI settings).
        Changes take effect on next Claude Code session.
    """
    try:
        settings_path = Path.home() / ".claude.json"

        # Read existing settings or create new
        if settings_path.exists():
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        else:
            settings = {}

        # Update autocompact setting (use camelCase to match CC convention)
        settings['autoCompactEnabled'] = enabled

        # Write atomically via temp file
        temp_path = settings_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(settings, f, indent=2)
        temp_path.replace(settings_path)

        return True
    except (OSError, json.JSONDecodeError, TypeError) as e:
        import sys
        print(f"⚠️ MACF: Settings write failed (autocompact): {e}", file=sys.stderr)
        return False


def set_permission_mode(mode: str, project_root: Optional[Path] = None) -> bool:
    """
    Set Claude Code default permission mode in project settings.

    This modifies .claude/settings.local.json to change how Claude Code
    handles permission requests (accept-edits, plan, bypassPermissions, etc.).

    Args:
        mode: Permission mode string (e.g., "accept-edits", "plan", "default")
        project_root: Project root path. If None, attempts auto-detection.

    Returns:
        True if successfully updated, False on error

    Note:
        Modifies project-local .claude/settings.local.json.
        Common modes: "default", "accept-edits", "plan", "bypassPermissions"
    """
    try:
        if project_root is None:
            from .paths import find_project_root
            project_root = find_project_root()

        settings_dir = project_root / ".claude"
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_path = settings_dir / "settings.local.json"

        # Read existing settings or create new
        if settings_path.exists():
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        else:
            settings = {}

        # Ensure permissions dict exists
        if 'permissions' not in settings:
            settings['permissions'] = {}

        # Update default mode
        settings['permissions']['defaultMode'] = mode

        # Write atomically via temp file
        temp_path = settings_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(settings, f, indent=2)
        temp_path.replace(settings_path)

        return True
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as e:
        import sys
        print(f"⚠️ MACF: Settings write failed (permission mode): {e}", file=sys.stderr)
        return False
