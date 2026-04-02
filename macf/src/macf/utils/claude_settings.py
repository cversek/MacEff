"""
Claude Code settings utilities.

Functions for reading Claude Code configuration to adapt MACF behavior
to user's Claude Code settings (autocompact, etc.).
"""

import json
import sys
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
        print(f"⚠️ MACF: Settings write failed (permission mode): {e}", file=sys.stderr)
        return False


def _read_settings(project_root: Optional[Path] = None) -> tuple:
    """Read settings.local.json, returning (settings_dict, settings_path) or raise."""
    if project_root is None:
        from .paths import find_project_root
        project_root = find_project_root()

    settings_path = project_root / ".claude" / "settings.local.json"

    if settings_path.exists():
        with open(settings_path, 'r') as f:
            settings = json.load(f)
    else:
        settings = {}

    return settings, settings_path


def _write_settings(settings: dict, settings_path: Path) -> None:
    """Write settings atomically via temp file."""
    temp_path = settings_path.with_suffix('.tmp')
    with open(temp_path, 'w') as f:
        json.dump(settings, f, indent=2)
    temp_path.replace(settings_path)


# Permissions that must always be in 'ask' (escalation requires human approval)
_PERMANENT_ASK = [
    "Bash(macf_tools task grant:*)",
    "Bash(macf_tools task grant-update:*)",
    "Bash(macf_tools task grant-delete:*)",
    "Bash(macf_tools mode set AUTO_MODE:*)",
]

# Permissions that must always be in 'allow' (agent can always de-escalate)
_PERMANENT_ALLOW = [
    "Bash(macf_tools mode set MANUAL_MODE:*)",
]


def ensure_mode_safety_permissions(project_root: Optional[Path] = None) -> bool:
    """
    Ensure infrastructure permission entries exist in settings.local.json.

    Installs permanent permission entries for mode switching safety:
    - AUTO_MODE activation in 'ask' (escalation always requires human approval)
    - MANUAL_MODE activation in 'allow' (agent can always de-escalate freely)
    - Task grant operations in 'ask' (destructive task manipulation needs approval)

    These entries are mode-independent — they persist across AUTO/MANUAL switches.
    Called by mode set command to ensure safety infrastructure is always present.

    Returns:
        True if successfully updated, False on error
    """
    try:
        settings, settings_path = _read_settings(project_root)
        permissions = settings.setdefault('permissions', {})
        ask_list = permissions.setdefault('ask', [])
        allow_list = permissions.setdefault('allow', [])

        changed = False
        for entry in _PERMANENT_ASK:
            if entry not in ask_list:
                ask_list.append(entry)
                changed = True
        for entry in _PERMANENT_ALLOW:
            if entry not in allow_list:
                allow_list.append(entry)
                changed = True

        if changed:
            _write_settings(settings, settings_path)
        return True
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as e:
        print(f"⚠️ MACF: Settings write failed (ensure_mode_safety): {e}", file=sys.stderr)
        return False


def toggle_write_ask_for_auto_mode(enable_auto: bool, project_root: Optional[Path] = None) -> bool:
    """
    Toggle Write tool between 'ask' and implicit bypass for AUTO_MODE.

    CC's permission resolution: deny > ask > allow > defaultMode.
    Write in 'ask' always prompts regardless of defaultMode.
    For AUTO_MODE to work autonomously, Write must be removed from 'ask'
    so it falls through to defaultMode (bypassPermissions).

    Args:
        enable_auto: True = remove Write from ask (AUTO_MODE entry),
                     False = restore Write to ask (MANUAL_MODE return)
        project_root: Project root path. If None, attempts auto-detection.

    Returns:
        True if successfully updated, False on error
    """
    try:
        settings, settings_path = _read_settings(project_root)
        permissions = settings.setdefault('permissions', {})
        ask_list = permissions.setdefault('ask', [])

        if enable_auto:
            # Remove Write from ask so bypassPermissions covers it
            if 'Write' in ask_list:
                ask_list.remove('Write')
        else:
            # Restore Write to ask for MANUAL_MODE prompting
            if 'Write' not in ask_list:
                ask_list.append('Write')

        _write_settings(settings, settings_path)
        return True
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as e:
        print(f"⚠️ MACF: Settings write failed (toggle_write_ask): {e}", file=sys.stderr)
        return False
