"""Terminal manipulation utilities.

Currently exposes one function:

- ``set_terminal_title(title)`` — write an OSC 2 escape to set the terminal
  window title (e.g. so multi-agent terminal layouts can be told apart at a
  glance).

Future utilities for cursor manipulation, color handling, or alternate-screen
mode would live here too. Kept deliberately small for now.
"""
from __future__ import annotations

import os
import sys

__all__ = ["set_terminal_title"]


def set_terminal_title(title: str) -> bool:
    """Set the terminal window title via an OSC 2 escape sequence.

    The escape is written to ``sys.stderr`` (never stdout) so it does not
    contaminate downstream data pipelines such as
    ``macf_tools env set-term-title "foo" | jq ...``.

    Args:
        title: The window title. BEL (``\\x07``) and ESC (``\\x1b``) bytes are
            stripped defensively before emission because either would
            prematurely terminate the OSC sequence. Empty/whitespace-only
            titles are treated as no-ops.

    Returns:
        True if the escape was actually written, False if any safety guard
        tripped (output not a TTY, ``$TERM`` is unset or ``dumb``, or title
        is empty after stripping).

    Terminal support:
        OSC 2 + BEL terminator is respected by Terminal.app, iTerm2, xterm,
        gnome-terminal / Konsole / other VTE-based terminals, Windows Terminal
        and VS Code's integrated terminal. Plain ``ssh`` sessions pass the
        sequence through.

        Tmux passthrough is NOT auto-wrapped in DCS. Inside tmux, use
        ``tmux set-option -g set-titles on`` and tmux will manage the host
        terminal's title via its own configuration. Direct DCS wrapping
        (``\\x1bPtmux;...\\x1b\\\\``) is deferred until a user needs it.
    """
    if title is None:
        return False
    # Strip OSC-terminating bytes defensively, then check emptiness.
    cleaned = title.replace("\x07", "").replace("\x1b", "").strip()
    if not cleaned:
        return False

    # Guard: output must be an interactive terminal.
    try:
        if not sys.stdout.isatty():
            return False
    except (AttributeError, ValueError):
        # ValueError: I/O operation on closed file. Treat as non-TTY.
        return False

    # Guard: $TERM must be set and not "dumb".
    term = os.environ.get("TERM")
    if not term or term == "dumb":
        return False

    # OSC 2: set window title only. BEL terminator (universally accepted).
    try:
        sys.stderr.write(f"\x1b]2;{cleaned}\x07")
        sys.stderr.flush()
    except (OSError, IOError, ValueError):
        # Write to closed stderr or pipe in a weird state — non-fatal.
        return False
    return True
