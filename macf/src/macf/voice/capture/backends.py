"""The four things a capture unit reaches on its platform, behind interfaces (MIS-0008 R14).

The capture logic is the same everywhere. What differs by platform is how audio comes in, how
the screen's lock state is read, how the indicator is drawn, and how a key press on a declared
trigger device arrives. Each of those is a small class here; a porter writes four subclasses and
knows they are right when ``macf.voice.capture.contract`` passes them.

Every frame is 80 ms of 16 kHz mono signed 16-bit audio, as a NumPy array of FRAME samples.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Literal

import numpy as np

#: Samples per second, and per frame (80 ms): what every backend reads and every model takes.
RATE = 16000
FRAME = 1280

Screen = Literal["unlocked", "locked", "unknown"]
Mode = Literal["wake_phrase", "hold_key", "continual_voice"]


class AudioEnded(RuntimeError):
    """The microphone's stream ended or broke. The capture unit exits on it, and its daemon
    restarts it, rather than reading silence and calling it quiet."""


class AudioIn(ABC):
    """The microphone. Closed until ``open``; ``read`` blocks for one frame."""

    @abstractmethod
    def open(self) -> None:
        """Start reading the microphone."""

    @abstractmethod
    def read(self) -> np.ndarray:
        """The next frame: FRAME int16 samples. Raises AudioEnded when the stream is gone."""

    @abstractmethod
    def close(self) -> None:
        """Stop reading the microphone, so the platform shows it closed. Safe when closed."""

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """Whether the microphone is being read."""


class LockState(ABC):
    """The screen's lock state. Anything that can't be read is ``unknown``, which the channel
    treats as locked (MIS-0008 R07)."""

    @abstractmethod
    def state(self) -> Screen:
        """``unlocked``, ``locked`` or ``unknown``; never raises."""


class Indicator(ABC):
    """The on-screen sign of a recording: the agent's name, the mode, a waveform and a volume
    trace (MIS-0008 R21, R22). Shown only while recording, never while merely listening."""

    @abstractmethod
    def show(self, agent: str, mode: Mode) -> None:
        """Show the indicator for a recording that ``mode`` started, for ``agent``."""

    @abstractmethod
    def feed(self, frame: np.ndarray) -> None:
        """One recorded frame, for the waveform and the volume trace."""

    @abstractmethod
    def hide(self) -> None:
        """Hide it. Safe when hidden."""

    def window(self, left: float) -> None:
        """How much of the end window is left, 1.0 full to 0.0 empty (R56): a pause drains it and
        speech refills it, so the operator sees how long they have to go on. A backend that can't draw
        it may leave this as it is: doing nothing is allowed."""


@dataclass(frozen=True)
class KeyEvent:
    """A press or release of a declared key, read from a declared trigger device."""

    key: str
    down: bool


class TriggerSource(ABC):
    """The declared trigger devices (MIS-0008 R17). The capture unit reads them itself; no socket,
    pipe or command line can press a key for it (R18)."""

    @abstractmethod
    def poll(self) -> List[KeyEvent]:
        """The key events since the last poll, oldest first; never blocks."""

    @abstractmethod
    def close(self) -> None:
        """Release the devices."""


# ---------------------------------------------------------------- what the capture logic uses

class WakeDetector(ABC):
    """The wake model: a score for the wake phrase over the stream so far, from 0 to 1."""

    @abstractmethod
    def score(self, frame: np.ndarray) -> float:
        """Take one frame and score the stream ending with it."""

    def reset(self) -> None:
        """Forget the stream, after the microphone was closed or the unit was deaf."""


class SpeechGate(ABC):
    """Whether a frame holds speech, as opposed to noise, a tap or silence."""

    @abstractmethod
    def is_speech(self, frame: np.ndarray) -> bool:
        """Whether this frame reads as speech."""

    def reset(self) -> None:
        """Forget the state carried between frames."""


def level(frame: np.ndarray) -> float:
    """A frame's volume, 0 to 1: its RMS against full scale. What the volume trace draws."""
    x = frame.astype(np.float64) / 32768.0
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0
