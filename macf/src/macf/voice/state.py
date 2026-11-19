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


def _host(name: str) -> Path:
    """A mark every agent on this system shares, in the daemon runtime directory (R27, R29 as revised)."""
    from macf.pd.names import runtime_dir
    return runtime_dir() / name


def host_speaking_path() -> Path:
    return _host("voice-speaking")


def host_recording_path() -> Path:
    return _host("voice-recording")


def _fresh(path: Path, within_s: float, now: float = None) -> bool:
    try:
        touched = path.stat().st_mtime
    except FileNotFoundError:
        return False
    return (now or time.time()) - touched < within_s


def _touch(*paths: Path) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def speaking_path(home: Path) -> Path:
    """Touched by the speech worker while it plays, so the capture unit never wakes on it (R27)."""
    return voice_dir(home) / "speaking"


#: How fresh the recording mark must be to count: the capture unit touches it every frame it records.
RECORDING_FRESH_S = 1.0


def recording_path(home: Path) -> Path:
    """Touched by the capture unit on every frame it records, so the speech worker holds (R29)."""
    return voice_dir(home) / "recording"


def mark_recording(home: Path) -> None:
    """Mark this agent's recording, and the system's: any agent's speech holds while it records (R29)."""
    _touch(recording_path(home), host_recording_path())


def recording(home: Path, now: float = None) -> bool:
    """Whether a capture unit on this system is recording now, this agent's or another's (R29)."""
    return (_fresh(recording_path(home), RECORDING_FRESH_S, now)
            or _fresh(host_recording_path(), RECORDING_FRESH_S, now))


def listening_on(home: Path) -> bool:
    return not listen_off_path(home).exists()


def speaking(home: Path, now: float = None) -> bool:
    """Whether any agent's speech on this system is playing, or ended too recently to trust the
    microphone (R27 as revised: a capture unit never wakes on any speech of its system)."""
    return (_fresh(speaking_path(home), DEAF_AFTER_SPEECH_S, now)
            or _fresh(host_speaking_path(), DEAF_AFTER_SPEECH_S, now))


def set_listening(home: Path, on: bool) -> None:
    path = listen_off_path(home)
    if on:
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
