"""
Formatting utilities.
"""

import subprocess
from functools import lru_cache

import sys

try:
    from importlib.metadata import version
    __version__ = version("macf")
except (ImportError, Exception) as e:
    __version__ = "0.0.0-dev"  # Fallback for development

from .environment import get_rich_environment_string


@lru_cache(maxsize=1)
def get_claude_code_version() -> str:
    """
    Get Claude Code version using multi-strategy detection.

    Cached to avoid repeated subprocess calls (hooks may call this multiple times per session).

    Strategies (in order):
    0. MACF_CC_VERSION env var (explicit override — required for Mac alias-launched CC)
    1. Linux: Read /proc/PPID/cmdline to find the actual CC binary, extract version from it
    2. Auto-updater filename: ~/.local/share/claude/versions/X.Y.Z (version is the filename)
    3. Binary content: Read shutil.which("claude") resolved target for version pattern
    4. Direct binary: Try `claude --version` (may find stale global install)

    Returns:
        Version string (e.g., "2.1.32") or empty string if unavailable.
    """
    import os
    import platform
    import re

    # Strategy 0: Explicit env var override (highest priority)
    # Required for Mac when CC is launched via alias (e.g., claude-2.1.86)
    # because Mac provides no way to trace the running binary from a subprocess.
    env_version = os.environ.get("MACF_CC_VERSION")
    if env_version:
        return env_version

    def _parse_version(output: str) -> str:
        """Extract version from 'X.Y.Z (Claude Code)' format."""
        output = output.strip()
        return output.split()[0] if output else ""

    def _extract_version_from_script(script_path: str) -> str:
        """Extract version from a self-contained CC node script by grepping its content."""
        try:
            with open(script_path, 'r', errors='ignore') as f:
                # Read first 500KB (version is near the top of the bundle)
                content = f.read(512_000)
            # Look for the version constant pattern in the esbuild bundle
            # Common patterns: version:"2.1.32" or VERSION="2.1.32"
            match = re.search(r'(?:displayName\s*=\s*"Claude Code".*?version\s*[:=]\s*"(\d+\.\d+\.\d+)")', content, re.DOTALL)
            if match:
                return match.group(1)
            # Fallback: look for version pattern near "Claude Code" string
            match = re.search(r'"(\d+\.\d+\.\d+)\s*\(Claude Code\)"', content)
            if match:
                return match.group(1)
        except OSError as e:
            print(f"⚠️ MACF: failed to read claude script for version extraction: {e}", file=sys.stderr)
        return ""

    # Strategy 1: Linux — read /proc/PPID/cmdline
    if platform.system() == "Linux":
        try:
            ppid = os.getppid()
            cmdline_path = f"/proc/{ppid}/cmdline"
            with open(cmdline_path, 'rb') as f:
                cmdline = f.read()
            args = cmdline.split(b'\x00')
            # Find the claude script path (typically argv[1] after node)
            for arg in args:
                arg_str = arg.decode('utf-8', errors='ignore')
                if 'claude' in arg_str.lower() and os.path.isfile(arg_str):
                    version = _extract_version_from_script(arg_str)
                    if version:
                        return version
                    # Try running the specific binary
                    result = subprocess.run(
                        [arg_str, "--version"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        return _parse_version(result.stdout)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"⚠️ MACF: Linux /proc-based claude version detection failed: {e}", file=sys.stderr)

    # Strategy 2: Extract version from the claude binary file content
    # The claude binary is a self-contained node script with version embedded.
    # This avoids executing it (which could trigger npx downloads or TTY issues).
    import shutil
    claude_path = shutil.which("claude")
    if claude_path:
        version = _extract_version_from_script(claude_path)
        if version:
            return version

    # Strategy 3: Direct binary (may find stale global install)
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return _parse_version(result.stdout)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"⚠️ MACF: direct claude --version failed: {e}", file=sys.stderr)

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


def format_proprioception_awareness() -> str:
    """Format CLI capabilities and environment for hook injection.

    Answers: "What can I do?" and "Where am I?"
    Injects --help, cmd-tree, and env outputs with stimulating visual boundaries.
    """
    sections = []

    # 1. Top-level help
    try:
        help_result = subprocess.run(
            ["macf_tools", "--help"],
            capture_output=True, text=True, timeout=5
        )
        if help_result.returncode == 0:
            sections.append(f"""╔══════════════════════════════════════════════════════════════════╗
║  🔧 WHAT CAN I DO? - CLI Overview                                ║
╚══════════════════════════════════════════════════════════════════╝

{help_result.stdout.strip()}""")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"⚠️ MACF: macf_tools --help failed during proprioception: {e}", file=sys.stderr)

    # 2. Command tree
    try:
        tree_result = subprocess.run(
            ["macf_tools", "cmd-tree"],
            capture_output=True, text=True, timeout=10
        )
        if tree_result.returncode == 0:
            sections.append(f"""╔══════════════════════════════════════════════════════════════════╗
║  🌳 COMMAND TREE - Full Capability Map                           ║
╚══════════════════════════════════════════════════════════════════╝

{tree_result.stdout.strip()}""")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"⚠️ MACF: macf_tools cmd-tree failed during proprioception: {e}", file=sys.stderr)

    # 3. Environment
    try:
        env_result = subprocess.run(
            ["macf_tools", "env"],
            capture_output=True, text=True, timeout=5
        )
        if env_result.returncode == 0:
            sections.append(f"""╔══════════════════════════════════════════════════════════════════╗
║  📍 WHERE AM I? - Environment State                              ║
╚══════════════════════════════════════════════════════════════════╝

{env_result.stdout.strip()}""")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"⚠️ MACF: macf_tools env failed during proprioception: {e}", file=sys.stderr)

    return "\n\n".join(sections)
