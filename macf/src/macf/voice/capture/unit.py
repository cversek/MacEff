"""The capture unit's logic: from microphone frames and key presses to utterances (MIS-0008 6.3 to 6.5).

Platform-free. It reaches the world only through the backends it is given (R14), so the same code
runs on Linux, on macOS, and in tests on recorded audio.

States:
  off        listening is off and nothing is recording: the microphone is closed and no audio is
             read (R15).
  listening  reading audio only to detect a wake; nothing is kept past the short window the wake
             check needs, and no indicator shows.
  recording  capturing an utterance, from a wake or a key press until it ends, with the
             indicator showing the agent and the mode (R21, R22).

How each recording ends:
  wake phrase      a pause of ``end_silence_s`` after speech.
  hold key         the key's release.
  continual voice  each pause of ``end_silence_s`` ends one utterance and the microphone stays
                   open; the toggle key, or ``continual_close_s`` without speech, closes it.
Any recording ends at ``max_utterance_s``, and one that heard no speech at all sends nothing.

The audio of a recording lives in this process's memory and is dropped once transcribed; it is
never written anywhere (R13). Only the text, with closed metadata, leaves, through ``deliver``.
"""
from __future__ import annotations

import collections
import re
import time
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Deque, List, Optional

import numpy as np

from macf.voice.capture.backends import (FRAME, RATE, AudioIn, Indicator, LockState, Mode, SpeechGate,
                                         TriggerSource, WakeDetector)

#: The wake check's window: long enough to hold the phrase whole.
WAKE_WINDOW_S = 2.4
#: How long a fire waits for the phrase to finish before it is judged: the low bar fires as the
#: phrase begins, and a transcription of half of it fails.
SETTLE_AFTER_FIRE_S = 0.8
#: After a rejected fire: short, or a real call that follows a false fire is lost.
REJECT_COOLDOWN_S = 0.75
#: After a recording, before another wake may open one.
COOLDOWN_S = 3.0
#: Audio kept from just before a key press, so the first word isn't clipped.
KEY_PREROLL_S = 0.3
#: A recording that has heard no speech this long is cancelled, and sends nothing.
NO_SPEECH_CANCEL_S = 4.5


@dataclass
class CaptureConfig:
    """What the voice section declares, as the capture logic uses it."""

    agent: str
    wake_phrase: Optional[str] = None
    hold_key: Optional[str] = None
    toggle_key: Optional[str] = None
    detector_bar: float = 0.85
    end_silence_s: float = 1.2
    continual_close_s: float = 30.0
    max_utterance_s: float = 120.0
    #: The voice lock's lockout (MIS-0008 R39, R40), and whether it also covers key recordings
    #: (open question Q02: by default it covers the wake phrase only).
    lockout_attempts: int = 3
    lockout_window_s: float = 600.0
    lockout_s: float = 600.0
    lock_keys: bool = False


@dataclass
class Utterance:
    """One utterance, ready for the daemon: the words and the closed metadata."""

    trigger: Mode
    spoken_at: float
    screen: str
    text: str
    voice_lock: str = "not_declared"


@dataclass
class _Recording:
    mode: Mode
    started: float
    spoken_at: float
    frames: List[np.ndarray] = field(default_factory=list)
    heard_speech: bool = False
    last_speech: float = 0.0
    utterance_started: float = 0.0     # continual voice: when the current utterance began
    voice_lock: str = "not_declared"     # "matched" once the voice lock passed it


def _phrase_pattern(phrase: str) -> re.Pattern:
    words = [re.escape(w) for w in re.findall(r"[\w']+", phrase.lower())]
    return re.compile(r"\b" + r"\W+".join(words) + r"\b", re.I)


class InlineExecutor(Executor):
    """Run a job at once: for tests, so a transcription finishes before ``tick`` returns."""

    def submit(self, fn, *args, **kwargs):
        from concurrent.futures import Future
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as e:  # noqa: BLE001 - carried to the future, as a real executor does
            future.set_exception(e)
        return future


