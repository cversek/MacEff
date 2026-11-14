"""Stand-in backends for the capture unit's tests: a scripted microphone, a recording indicator,
key events pushed by the test, and models that read markers planted in the frames.

A frame's content says what it is: SILENCE is all zeros, SPEECH a loud tone, and WAKE a loud tone
the fake wake model scores as the phrase. Time is the count of frames read, 80 ms each.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

from macf.voice.capture.backends import (FRAME, RATE, AudioEnded, AudioIn, Indicator, KeyEvent, LockState,
                                         SpeechGate, TriggerSource, WakeDetector)
from macf.voice.capture.unit import CaptureConfig, CaptureUnit, InlineExecutor

FRAME_S = FRAME / RATE
WAKE_MARK = 7001
SPEECH_MARK = 5003
#: Scored as the phrase by the fake wake model, but too quiet for the speech gate: a fire on noise.
QUIET_WAKE_MARK = 51

SILENCE = np.zeros(FRAME, dtype=np.int16)
SPEECH = np.full(FRAME, SPEECH_MARK, dtype=np.int16)
WAKE = np.full(FRAME, WAKE_MARK, dtype=np.int16)
QUIET_WAKE = np.full(FRAME, QUIET_WAKE_MARK, dtype=np.int16)
#: The phrase in another voice: the wake model fires on it, the fake voice lock does not match it.
OTHER_VOICE_MARK = 7003
OTHER_WAKE = np.full(FRAME, OTHER_VOICE_MARK, dtype=np.int16)


def secs(seconds: float) -> int:
    """Frames in ``seconds``."""
    return max(1, round(seconds / FRAME_S))


class FakeAudio(AudioIn):
    """Plays a script of frames; silence once it runs out, unless ``end`` says the stream ends."""

    def __init__(self, script: Optional[List[np.ndarray]] = None, end: bool = False):
        self.script = list(script or [])
        self.end = end
        self._open = False
        self.reads = 0
        self.opens = 0

    def open(self) -> None:
        self._open = True
        self.opens += 1

    def read(self) -> np.ndarray:
        if not self._open:
            raise AudioEnded("the microphone is closed")
        self.reads += 1
        if self.script:
            return self.script.pop(0)
        if self.end:
            raise AudioEnded("the script ended")
        return SILENCE.copy()

    def close(self) -> None:
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def then(self, *chunks) -> "FakeAudio":
        """Append frames: each chunk is (frame, count)."""
        for frame, count in chunks:
            self.script.extend([frame] * count)
        return self


class FakeLock(LockState):
    def __init__(self, screen="unlocked"):
        self.screen = screen

    def state(self):
        return self.screen


class RecordingIndicator(Indicator):
    """Keeps every call, in order, so a test reads exactly what was shown."""

    def __init__(self):
        self.calls: List[tuple] = []
        self.windows: List[float] = []
        self.shown: Optional[tuple] = None

    def show(self, agent, mode):
        self.calls.append(("show", agent, mode))
        self.shown = (agent, mode)

    def feed(self, frame):
        self.calls.append(("feed",))

    def hide(self):
        self.calls.append(("hide",))
        self.shown = None

    def window(self, left):
        self.windows.append(left)


class PushedKeys(TriggerSource):
    def __init__(self):
        self.queue: List[KeyEvent] = []
        self.closed = False

    def press(self, key):
        self.queue.append(KeyEvent(key, True))

    def release(self, key):
        self.queue.append(KeyEvent(key, False))

    def poll(self):
        out, self.queue = self.queue, []
        return out

    def close(self):
        self.closed = True


class MarkerDetector(WakeDetector):
    def __init__(self):
        self.scored = 0

    def score(self, frame):
        self.scored += 1
        return 1.0 if frame[0] in (WAKE_MARK, QUIET_WAKE_MARK, OTHER_VOICE_MARK) else 0.0


class LoudGate(SpeechGate):
    """Speech is any loud frame, the wake phrase included."""

    def is_speech(self, frame):
        return int(np.abs(frame).max()) > 1000


class ScriptedTranscriber:
    """Says what the test scripts, in order of calls, and keeps what it was asked."""

    def __init__(self, *texts: str):
        self.texts = list(texts)
        self.calls: List[tuple] = []

    def __call__(self, audio, prompt):
        self.calls.append((audio, prompt))
        return self.texts.pop(0) if self.texts else ""


def make_unit(audio: FakeAudio, transcriber: ScriptedTranscriber, *, phrase="yo tom", hold="KEY_F9",
              toggle="KEY_F10", listening_on: Callable[[], bool] = lambda: True,
              speaking: Callable[[], bool] = lambda: False, screen="unlocked", speaker=None,
              on_voice_event=None, guard_lowered=None, **config) -> "Rig":
    # These tests script their silences and transcripts: the short end window and no stop-word checks,
    # unless a test asks for them (R56 has tests of its own).
    config = {"end_silence_s": 1.2, "end_hold_s": 0.5, "stop_words": False, **config}
    delivered = []
    keys = PushedKeys()
    indicator = RecordingIndicator()
    unit = CaptureUnit(CaptureConfig(agent="Tester_abc123", wake_phrase=phrase, hold_key=hold, toggle_key=toggle,
                                     **config),
                       audio=audio, lock=FakeLock(screen), indicator=indicator, triggers=keys, gate=LoudGate(),
                       transcribe=transcriber, deliver=delivered.append, detector=MarkerDetector(),
                       listening_on=listening_on, speaking=speaking,
                       clock=lambda: audio.reads * FRAME_S, wall=lambda: 1794600000.0 + audio.reads * FRAME_S,
                       executor=InlineExecutor(), speaker=speaker,
                       on_voice_event=on_voice_event or (lambda kind, data: None),
                       guard_lowered=guard_lowered or (lambda: False))
    return Rig(unit=unit, keys=keys, indicator=indicator, delivered=delivered, audio=audio)


@dataclass(frozen=True, kw_only=True)
class Rig:
    """A capture unit on fakes, and the fakes a test drives and reads."""

    unit: CaptureUnit
    keys: PushedKeys
    indicator: RecordingIndicator
    delivered: list
    audio: FakeAudio

    def run(self, frames: int) -> None:
        run(self.unit, frames)

    def texts(self) -> list:
        return [(u.trigger, u.text) for u in self.delivered]


def run(unit: CaptureUnit, frames: int) -> None:
    for _ in range(frames):
        unit.tick()
