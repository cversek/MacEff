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


def _bash_pattern_command(entry: str) -> Optional[str]:
    """Extract the command portion from a 'Bash(<cmd>:*)' permission entry.

    Returns the command (e.g. 'gh issue create') or None if the entry is not
    a Bash() permission pattern. Used by shadow detection to compare allow
    and ask patterns regardless of trailing-wildcard form.
    """
    if not entry.startswith("Bash(") or not entry.endswith(")"):
        return None
    inner = entry[5:-1]
    # Strip trailing ":*" (the conventional CC wildcard)
    if inner.endswith(":*"):
        inner = inner[:-2]
    return inner.strip()


def _find_shadowing_allow_entries(ask_entry: str, allow_list: list) -> list:
    """Return allow entries broader than (i.e., shadowing) the given ask entry.

    A shadow is an allow pattern whose stripped command is a prefix of the
    ask's stripped command, on a space boundary (or exactly equal). Example:
    ``Bash(gh issue:*)`` shadows ``Bash(gh issue create:*)`` because every
    invocation matched by the ask is also matched by the allow.

    Identical entries (allow == ask) are NOT returned — they're handled by
    the caller's add/remove logic, not by relocation.

    Returns a list (possibly empty) of allow entries that shadow the ask.
    Non-Bash() entries in allow_list are ignored.
    """
    ask_cmd = _bash_pattern_command(ask_entry)
    if ask_cmd is None:
        return []
    shadows = []
    for allow in allow_list:
        if allow == ask_entry:
            continue  # exact-match handled elsewhere; not a shadow
        allow_cmd = _bash_pattern_command(allow)
        if allow_cmd is None:
            continue
        # Allow is a shadow when its command is a prefix of the ask's command
        # on a space boundary, or when the two commands are identical (which
        # we already filtered with the exact-pattern equality above; this
        # second check covers ``Bash(gh release:*)`` vs ``Bash(gh release:*)``
        # where stripped-cmd equality but possibly differing wildcard form).
        if ask_cmd == allow_cmd or ask_cmd.startswith(allow_cmd + " "):
            shadows.append(allow)
    return shadows


def toggle_auto_mode_ask_permissions(enable_auto: bool, project_root: Optional[Path] = None) -> dict:
    """
    Toggle AUTO_MODE-specific ask permissions.

    Returns:
        Dict with keys:
          - 'changed': list of ask entries added (enable) or removed (disable)
          - 'shadows_relocated': list of (ask_entry, [shadowing_allow_entries])
            tuples for shadows moved out of allow during enable; empty during
            disable
          - 'shadows_restored': list of allow entries restored on disable
        Returns None on error.

    Design (closes GH issue #67):
        On enable, for every ask entry being installed, scan the allow list
        for broader patterns that would shadow it (e.g. ``Bash(gh issue:*)``
        shadowing ``Bash(gh issue create:*)``). Remove the shadowing entries
        from allow and stash them under settings['_macf_shadowed_allow']
        keyed by the ask entry that displaced them. Print a stderr warning
        for transparency.

        On disable (return to MANUAL_MODE), restore the previously-stashed
        allow entries so the user's pre-AUTO_MODE permission state is
        recovered cleanly.
    """
    try:
        settings, settings_path = _read_settings(project_root)
        permissions = settings.setdefault('permissions', {})
        ask_list = permissions.setdefault('ask', [])
        allow_list = permissions.setdefault('allow', [])
        shadowed_store = settings.setdefault('_macf_shadowed_allow', {})

        changed = []
        shadows_relocated = []
        shadows_restored = []

        if enable_auto:
            for entry in _AUTO_MODE_ASK:
                if entry not in ask_list:
                    ask_list.append(entry)
                    changed.append(entry)
                # Relocate shadowing allow entries even if the ask was already
                # present (covers brownfield envs where the ask was added in a
                # prior session but allow shadows pre-existed).
                shadows = _find_shadowing_allow_entries(entry, allow_list)
                if shadows:
                    stash = shadowed_store.setdefault(entry, [])
                    for s in shadows:
                        if s in allow_list:
                            allow_list.remove(s)
                        if s not in stash:
                            stash.append(s)
                    shadows_relocated.append((entry, shadows))
                    print(
                        f"⚠️ MACF: AUTO_MODE ask '{entry}' would have been shadowed by "
                        f"broader allow entries — relocated to safekeeping for "
                        f"restoration on MANUAL_MODE return: {shadows}",
                        file=sys.stderr,
                    )
        else:
            for entry in _AUTO_MODE_ASK:
                if entry in ask_list:
                    ask_list.remove(entry)
                    changed.append(entry)
                # Restore any allow entries we stashed on AUTO_MODE entry
                stash = shadowed_store.pop(entry, [])
                for s in stash:
                    if s not in allow_list:
                        allow_list.append(s)
                        shadows_restored.append(s)

            # If the stash is now empty, drop the key for tidiness
            if not shadowed_store:
                settings.pop('_macf_shadowed_allow', None)

        if changed or shadows_relocated or shadows_restored:
            _write_settings(settings, settings_path)
        return {
            'changed': changed,
            'shadows_relocated': shadows_relocated,
            'shadows_restored': shadows_restored,
        }
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
