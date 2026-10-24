"""Which build of macf a process runs, and how to read a daemon that is older than its CLI.

A primal daemon keeps the code it started with until its unit restarts, while the CLI that asks
it runs whatever the checkout holds now. When the two drift, a verb the daemon doesn't know used
to fail with its request parser's message, passed straight through. These helpers name the
build each side runs, so ``pd status`` can say when they differ, and turn that parser message
into what it means (MacEff #816).
"""
import re
import subprocess
from pathlib import Path
from typing import Optional

#: How pydantic words a request whose ``op`` no member of the union names.
_UNKNOWN_OP = re.compile(r"Input tag '([A-Za-z0-9_]+)' found using 'op' does not match any of the expected tags")

#: What to do about it, said with the refusal (persistent_layer 6.2).
UPDATE_HINT = ("update it: `macf_tools pd install --force`, then restart the daemon's unit. A restart "
               "carries its running units, so the session keeps running; only what loads with the session, "
               "such as the MacEff channel, needs a session restart")


def build_id(package_dir: Optional[Path] = None) -> str:
    """``macf <version>``, with the commit when the package runs from a git checkout."""
    try:
        from importlib.metadata import version
        ver = version("macf")
    except Exception:  # noqa: BLE001 - an unknown version is still a build to name
        ver = "unknown"
    if package_dir is None:
        import macf
        package_dir = Path(macf.__file__).resolve().parent
    here = Path(package_dir)
    try:
        out = subprocess.run(["git", "-C", str(here), "rev-parse", "--short=8", "HEAD"],
                             capture_output=True, text=True, timeout=2)
        commit = out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        commit = ""
    return f"macf {ver} at {commit}" if commit else f"macf {ver}"


def unknown_verb(error: Optional[str]) -> Optional[str]:
    """The request op a daemon refused because it doesn't know it, or None."""
    m = _UNKNOWN_OP.search(error or "")
    return m.group(1) if m else None
