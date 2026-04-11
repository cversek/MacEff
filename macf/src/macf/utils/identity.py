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

    Resolution:
    1. Read GECOS field from getent passwd $USER (5th colon-delimited field)
    2. Read UUID from ~/.maceff_primary_agent.id
    3. Compose: {GECOS_no_spaces}@{uuid_prefix}
    4. Fallback: {username}@unknown if UUID file missing

    Returns:
        str: Agent identity (e.g., 'MannyMacEff@a3f7c2') or fallback

    Examples:
        >>> get_agent_identity()
        'MannyMacEff@a3f7c2'

        >>> # If UUID file missing
        'manny@unknown'
    """
    # Get current user
    username = os.environ.get('USER', 'unknown')

    # Get display name: MACEFF_AGENT_NAME env var > GECOS > username
    display_name = os.environ.get('MACEFF_AGENT_NAME')
    if not display_name:
        display_name = _get_gecos_name()
    if not display_name:
        display_name = username

    # Get UUID prefix
    uuid_prefix = _get_uuid_prefix()

    # Compose identity
    return f"{display_name}@{uuid_prefix}"


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
