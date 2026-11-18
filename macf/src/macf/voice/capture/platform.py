"""This platform's capture backends, chosen in one place (MIS-0008 R14; docs/VOICE_PORTING.md section 3).

Each platform's modules are imported inside its own branch, so one platform's code never loads on another.
"""
from __future__ import annotations

import sys
from typing import Callable, Sequence


def backends(trigger_devices: Sequence[str] = ()) -> dict:
    """audio, lock and indicator for this machine, and ``triggers`` for the declared devices (None when none
    are declared; the caller puts its NoKeys there)."""
    if sys.platform.startswith("linux"):
        from macf.voice.capture.linux import EvdevTriggers, LinuxLockState, OverlayIndicator, PipeWireAudio
        return dict(audio=PipeWireAudio(), lock=LinuxLockState(), indicator=OverlayIndicator(),
                    triggers=EvdevTriggers(trigger_devices) if trigger_devices else None)
    if sys.platform == "darwin":
        from macf.voice.capture.macos import MacAudioIn, MacIndicator, MacLockState
        triggers = None
        if trigger_devices:
            from macf.voice.capture.macos import MacTriggers
            triggers = MacTriggers(trigger_devices)
        return dict(audio=MacAudioIn(), lock=MacLockState(), indicator=MacIndicator(), triggers=triggers)
    raise RuntimeError("this platform has no capture backends yet; docs/VOICE_PORTING.md says what to write (MIS-0008 R14)")


def microphone():
    """This machine's microphone alone, for a command that records on the operator's word (``voice wake record``)."""
    if sys.platform.startswith("linux"):
        from macf.voice.capture.linux import PipeWireAudio
        return PipeWireAudio()
    if sys.platform == "darwin":
        from macf.voice.capture.macos import MacAudioIn
        return MacAudioIn()
    raise RuntimeError("this platform has no microphone backend yet; docs/VOICE_PORTING.md says what to write (MIS-0008 R14)")


def lock_state() -> Callable[[], str] | None:
    """The screen's lock state reader for the speech worker, or None where none is written."""
    if sys.platform.startswith("linux"):
        from macf.voice.capture.linux import LinuxLockState
        return LinuxLockState().state
    if sys.platform == "darwin":
        from macf.voice.capture.macos import MacLockState
        return MacLockState().state
    return None
