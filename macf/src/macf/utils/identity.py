"""
Agent identity utilities for MACF.

Provides functions to get agent identity information combining
display name (from GECOS) and UUID.
"""

import os
import subprocess
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

    # Get display name from GECOS
    display_name = _get_gecos_name()
    if not display_name:
        display_name = username

    # Get UUID prefix
    uuid_prefix = _get_uuid_prefix()

    # Compose identity
    return f"{display_name}@{uuid_prefix}"


def _get_gecos_name() -> Optional[str]:
    """
    Extract display name from GECOS field (5th field in passwd).

    Removes spaces from GECOS field to create display name.
    Example: "Manny MacEff" -> "MannyMacEff"

    Returns:
        str: Display name with spaces removed, or None if unavailable
    """
    try:
        username = os.environ.get('USER')
        if not username:
            return None

        # Use getent to get passwd entry
        result = subprocess.run(
            ['getent', 'passwd', username],
            capture_output=True,
            text=True,
            timeout=2
        )

        if result.returncode != 0:
            return None

        # Parse passwd line: username:x:uid:gid:gecos:home:shell
        fields = result.stdout.strip().split(':')
        if len(fields) < 5:
            return None

        gecos = fields[4]
        if not gecos:
            return None

        # GECOS may have comma-separated fields (full name, room, work phone, etc.)
        # Take first field (full name)
        full_name = gecos.split(',')[0].strip()

        # Remove spaces
        display_name = full_name.replace(' ', '')

        return display_name if display_name else None

    except Exception:
        return None


def _get_uuid_prefix() -> str:
    """
    Read UUID from ~/.maceff_primary_agent.id and return first 6 chars.

    Returns:
        str: First 6 characters of UUID, or 'unknown' if unavailable
    """
    try:
        uuid_file = Path.home() / '.maceff_primary_agent.id'
        if not uuid_file.exists():
            return 'unknown'

        uuid_full = uuid_file.read_text().strip()
        if not uuid_full:
            return 'unknown'

        # Return first 6 characters
        return uuid_full[:6]

    except Exception:
        return 'unknown'
