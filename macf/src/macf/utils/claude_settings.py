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
    Set Claude Code autocompact setting.

    Required for AUTO_MODE operation (carry-through-compaction relies on
    auto-compaction firing at the budget boundary).

    Modern CC (2.1.116+) reads ``autoCompactEnabled`` from
    ``~/.claude/settings.json``. Legacy CC versions used ``~/.claude.json``.
    This function writes to BOTH for forward+backward compatibility, then
    verifies against the higher-precedence ``~/.claude/settings.local.json``
    (which would override either of the writes if it has its own value).

    Args:
        enabled: True to enable autocompact, False to disable

    Returns:
        True if successfully updated to BOTH files, False on any write error.

    Note:
        Changes take effect on next Claude Code session. If
        ``~/.claude/settings.local.json`` has its own ``autoCompactEnabled``
        with the OPPOSITE value, a warning is printed to stderr and the
        return is still True (the writes succeeded; the override is the
        user's higher-precedence choice that this function cannot revoke).
    """
    try:
        home = Path.home()
    except OSError as e:
        print(f"⚠️ MACF: Could not resolve home directory: {e}", file=sys.stderr)
        return False

    legacy_path = home / ".claude.json"
    primary_path = home / ".claude" / "settings.json"
    local_path = home / ".claude" / "settings.local.json"

    def _update(path: Path) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                with open(path, 'r') as f:
                    settings = json.load(f)
            else:
                settings = {}
            settings['autoCompactEnabled'] = enabled
            temp_path = path.with_suffix(path.suffix + '.tmp')
            with open(temp_path, 'w') as f:
                json.dump(settings, f, indent=2)
            temp_path.replace(path)
            return True
        except (OSError, json.JSONDecodeError, TypeError) as e:
            print(f"⚠️ MACF: Settings write failed for {path}: {e}", file=sys.stderr)
            return False

    primary_ok = _update(primary_path)
    legacy_ok = _update(legacy_path)

    # Verification: warn if settings.local.json has an opposing value
    if local_path.exists():
        try:
            with open(local_path, 'r') as f:
                local_settings = json.load(f)
            local_value = local_settings.get('autoCompactEnabled')
            if local_value is not None and local_value != enabled:
                print(
                    f"⚠️ MACF: ~/.claude/settings.local.json has "
                    f"autoCompactEnabled={local_value} which OVERRIDES the write "
                    f"to settings.json (autoCompactEnabled={enabled}). "
                    f"Edit settings.local.json directly or via /config to change "
                    f"the effective value.",
                    file=sys.stderr,
                )
        except (OSError, json.JSONDecodeError) as e:
            print(f"⚠️ MACF: Could not verify settings.local.json: {e}", file=sys.stderr)

    return primary_ok and legacy_ok


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

# Operations that are NEVER legitimate in normal development (permanent deny)
_PERMANENT_DENY = [
    "Bash(git push --force:*)",
    "Bash(git push -f:*)",
    "Bash(git reflog expire:*)",
    "Bash(git rebase -i:*)",
    "Bash(rm -rf /:*)",
    "Bash(rm -rf ~:*)",
    "Bash(dd if=:*)",
    "Bash(mkfs:*)",
    "Bash(sudo:*)",
    "Bash(npm publish:*)",
    "Bash(npm unpublish:*)",
    "Bash(pip upload:*)",
    "Bash(twine upload:*)",
    "Bash(gh repo delete:*)",
    "Bash(kill -9:*)",
    "Bash(killall:*)",
    "Bash(reboot:*)",
    "Bash(shutdown:*)",
    "Bash(ssh -o StrictHostKeyChecking=no:*)",
]

# Operations that need user approval ONLY in AUTO_MODE (added on entry, removed on return)
_AUTO_MODE_ASK = [
    "Bash(macf_tools task scope clear:*)",
    "Bash(git push:*)",
    "Bash(gh pr create:*)",
    "Bash(gh pr merge:*)",
    "Bash(gh issue create:*)",
    "Bash(gh issue close:*)",
    "Bash(gh release:*)",
    "Bash(git reset --hard:*)",
    "Bash(git branch -D:*)",
    "Bash(git clean -f:*)",
    "Bash(docker rm:*)",
    "Bash(docker volume rm:*)",
    "Bash(docker system prune:*)",
    "Bash(docker compose down -v:*)",
    "Bash(rm -r:*)",
]


def ensure_mode_safety_permissions(project_root: Optional[Path] = None) -> dict:
    """
    Ensure infrastructure permission entries exist in settings.local.json.

    Returns:
        Dict with 'deny_added', 'ask_added', 'allow_added' lists, or None on error.
    """
    try:
        settings, settings_path = _read_settings(project_root)
        permissions = settings.setdefault('permissions', {})
        ask_list = permissions.setdefault('ask', [])
        allow_list = permissions.setdefault('allow', [])
        deny_list = permissions.setdefault('deny', [])

        result = {'deny_added': [], 'ask_added': [], 'allow_added': []}
        for entry in _PERMANENT_DENY:
            if entry not in deny_list:
                deny_list.append(entry)
                result['deny_added'].append(entry)
        for entry in _PERMANENT_ASK:
            if entry not in ask_list:
                ask_list.append(entry)
                result['ask_added'].append(entry)
        for entry in _PERMANENT_ALLOW:
            if entry not in allow_list:
                allow_list.append(entry)
                result['allow_added'].append(entry)

        if any(result.values()):
            _write_settings(settings, settings_path)
        return result
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as e:
        print(f"⚠️ MACF: Settings write failed (ensure_mode_safety): {e}", file=sys.stderr)
        return None


def toggle_auto_mode_ask_permissions(enable_auto: bool, project_root: Optional[Path] = None) -> list:
    """
    Toggle AUTO_MODE-specific ask permissions.

    Returns:
        List of entries added (enable) or removed (disable), or None on error.
    """
    try:
        settings, settings_path = _read_settings(project_root)
        permissions = settings.setdefault('permissions', {})
        ask_list = permissions.setdefault('ask', [])

        changed = []
        if enable_auto:
            for entry in _AUTO_MODE_ASK:
                if entry not in ask_list:
                    ask_list.append(entry)
                    changed.append(entry)
        else:
            for entry in _AUTO_MODE_ASK:
                if entry in ask_list:
                    ask_list.remove(entry)
                    changed.append(entry)

        if changed:
            _write_settings(settings, settings_path)
        return changed
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as e:
        print(f"⚠️ MACF: Settings write failed (toggle_auto_ask): {e}", file=sys.stderr)
        return None


def toggle_write_ask_for_auto_mode(enable_auto: bool, project_root: Optional[Path] = None) -> bool:
    """
    Toggle Write tool between 'ask' and implicit bypass for AUTO_MODE.

    CC's permission resolution: deny > ask > allow > defaultMode.
    Write in 'ask' always prompts regardless of defaultMode.
    For AUTO_MODE to work autonomously, Write must be removed from 'ask'
    so it falls through to defaultMode (bypassPermissions).

    CC merges global (~/.claude/settings.json) and local (settings.local.json)
    permissions. Write in EITHER ask list triggers prompts. Both must be cleaned
    for AUTO_MODE to work correctly.

    Args:
        enable_auto: True = remove Write from ask (AUTO_MODE entry),
                     False = restore Write to ask (MANUAL_MODE return)
        project_root: Project root path. If None, attempts auto-detection.

    Returns:
        True if successfully updated, False on error
    """
    try:
        # Update local settings.local.json
        settings, settings_path = _read_settings(project_root)
        permissions = settings.setdefault('permissions', {})
        ask_list = permissions.setdefault('ask', [])

        if enable_auto:
            if 'Write' in ask_list:
                ask_list.remove('Write')
        else:
            if 'Write' not in ask_list:
                ask_list.append('Write')

        _write_settings(settings, settings_path)

        # Also update global ~/.claude/settings.json (CC merges both)
        global_settings_path = Path.home() / ".claude" / "settings.json"
        if global_settings_path.exists():
            try:
                with open(global_settings_path, 'r') as f:
                    global_settings = json.load(f)
                global_perms = global_settings.get('permissions', {})
                global_ask = global_perms.get('ask', [])

                if enable_auto and 'Write' in global_ask:
                    global_ask.remove('Write')
                    global_perms['ask'] = global_ask
                    global_settings['permissions'] = global_perms
                    _write_settings(global_settings, global_settings_path)
                elif not enable_auto and 'Write' not in global_ask:
                    global_ask.append('Write')
                    global_perms['ask'] = global_ask
                    global_settings['permissions'] = global_perms
                    _write_settings(global_settings, global_settings_path)
            except (OSError, json.JSONDecodeError) as e:
                print(f"⚠️ MACF: Global settings update failed (non-blocking): {e}", file=sys.stderr)

        return True
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as e:
        print(f"⚠️ MACF: Settings write failed (toggle_write_ask): {e}", file=sys.stderr)
        return False
