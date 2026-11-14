"""What every capture backend must do, as checks a porter runs against their own (MIS-0008 R14).

Each check takes a backend (or a function making a fresh one), raises AssertionError naming the
first thing it got wrong, and returns nothing when the backend keeps its contract. The framework's
own tests run them over every backend it ships; a new platform's backends pass the same checks.

    from macf.voice.capture import contract
    contract.check_audio_in(MyMicrophone)
"""
from __future__ import annotations

import time
from typing import Callable

import numpy as np

from macf.voice.capture.backends import FRAME, AudioEnded, AudioIn, Indicator, KeyEvent, LockState, TriggerSource


def check_audio_in(make: Callable[[], AudioIn]) -> None:
    """Closed until opened; each read is one int16 frame; closing is safe twice and really closes,
    so a read after it raises AudioEnded rather than inventing silence."""
    mic = make()
    assert not mic.is_open, "a new microphone backend must start closed"
    mic.open()
    assert mic.is_open, "open() must leave the microphone open"
    for _ in range(3):
        frame = mic.read()
        assert isinstance(frame, np.ndarray), f"read() returned {type(frame).__name__}, not an ndarray"
        assert frame.dtype == np.int16, f"read() returned {frame.dtype} samples, not int16"
        assert frame.shape == (FRAME,), f"read() returned {frame.shape}, not one frame of {FRAME} samples"
    mic.close()
    mic.close()
    assert not mic.is_open, "close() must leave the microphone closed"
    try:
        mic.read()
        ended = False
    except AudioEnded:
        ended = True
    assert ended, "read() on a closed microphone must raise AudioEnded, not return audio"


def check_lock_state(backend: LockState) -> None:
    """Always one of the three values, and never an exception: what can't be read is unknown."""
    for _ in range(2):
        state = backend.state()
        assert state in ("unlocked", "locked", "unknown"), f"state() returned {state!r}"


def check_indicator(backend: Indicator) -> None:
    """Show, feed and hide in every order a capture unit uses, hide twice, and never raise."""
    frame = np.zeros(FRAME, dtype=np.int16)
    backend.hide()
    for mode in ("wake_phrase", "hold_key", "continual_voice"):
        backend.show("Tester_abc123", mode)
        for _ in range(3):
            backend.feed(frame)
        backend.hide()
    backend.hide()


def check_trigger_source(backend: TriggerSource) -> None:
    """A poll returns a list of KeyEvents at once, never blocking the capture loop; close is safe."""
    for _ in range(3):
        started = time.monotonic()
        events = backend.poll()
        assert time.monotonic() - started < 0.1, "poll() blocked; it must return at once"
        assert isinstance(events, list), f"poll() returned {type(events).__name__}, not a list"
        assert all(isinstance(e, KeyEvent) for e in events), "poll() must return KeyEvents only"
    backend.close()
