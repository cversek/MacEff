"""The capture backends for macOS (MIS-0008 R14; docs/VOICE_PORTING.md section 6).

Each keeps the promise its interface in ``backends`` makes, checked by ``contract``. The
microphone and the screen belong to the console user's login session on a Mac, so these run
in that session: a capture unit started outside it (over ssh, or as a system daemon) gets no
microphone and reads the screen as ``unknown``.
"""
from __future__ import annotations

import sys
from typing import Any, Callable, Optional

import numpy as np

from macf.voice.capture.backends import FRAME, RATE, AudioEnded, AudioIn, LockState, Screen


def _open_stream():
    """The default input as a 16 kHz mono int16 stream, read one frame at a time; Core Audio resamples."""
    import sounddevice
    stream = sounddevice.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME)
    stream.start()
    return stream


class MacAudioIn(AudioIn):
    """The default microphone through PortAudio (``sounddevice``), read in memory only (R13).

    Opening starts the stream and closing stops and closes it, so the orange microphone dot in
    the menu bar agrees with the capture unit: off really means not read (R15). The first open
    asks macOS for the microphone permission on behalf of the process that runs the unit.
    """

    def __init__(self) -> None:
        self._stream: Optional[Any] = None
        self.overflows = 0

    def open(self) -> None:
        if self._stream is not None:
            return
        try:
            self._stream = _open_stream()
        except (OSError, ImportError) as e:   # sounddevice raises PortAudioError, an OSError subclass
            raise AudioEnded(f"the microphone can't be opened: {e}") from e

    def read(self) -> np.ndarray:
        if self._stream is None:
            raise AudioEnded("the microphone is closed")
        try:
            raw, overflowed = self._stream.read(FRAME)
        except OSError as e:
            raise AudioEnded(f"the microphone's stream broke: {e}") from e
        if overflowed:
            self.overflows += 1
            if self.overflows == 1:
                print("⚠️ MACF: voice: the microphone overflowed (frames were lost while the unit was busy); "
                      "counting further ones in MacAudioIn.overflows", file=sys.stderr)
        frame = np.frombuffer(bytes(raw), dtype=np.int16).copy()
        if frame.shape != (FRAME,):
            raise AudioEnded(f"the microphone returned {frame.size} samples, not a frame of {FRAME}")
        return frame

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.stop()
            stream.close()
        except OSError as e:
            print(f"⚠️ MACF: voice: closing the microphone failed ({e}); it may still be open", file=sys.stderr)

    @property
    def is_open(self) -> bool:
        return self._stream is not None


def _session_dictionary() -> Optional[dict]:
    import Quartz
    found = Quartz.CGSessionCopyCurrentDictionary()
    return dict(found) if found is not None else None


class MacLockState(LockState):
    """From Quartz's session dictionary: locked while ``CGSSessionScreenIsLocked`` is set or the
    session is not on the console (another user switched in); unlocked only when the session is on
    the console and the lock key is absent; unknown otherwise, which R07 treats as locked."""

    def __init__(self, read: Callable[[], Optional[dict]] = _session_dictionary) -> None:
        self._read = read

    def state(self) -> Screen:
        try:
            session = self._read()
        except Exception as e:  # noqa: BLE001 - R07: any failure to read is "unknown", said once per call
            print(f"⚠️ MACF: voice: the screen's lock state can't be read ({e}); treating it as unknown",
                  file=sys.stderr)
            return "unknown"
        if not session:
            return "unknown"
        if session.get("CGSSessionScreenIsLocked"):
            return "locked"
        on_console = session.get("kCGSSessionOnConsoleKey")
        if on_console is None:
            return "unknown"
        return "unlocked" if on_console else "locked"


def MacIndicator(settle_s: float = 1.0):
    """The indicator as its own AppKit process (``indicator_overlay_macos.py``) under this Python, which
    carries PyObjC; fed the same JSON lines as the Linux overlay, so the Linux driver class serves both."""
    import importlib.util
    from pathlib import Path

    from macf.voice.capture.linux import OverlayIndicator
    overlay = Path(importlib.util.find_spec("macf.voice.indicator_overlay_macos").origin)
    return OverlayIndicator(python=sys.executable, overlay=overlay, settle_s=settle_s, preload=None)