class CaptureUnit:
    """One capture unit for one agent. Call ``tick`` in a loop; it returns after one frame, or at
    once while the microphone is closed."""

    def __init__(self, config: CaptureConfig, *, audio: AudioIn, lock: LockState, indicator: Indicator,
                 triggers: TriggerSource, gate: SpeechGate, transcribe: Callable[[np.ndarray, Optional[str]], str],
                 deliver: Callable[[Utterance], object], detector: Optional[WakeDetector] = None,
                 listening_on: Callable[[], bool] = lambda: True, speaking: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time,
                 executor: Optional[Executor] = None, log: Callable[[str], None] = lambda s: None,
                 speaker: Optional[Callable[[np.ndarray], bool]] = None,
                 on_voice_event: Callable[[str, dict], None] = lambda kind, data: None,
                 guard_lowered: Callable[[], bool] = lambda: False):
        self.config = config
        self.audio, self.lock, self.indicator, self.triggers = audio, lock, indicator, triggers
        self.gate, self.detector, self._transcribe, self._deliver = gate, detector, transcribe, deliver
        self._listening_on, self._speaking = listening_on, speaking
        self.clock, self.wall, self.log = clock, wall, log
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice-transcribe")
        self._phrase = _phrase_pattern(config.wake_phrase) if config.wake_phrase else None
        self.ring: Deque[np.ndarray] = collections.deque(maxlen=int(WAKE_WINDOW_S * RATE / FRAME))
        self.recording: Optional[_Recording] = None
        self._pending_since: Optional[float] = None
        self._quiet_until = 0.0
        #: When listening and the current recording began, for the status entries (R16).
        self.listening_since: Optional[float] = None
        self.recording_since: Optional[float] = None
        self.frames_read = 0
        #: The voice lock (R34): True when the audio's speaker matches the enrolled voice. None: no lock.
        self._speaker = speaker
        self._on_voice_event = on_voice_event
        #: Whether the operator lowered the agent's raised guard, which ends the lockout early (R44).
        self._guard_lowered = guard_lowered
        self._failures: List[float] = []
        self.locked_out_until: Optional[float] = None
        self.locked_out_attempts = 0

    # ------------------------------------------------------------------ the loop

    @property
    def state(self) -> str:
        if self.recording is not None:
            return "recording"
        return "listening" if self.audio.is_open else "off"

    def tick(self) -> None:
        for event in self.triggers.poll():
            self._key(event.key, event.down)
        if self.recording is None:
            on = self._listening_on() and self._phrase is not None and self.detector is not None
            if on and not self.audio.is_open:
                self._open("listening")
            elif not on and self.audio.is_open:
                self._close()
            if not self.audio.is_open:
                return                       # R15: listening off reads nothing
        frame = self.audio.read()
        self.frames_read += 1
        now = self.clock()
        self.ring.append(frame)
        if self.recording is not None:
            self._record(frame, now)
        else:
            self._listen(frame, now)

    def _open(self, why: str) -> None:
        self.audio.open()
        self.ring.clear()
        if self.detector is not None:
            self.detector.reset()
        self.gate.reset()
        self._pending_since = None
        if why == "listening":
            self.listening_since = self.wall()
        self.log(f"microphone open ({why})")

    def _close(self) -> None:
        self.audio.close()
        self.listening_since = None
        self.log("microphone closed")

    # ------------------------------------------------------------------ keys

    def _key(self, key: str, down: bool) -> None:
        cfg = self.config
        if key == cfg.hold_key:
            if down and self.recording is None:
                self._start("hold_key")
            elif not down and self.recording is not None and self.recording.mode == "hold_key":
                self._finish(self.clock())
        elif key == cfg.toggle_key and down:
            if self.recording is not None and self.recording.mode == "continual_voice":
                self._finish(self.clock(), closing=True)
            elif self.recording is None:
                self._start("continual_voice")

    # ------------------------------------------------------------------ listening

    def _listen(self, frame: np.ndarray, now: float) -> None:
        if self.detector is None or self._phrase is None:
            return
        if self._speaking():                 # R27: never wake on the agent's own voice
            self._pending_since = None
            self.detector.reset()
            return
        score = self.detector.score(frame)
        if now < self._quiet_until:
            return
        if self._pending_since is None:
            if score >= self.config.detector_bar:
                self._pending_since = now
            return
        if now - self._pending_since < SETTLE_AFTER_FIRE_S:
            return
        self._pending_since = None
        window = np.concatenate(self.ring)
        if not self._window_has_speech(window):
            self.log("wake fired with no speech in the window: rejected")
            self._quiet_until = now + REJECT_COOLDOWN_S
            return
        if not self._voice_lock_passes(window, now):
            self._quiet_until = now + REJECT_COOLDOWN_S
            return
        heard = self._transcribe(window, self.config.wake_phrase)
        found = self._phrase.search(heard or "")
        if not found:
            self.log("wake fired but the phrase wasn't heard: rejected")
            self._quiet_until = now + REJECT_COOLDOWN_S
            return
        self.log("wake")
        self._start("wake_phrase", preroll=list(self.ring))
        if self._speaker is not None:
            self.recording.voice_lock = "matched"
        if heard[found.end():].strip(" ,.!?;:-"):
            # Words run on in the same breath as the phrase are already in the window: the
            # recording has heard speech, so its pause ends it rather than a no-speech cancel.
            self.recording.heard_speech = True

    def _window_has_speech(self, window: np.ndarray) -> bool:
        self.gate.reset()
        found = any(self.gate.is_speech(window[i:i + FRAME]) for i in range(0, window.size - FRAME + 1, FRAME))
        self.gate.reset()
        return found

    # ------------------------------------------------------------------ recording

    def _start(self, mode: Mode, preroll: Optional[List[np.ndarray]] = None) -> None:
        if not self.audio.is_open:
            self._open(mode)
        now = self.clock()
        if preroll is None:
            keep = int(KEY_PREROLL_S * RATE / FRAME)
            preroll = list(self.ring)[-keep:] if keep else []
        self.recording = _Recording(mode=mode, started=now, spoken_at=self.wall(), frames=list(preroll),
                                    last_speech=now, utterance_started=now)
        self.recording_since = self.wall()
        self.gate.reset()
        self.indicator.show(self.config.agent, mode)

    def _record(self, frame: np.ndarray, now: float) -> None:
        rec = self.recording
        rec.frames.append(frame)
        self.indicator.feed(frame)
        if self.gate.is_speech(frame):
            rec.heard_speech, rec.last_speech = True, now
        if now - rec.started >= self.config.max_utterance_s:
            self._finish(now, closing=True)
            return
        if rec.mode == "hold_key":
            return                           # the release ends it
        silent_for = now - rec.last_speech
        if not rec.heard_speech:
            limit = self.config.continual_close_s if rec.mode == "continual_voice" else NO_SPEECH_CANCEL_S
            if now - rec.utterance_started >= limit:
                self._finish(now, closing=True)
            return
        if silent_for >= self.config.end_silence_s:
            self._finish(now, closing=rec.mode != "continual_voice")

    def _finish(self, now: float, closing: bool = True) -> None:
        """End the current utterance: transcribe it on the worker and deliver it. In continual voice
        a pause ends the utterance and keeps the microphone open, unless ``closing``."""
        rec = self.recording
        if rec.heard_speech:
            audio = np.concatenate(rec.frames)
            if rec.mode != "wake_phrase" and self.config.lock_keys and self._speaker is not None:
                if self._voice_lock_passes(audio, now):
                    rec.voice_lock = "matched"
                else:
                    audio = None             # discarded untranscribed (R37)
            if audio is not None:
                self.executor.submit(self._transcribe_and_deliver, audio, rec.mode, rec.spoken_at, rec.voice_lock)
        else:
            self.log(f"{rec.mode} recording heard no speech: nothing sent")
        rec.frames = []                      # the audio is now the worker's alone, and is dropped after
        if rec.mode == "continual_voice" and not closing:
            rec.heard_speech, rec.utterance_started, rec.spoken_at = False, now, self.wall()
            return
        self.recording = None
        self.recording_since = None
        self.indicator.hide()
        self._quiet_until = now + COOLDOWN_S
        if not (self._listening_on() and self._phrase is not None and self.detector is not None):
            self._close()
        else:
            self.ring.clear()
            self.detector.reset()

    def _voice_lock_passes(self, audio: np.ndarray, now: float) -> bool:
        """The voice lock's verdict on ``audio``, before any transcription (R23, R37). A failure
        discards the audio and tells the agent without content; enough failures in the window lock
        voice contact out, and during a lockout every attempt is counted and none delivered (R39, R41)."""
        if self._speaker is None:
            return True
        if self.locked_out_until is not None:
            if now < self.locked_out_until and self._guard_lowered():
                self.log("the operator lowered the guard: the lockout ends early")
                self.locked_out_until, self.locked_out_attempts = None, 0
            elif now < self.locked_out_until:
                self.locked_out_attempts += 1
                self.log(f"voice locked out: attempt {self.locked_out_attempts} ignored")
                return False
            self.locked_out_until, self.locked_out_attempts = None, 0
        if self._speaker(audio):
            return True
        cfg = self.config
        self._failures = [t for t in self._failures if now - t < cfg.lockout_window_s] + [now]
        self.log(f"voice not matched ({len(self._failures)} of {cfg.lockout_attempts}): discarded untranscribed")
        self._on_voice_event("unmatched", {"attempts": len(self._failures), "of": cfg.lockout_attempts})
        if len(self._failures) >= cfg.lockout_attempts:
            self.locked_out_until = now + cfg.lockout_s
            self._failures = []
            self._on_voice_event("lockout", {"until": self.wall() + cfg.lockout_s})
        return False

    def _transcribe_and_deliver(self, audio: np.ndarray, mode: Mode, spoken_at: float,
                                voice_lock: str = "not_declared") -> None:
        text = (self._transcribe(audio, self.config.wake_phrase if mode == "wake_phrase" else None) or "").strip()
        if mode == "wake_phrase" and self._phrase is not None:
            found = self._phrase.search(text)
            if found:
                text = text[found.end():]
        text = text.strip(" ,.!?;:-")
        if not text:
            self.log(f"{mode} utterance transcribed to nothing: nothing sent")
            return
        self._deliver(Utterance(trigger=mode, spoken_at=spoken_at, screen=self.lock.state(), text=text,
                                voice_lock=voice_lock))

    # ------------------------------------------------------------------ status

    def status(self) -> dict:
        """What the capture unit's beat reports (R16): listening and recording, each with when it
        began, and the agent and mode of a recording."""
        rec = self.recording
        return {"listening_since": self.listening_since if rec is None else None,
                "recording_since": self.recording_since,
                "recording_for": self.config.agent if rec is not None else None,
                "mode": rec.mode if rec is not None else None}

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True)
        self.indicator.hide()
        self.audio.close()
        self.triggers.close()
