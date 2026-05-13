"""Unit tests for macf.utils.terminal.set_terminal_title.

Focused 6-test suite covering the happy path, all four safety guards
(non-TTY stdout, dumb terminal, $TERM unset, empty title), and the
defensive BEL/ESC stripping.
"""
from __future__ import annotations

import io
import sys

import pytest

from macf.utils.terminal import set_terminal_title


def _capture_stderr(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Replace sys.stderr with an in-memory buffer and return it."""
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    return buf


def _force_tty(monkeypatch: pytest.MonkeyPatch, isatty: bool) -> None:
    """Make sys.stdout.isatty() return the given value."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: isatty)


# --- Happy path -----------------------------------------------------------

def test_happy_path_writes_osc2_to_stderr(monkeypatch: pytest.MonkeyPatch):
    """Interactive TTY + sane $TERM: writes the OSC 2 escape to stderr."""
    _force_tty(monkeypatch, True)
    monkeypatch.setenv("TERM", "xterm-256color")
    buf = _capture_stderr(monkeypatch)

    ok = set_terminal_title("Hello")

    assert ok is True
    assert buf.getvalue() == "\x1b]2;Hello\x07"


# --- Safety guards (each returns False without writing) -------------------

def test_non_tty_stdout_is_noop(monkeypatch: pytest.MonkeyPatch):
    """stdout not a TTY -> no write, return False."""
    _force_tty(monkeypatch, False)
    monkeypatch.setenv("TERM", "xterm-256color")
    buf = _capture_stderr(monkeypatch)

    ok = set_terminal_title("Hello")

    assert ok is False
    assert buf.getvalue() == ""


def test_dumb_term_is_noop(monkeypatch: pytest.MonkeyPatch):
    """TERM=dumb -> no write, return False."""
    _force_tty(monkeypatch, True)
    monkeypatch.setenv("TERM", "dumb")
    buf = _capture_stderr(monkeypatch)

    ok = set_terminal_title("Hello")

    assert ok is False
    assert buf.getvalue() == ""


def test_term_unset_is_noop(monkeypatch: pytest.MonkeyPatch):
    """TERM env var missing -> no write, return False."""
    _force_tty(monkeypatch, True)
    monkeypatch.delenv("TERM", raising=False)
    buf = _capture_stderr(monkeypatch)

    ok = set_terminal_title("Hello")

    assert ok is False
    assert buf.getvalue() == ""


def test_empty_title_is_noop(monkeypatch: pytest.MonkeyPatch):
    """Empty/whitespace title -> no write, return False (even with TTY+TERM set)."""
    _force_tty(monkeypatch, True)
    monkeypatch.setenv("TERM", "xterm-256color")
    buf = _capture_stderr(monkeypatch)

    assert set_terminal_title("") is False
    assert set_terminal_title("   ") is False
    assert set_terminal_title(None) is False  # type: ignore[arg-type]
    assert buf.getvalue() == ""


# --- Defensive escaping ---------------------------------------------------

def test_strips_bel_and_esc_bytes(monkeypatch: pytest.MonkeyPatch):
    """User-supplied BEL or ESC bytes get stripped before the OSC sequence
    is built, so they can't prematurely terminate the OSC and corrupt the
    terminal state.
    """
    _force_tty(monkeypatch, True)
    monkeypatch.setenv("TERM", "xterm-256color")
    buf = _capture_stderr(monkeypatch)

    ok = set_terminal_title("evil\x07injected\x1bvalue")

    assert ok is True
    # The escape bytes (\x07 BEL and \x1b ESC) inside the title MUST NOT
    # appear in the emitted OSC sequence — only the wrapper's own BEL
    # terminator at the very end is allowed.
    emitted = buf.getvalue()
    assert emitted == "\x1b]2;evilinjectedvalue\x07"
