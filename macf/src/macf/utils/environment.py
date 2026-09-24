"""
Environment detection utilities.

Cross-platform system information detection using Python stdlib only.
"""

import json
import os
import platform
import socket
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# Key environment variables to always report in diagnostics
# These are checked explicitly and shown as "(not set)" if missing
KEY_ENV_VARS = [
    "MACF_CONTEXT_WINDOW",
    "MACEFF_AGENT_HOME_DIR",
    "MACEFF_AGENT_NAME",
    "MACEFF_ROOT_DIR",
    "MACEFF_TZ",
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


def model_display_name(model_id: str) -> str:
    """Human name for a model id: ``claude-opus-5-5`` -> ``Opus 5.5``, ``claude-haiku-4-5-20251001`` -> ``Haiku 4.5``.

    Ids that do not follow the ``claude-<family>-<major>-<minor>`` shape are returned unchanged.
    """
    import re
    base = model_id.split("[")[0]
    m = re.match(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$", base)
    if not m:
        return model_id
    family, major, minor = m.group(1).capitalize(), m.group(2), m.group(3)
    return f"{family} {major}.{minor}" if minor else f"{family} {major}"


def _model_from_transcript(path: Path) -> Optional[str]:
    """The model of the newest assistant message in a transcript, scanning backwards until one is found."""
    from .streaming import iter_lines_reverse
    for line in iter_lines_reverse(path):
        if '"assistant"' not in line or '"model"' not in line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("type") == "assistant":
            m = (data.get("message") or {}).get("model")
            if m and not m.startswith("<"):
                return m
    return None


def current_model(session_id: Optional[str] = None) -> Dict[str, str]:
    """The model this agent is running, as ``{"id", "display", "source"}``. The one place MACF answers this.

    Sources, in order: ``ANTHROPIC_MODEL`` (an explicit override); the newest assistant message in this
    session's transcript; the newest assistant message in the most recently written transcript of the same
    project (source ``last seen``: a new session has no reply of its own yet). ``unknown`` when none answers.
    Never raises.
    """
    from .session import get_current_session_id
    from .paths import get_session_transcript_path

    def result(mid: str, source: str) -> Dict[str, str]:
        return {"id": mid, "display": model_display_name(mid), "source": source}

    env = os.environ.get("ANTHROPIC_MODEL")
    if env:
        return result(env, "ANTHROPIC_MODEL")
    try:
        sid = session_id or get_current_session_id()
        path = Path(get_session_transcript_path(sid)) if sid and sid != "unknown" else None
        if path and path.exists():
            mid = _model_from_transcript(path)
            if mid:
                return result(mid, "transcript")
        folder = path.parent if path else None
        if folder and folder.is_dir():
            others = sorted((p for p in folder.glob("*.jsonl") if p != path), key=lambda p: p.stat().st_mtime, reverse=True)
            for other in others[:3]:
                mid = _model_from_transcript(other)
                if mid:
                    return result(mid, "last seen")
    except (OSError, ValueError, TypeError) as e:
        print(f"⚠️ MACF: model detection failed: {e}", file=sys.stderr)
    return {"id": "unknown", "display": "unknown", "source": "none"}


def detect_model(session_id: Optional[str] = None) -> str:
    """Model id of the running agent, or 'unknown'. Kept for callers that want the bare id; see current_model()."""
    return current_model(session_id)["id"]
