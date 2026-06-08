"""
Agent identity utilities for MACF.

Provides functions to get agent identity information combining
display name (from GECOS) and UUID.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def get_agent_identity() -> str:
    """
    Get agent identity in format 'DisplayName@uuid_prefix'.

    Resolution (highest priority first):
    1. ``MACEFF_AGENT_NAME`` env var — explicit one-off override
    2. ``.maceff/config.json`` ``agent_identity.calling_card`` (preferred) or
       ``agent_identity.moniker`` (fallback) — per-project configured default
    3. GECOS / Directory-Services display name (spaces stripped)
    4. ``$USER`` — last-resort fallback

    Layer 2 is the unified-config-layer slot added per cversek/MacEff#96
    (Phase 1). It eliminates the prior need to bake ``MACEFF_AGENT_NAME`` into
    a shell rc file just to override a stale GECOS reading; per-project
    config travels with the repo.

    Returns:
        str: Agent identity (e.g., 'Card@abcdef') or fallback

    Examples:
        >>> get_agent_identity()
        'Card@abcdef'
    """
    # Get current user
    username = os.environ.get('USER', 'unknown')

    # Resolve display name: env > config > GECOS > username
    display_name = os.environ.get('MACEFF_AGENT_NAME')
    if not display_name:
        display_name = _get_config_identity_name()
    if not display_name:
        display_name = _get_gecos_name()
    if not display_name:
        display_name = username

    # Get UUID prefix
    uuid_prefix = _get_uuid_prefix()

    # Compose identity
    return f"{display_name}@{uuid_prefix}"


def _get_config_identity_name() -> Optional[str]:
    """Read display name from .maceff/config.json agent_identity block.

    Prefers ``calling_card`` (the short-form display name added by
    cversek/MacEff#96), falling back to ``moniker`` (the existing
    formal-name field).

    Resolution starts from the agent home base, so per-project config
    is picked up correctly. Returns None on any failure — caller will
    fall through to GECOS / username.
    """
    import json
    try:
        from macf.utils.paths import find_agent_home
        try:
            agent_home = find_agent_home()
        except ImportError:
            return None
        if agent_home is None:
            return None
        config_file = agent_home / '.maceff' / 'config.json'
        if not config_file.exists():
            return None
        try:
            with open(config_file) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"⚠️ MACF: .maceff/config.json read failed: {e}", file=sys.stderr)
            return None
        identity = data.get('agent_identity') or {}
        # Prefer calling_card (short) over moniker (formal name)
        for key in ('calling_card', 'moniker'):
            value = identity.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
    except (OSError, ImportError) as e:
        print(f"⚠️ MACF: config-based identity lookup failed: {e}", file=sys.stderr)
        return None


def _get_gecos_name() -> Optional[str]:
    """
    Extract display name from GECOS field.

    Removes spaces from GECOS field to create display name.
    Example: "Manny MacEff" -> "MannyMacEff"

    Platform-aware:
    - Linux: `getent passwd $USER` (5th colon-delimited field)
    - macOS: `id -F` (full name from Directory Services)

    Returns:
        str: Display name with spaces removed, or None if unavailable
    """
    import sys
    try:
        username = os.environ.get('USER')
        if not username:
            return None

        full_name = None

        if sys.platform == 'darwin':
            # macOS: id -F returns full name from Directory Services
            result = subprocess.run(
                ['id', '-F'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                full_name = result.stdout.strip()
        else:
            # Linux: getent passwd
            result = subprocess.run(
                ['getent', 'passwd', username],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                fields = result.stdout.strip().split(':')
                if len(fields) >= 5 and fields[4]:
                    # GECOS: comma-separated, first field is full name
                    full_name = fields[4].split(',')[0].strip()

        if not full_name:
            return None

        # Remove spaces
        display_name = full_name.replace(' ', '')
        return display_name if display_name else None

    except (OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"⚠️ MACF: agent display name detection failed: {e}", file=sys.stderr)
        return None


def _get_uuid_prefix() -> str:
    """
    Read UUID from agent identity file and return first 6 chars.

    Resolution order:
    1. {agent_home}/.maceff_primary_agent.id (per-project, via find_agent_home)
    2. ~/.maceff_primary_agent.id (global fallback)

    Returns:
        str: First 6 characters of UUID, or 'unknown' if unavailable
    """
    try:
        from macf.utils.paths import find_agent_home

        # Priority 1: Per-project identity (agent home)
        try:
            agent_home = find_agent_home()
            per_project = agent_home / '.maceff_primary_agent.id'
            if per_project.exists():
                uuid_full = per_project.read_text().strip()
                if uuid_full:
                    return uuid_full[:6]
        except ImportError:
            pass  # find_agent_home not available — fall through to global
        except (OSError, IOError) as e:
            import sys
            print(f"Warning: could not read per-project agent ID: {e}", file=sys.stderr)

        # Priority 2: Global fallback
        uuid_file = Path.home() / '.maceff_primary_agent.id'
        if not uuid_file.exists():
            return 'unknown'

        uuid_full = uuid_file.read_text().strip()
        if not uuid_full:
            return 'unknown'

        return uuid_full[:6]

    except (OSError, IOError) as e:
        import sys
        print(f"Warning: could not read agent ID: {e}", file=sys.stderr)
        return 'unknown'
