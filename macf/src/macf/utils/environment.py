"""
Environment detection utilities.

Cross-platform system information detection using Python stdlib only.
"""

import os
import platform
import socket
import sys
from pathlib import Path
from typing import Dict, Tuple

# Key environment variables to always report in diagnostics
# These are checked explicitly and shown as "(not set)" if missing
KEY_ENV_VARS = [
    "MACEFF_AGENT_HOME_DIR",
    "MACEFF_TZ",
    "MACF_AGENT",
    "BASH_ENV",
    "CLAUDECODE",
    "CLAUDE_PROJECT_DIR",
    "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR",
    "TZ",
]

# Prefixes for dynamic env var discovery (additional vars beyond KEY_ENV_VARS)
ENV_VAR_PREFIXES = ("MACEFF_", "MACF_", "CLAUDE")


def get_env_var_report() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Get environment variables for diagnostic reporting.

    Returns:
        Tuple of (key_vars, extra_vars):
        - key_vars: Dict of KEY_ENV_VARS with values or "(not set)"
        - extra_vars: Dict of additional matching vars that are set
    """
    # Key vars always reported
    key_vars = {}
    for k in KEY_ENV_VARS:
        key_vars[k] = os.getenv(k, "(not set)")

    # Extra vars matching prefixes but not in key list
    extra_vars = {
        k: v for k, v in sorted(os.environ.items())
        if k.startswith(ENV_VAR_PREFIXES) and k not in KEY_ENV_VARS
    }

    return key_vars, extra_vars


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
    # Catch all exceptions to ensure "never crashes" guarantee
    try:
        hostname = socket.gethostname()
    except Exception as e:
        print(f"⚠️ MACF: Hostname detection failed: {e}", file=sys.stderr)
        hostname = "unknown-host"

    try:
        os_name = platform.system()  # "Darwin", "Linux", "Windows"
    except Exception as e:
        print(f"⚠️ MACF: OS detection failed: {e}", file=sys.stderr)
        os_name = "Unknown"

    try:
        # platform.release() gives kernel version on Mac/Linux, Windows version on Windows
        os_version = platform.release()
    except Exception as e:
        print(f"⚠️ MACF: OS version detection failed: {e}", file=sys.stderr)
        os_version = "unknown"

    # Compose rich string
    return f"{base_env} - {hostname} {os_name} {os_version}"
