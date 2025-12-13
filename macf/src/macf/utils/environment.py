"""
Environment detection utilities.

Cross-platform system information detection using Python stdlib only.
"""

import os
import platform
import socket
from pathlib import Path


def detect_execution_environment() -> str:
    """
    Detect where MACF tools are running.

    Returns:
        One of:
        - "MacEff Container (username)" - if /.dockerenv exists
        - "MacEff Host System" - if project has MacEff markers
        - "Host System" - generic host
    """
    # Check for container environment
    if Path("/.dockerenv").exists():
        # Read username from environment
        username = os.environ.get("MACEFF_USER") or os.environ.get("USER") or "unknown"
        return f"MacEff Container ({username})"

    # Check if running in MacEff project on host
    cwd = Path.cwd()
    current = cwd

    # Walk up directory tree looking for MacEff markers
    while current != current.parent:
        if "MacEff" in current.name:
            return "MacEff Host System"
        current = current.parent

    # Generic host fallback
    return "Host System"


def get_rich_environment_string() -> str:
    """
    Get rich environment string with hostname and OS/kernel version details.

    Uses Python stdlib for cross-platform compatibility (Mac, Linux, Windows).
    Composition pattern - builds on detect_execution_environment().

    Returns:
        Formatted string like:
        - "Host System - hostname Darwin 24.5.0"
        - "MacEff Host System - hostname Linux 5.15.0"
        - "MacEff Container (user) - hostname Linux 6.2.0"

    Never crashes - graceful fallback on any failure.
    """
    # Get base environment
    base_env = detect_execution_environment()

    # Gather system details with safe fallbacks
    try:
        hostname = socket.gethostname()
    except (socket.error, OSError) as e:
        import sys
        print(f"⚠️ MACF: Hostname detection failed: {e}", file=sys.stderr)
        hostname = "unknown-host"

    try:
        os_name = platform.system()  # "Darwin", "Linux", "Windows"
    except OSError as e:
        import sys
        print(f"⚠️ MACF: OS detection failed: {e}", file=sys.stderr)
        os_name = "Unknown"

    try:
        # platform.release() gives kernel version on Mac/Linux, Windows version on Windows
        os_version = platform.release()
    except OSError as e:
        import sys
        print(f"⚠️ MACF: OS version detection failed: {e}", file=sys.stderr)
        os_version = "unknown"

    # Compose rich string
    return f"{base_env} - {hostname} {os_name} {os_version}"
