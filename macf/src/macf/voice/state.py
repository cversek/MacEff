"""Where an agent's voice state lives in its home: the listening switch, and the mark its speech
worker keeps while speaking (MIS-0008).

Both are files, read by the capture unit on every pass, so turning listening off takes effect
within one frame and survives a restart of the unit or the machine.
"""
import time
from pathlib import Path

#: How long after the agent's own speech the capture unit stays deaf: longer than the wake
#: check's window and any echo.
DEAF_AFTER_SPEECH_S = 3.0


def voice_dir(home: Path) -> Path:
    return Path(home) / ".maceff" / "voice"


def listen_off_path(home: Path) -> Path:
    """Present while the operator has turned listening off (``macf_tools voice listen off``)."""
    return voice_dir(home) / "listen_off"


def speaking_path(home: Path) -> Path:
    """Touched by the speech worker while it plays, so the capture unit never wakes on it (R27)."""
    return voice_dir(home) / "speaking"


#: How fresh the recording mark must be to count: the capture unit touches it every frame it records.
RECORDING_FRESH_S = 1.0


def recording_path(home: Path) -> Path:
    """Touched by the capture unit on every frame it records, so the speech worker holds (R29)."""
    return voice_dir(home) / "recording"


def mark_recording(home: Path) -> None:
    path = recording_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def recording(home: Path, now: float = None) -> bool:
    """Whether the capture unit is recording now, by how fresh its mark is."""
    try:
        touched = recording_path(home).stat().st_mtime
    except FileNotFoundError:
        return False
    return (now or time.time()) - touched < RECORDING_FRESH_S


def listening_on(home: Path) -> bool:
    return not listen_off_path(home).exists()


def speaking(home: Path, now: float = None) -> bool:
    """Whether the agent's own speech is playing, or ended too recently to trust the microphone."""
    try:
        touched = speaking_path(home).stat().st_mtime
    except FileNotFoundError:
        return False
    return (now or time.time()) - touched < DEAF_AFTER_SPEECH_S


def set_listening(home: Path, on: bool) -> None:
    path = listen_off_path(home)
    if on:
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
