"""
Formatting utilities.
"""

import subprocess
from functools import lru_cache

try:
    from importlib.metadata import version
    __version__ = version("macf")
except Exception:
    __version__ = "0.0.0-dev"  # Fallback for development

from .environment import get_rich_environment_string


@lru_cache(maxsize=1)
def get_claude_code_version() -> str:
    """
    Get Claude Code version via `claude --version`.

    Cached to avoid repeated subprocess calls (hooks may call this multiple times per session).

    Returns:
        Version string (e.g., "2.0.62") or empty string if unavailable.

    Note:
        This assumes `claude` command is available in PATH. If user runs CC via
        a different command/alias, this still works as long as `claude` resolves
        to some CC installation.
    """
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Output format: "2.0.62 (Claude Code)" - extract version number
            output = result.stdout.strip()
            # Take first whitespace-delimited token
            version_str = output.split()[0] if output else ""
            return version_str
        return ""
    except Exception:
        return ""


def format_macf_footer() -> str:
    """
    Standard MACF attribution footer with shortened tag.

    Uses importlib.metadata.version("macf") - single source of truth from pyproject.toml.
    Includes Claude Code version if available via `claude --version`.
    Gets rich environment string automatically (no parameter needed).

    Returns:
        ```
        ---
        🏗️ MACF Tools {__version__} | Claude Code {cc_version}
        Environment: {rich_environment}
        ```

        Or without CC version if unavailable:
        ```
        ---
        🏗️ MACF Tools {__version__} (Multi-Agent Coordination Framework)
        Environment: {rich_environment}
        ```
    """
    environment = get_rich_environment_string()
    cc_version = get_claude_code_version()

    if cc_version:
        version_line = f"🏗️ MACF Tools {__version__} | Claude Code {cc_version}"
    else:
        version_line = f"🏗️ MACF Tools {__version__} (Multi-Agent Coordination Framework)"

    return f"""---
{version_line}
Environment: {environment}"""
