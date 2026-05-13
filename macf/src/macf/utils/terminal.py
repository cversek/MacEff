"""Terminal manipulation utilities.

Currently exposes one function:

- ``set_terminal_title(title)`` — write an OSC 0 escape to set the terminal
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
    """Set the terminal window title via an OSC 0 escape sequence.

    OSC 0 sets both the icon name and the window title in one go. We chose
    OSC 0 over OSC 2 (window-title only) because empirical testing on
    Terminal.app showed OSC 2 was silently ignored while OSC 0 worked. OSC 0
    is the most broadly supported of the title-setting escapes across
    terminal emulators in practice.

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
        OSC 0 + BEL terminator is respected by Terminal.app, iTerm2, xterm,
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

    # OSC 0: set icon name AND window title. BEL terminator (universally
    # accepted). OSC 0 is empirically more reliable than OSC 2 across
    # terminal emulators (Terminal.app in particular ignores OSC 2).
    try:
        sys.stderr.write(f"\x1b]0;{cleaned}\x07")
        sys.stderr.flush()
    except (OSError, IOError, ValueError):
        # Write to closed stderr or pipe in a weird state — non-fatal.
        return False
    return True
