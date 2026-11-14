"""The tray's Attach item: a terminal window attached to one agent's session (cversek/MacEff#726).

A restart of the session unit ends the tmux server an operator was attached to, so the
operator needs a quick way back in. The window runs ``harness attach --card``, which finds
the session from the agent's own daemon, so the tray holds no knowledge of tmux at all.

The tray only opens the window, which the operator then uses. It never types into a session
(MIS-0002-R71 (tray_MUST-NOT_type_into_session)).

The window comes from ``open`` on a ``.command`` file. Driving iTerm2 or Terminal through
AppleScript would raise the Automation permission dialog, and ``open`` needs no grant.
iTerm2 speaks tmux control mode, so it gets ``--control``. Terminal does not, and control
mode there prints the raw protocol, so it gets ``--no-control``.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

#: Where iTerm2 installs. Its presence decides the window and the mode.
ITERM = Path("/Applications/iTerm.app")


def attach_script(card: str, python: str, control: bool) -> str:
    """The ``.command`` file's text: attach to ``card``'s session with this interpreter's macf."""
    argv = [python, "-m", "macf.cli", "harness", "attach", "--card", card,
            "--control" if control else "--no-control"]
    return "#!/bin/sh\n# Written by the MacEff tray's Attach item.\nexec " + shlex.join(argv) + "\n"


def _script_name(card: str) -> str:
    """A file name for ``card``'s script that the card's own characters can't steer."""
    return "attach-" + re.sub(r"[^A-Za-z0-9._-]", "-", card) + ".command"


def open_attach(card: str, *, directory: Optional[Path] = None, python: str = sys.executable,
                iterm: Path = ITERM, run: Callable = subprocess.run) -> dict:
    """Write ``card``'s attach script into this user's private directory and open it in a
    terminal window. Returns ``ok``, the script's path, and an error when it could not be
    written or opened. Every failure comes back as that error, never as an exception, so the
    menu can say it: a runtime directory others can write is refused, and so is a link at
    the script's temporary path, which is never written through."""
    control = iterm.is_dir()
    try:
        if directory is None:
            from macf.utils.paths import user_runtime_dir
            directory = user_runtime_dir() / "tray"
        directory = Path(directory)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        script = directory / _script_name(card)
        tmp = script.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o700)
        with os.fdopen(fd, "w") as f:
            f.write(attach_script(card, python, control))
        os.chmod(tmp, 0o700)
        os.replace(tmp, script)
    except OSError as e:
        return {"ok": False, "script": None, "error": f"the attach script could not be written: {e}"}
    app = str(iterm) if control else "Terminal"
    try:
        done = run(["open", "-a", app, str(script)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "script": str(script), "error": f"open failed: {e}"}
    if done.returncode != 0:
        return {"ok": False, "script": str(script),
                "error": (done.stderr or done.stdout or f"open exited {done.returncode}").strip()}
    return {"ok": True, "script": str(script)}
