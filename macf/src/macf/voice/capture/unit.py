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
#: R56's stop words: said as the last word, ``send`` ends the utterance and sends it without the word;
#: ``abort`` ends it and sends nothing.
SEND_WORD, ABORT_WORD = "send", "abort"
#: What recognition actually writes for a stop word, each counted as that word. "sand" is how Whisper heard
#: the operator's "send" in the second live trial (2026-11-13); add one only from a real mishearing.
STOP_WORD_HEARD_AS = {"send": SEND_WORD, "sand": SEND_WORD, "abort": ABORT_WORD}
#: The pause after speech at which the last words are checked for a stop word, and how much is checked.
STOP_PAUSE_S = 0.6
STOP_TAIL_S = 2.5


def last_stop_word(text: str) -> Optional[str]:
    """``send`` or ``abort`` when the text's last word is one of them, ignoring case and punctuation."""
    words = re.findall(r"[a-z']+", (text or "").lower())
    return STOP_WORD_HEARD_AS.get(words[-1]) if words else None


def strip_stop_word(text: str) -> tuple:
    """(text without a trailing stop word, the word or None)."""
    word = last_stop_word(text)
    if word is None:
        return text, None
    cut = re.search(r"\b[\w']+\W*$", text)        # the last word as heard, whichever spelling matched
    return (text[:cut.start()] if cut else text).rstrip(" ,.!?;:-"), word


@dataclass
class CaptureConfig:
    """What the voice section declares, as the capture logic uses it."""

    agent: str
    wake_phrase: Optional[str] = None
    hold_key: Optional[str] = None
    toggle_key: Optional[str] = None
    detector_bar: float = 0.85
    #: R56's end window: full for ``end_hold_s`` of quiet, empty at ``end_silence_s``, when the utterance ends.
    end_hold_s: float = 2.0
    end_silence_s: float = 5.0
    #: R56: listen for the stop words at each short pause. Off only where transcription is scripted.
    stop_words: bool = True
    continual_close_s: float = 30.0
    max_utterance_s: float = 120.0
    #: The voice lock's lockout (MIS-0008 R39, R40), and whether it also covers key recordings
    #: (open question Q02: by default it covers the wake phrase only).
    lockout_attempts: int = 3
    lockout_window_s: float = 600.0
    lockout_s: float = 600.0
    lock_keys: bool = False


@dataclass
class AgentBinding:
    """One agent a capture unit listens for: its card, the phrase and keys that open the microphone
    for it, its wake model, and its voice lock with the lockout counted for it alone (MIS-0008 R46,
    R47). A unit for one agent builds its single binding from its ``CaptureConfig``; a system's
    unit is given one per member, from the system declaration."""

    agent: str
    wake_phrase: Optional[str] = None
    hold_key: Optional[str] = None
    toggle_key: Optional[str] = None
    detector: Optional[WakeDetector] = None
    detector_bar: float = 0.85
    #: True when the audio's speaker matches this agent's enrolled voice. None: no voice lock.
    speaker: Optional[Callable[[np.ndarray], bool]] = None
    on_voice_event: Callable[[str, dict], None] = lambda kind, data: None
    guard_lowered: Callable[[], bool] = lambda: False
    lockout_attempts: int = 3
    lockout_window_s: float = 600.0
    lockout_s: float = 600.0
    lock_keys: bool = False


class _Agent:
    """A binding with its running state: the phrase as a pattern, and the voice lock's count."""

    def __init__(self, binding: AgentBinding):
        self.b = binding
        self.phrase = _phrase_pattern(binding.wake_phrase) if binding.wake_phrase else None
        self.failures: List[float] = []
        self.locked_out_until: Optional[float] = None
        self.locked_out_attempts = 0

    @property
    def wakeable(self) -> bool:
        return self.phrase is not None and self.b.detector is not None


@dataclass
class Utterance:
    """One utterance, ready for the daemon: the words and the closed metadata, and the agent it is
    for, which only the binding that fired decides (R47)."""

    trigger: Mode
    spoken_at: float
    screen: str
    text: str
    voice_lock: str = "not_declared"
    agent: str = ""
    #: Why the recording ended (idea 602): "end window", "send", "key released", "toggle key",
    #: "longest length". Metadata for the unit's own log; never sent to the daemon.
    ended: str = ""


@dataclass
class _Recording:
    mode: Mode
    started: float
    spoken_at: float
    agent: "_Agent"
    frames: List[np.ndarray] = field(default_factory=list)
    heard_speech: bool = False
    last_speech: float = 0.0
    utterance_started: float = 0.0     # continual voice: when the current utterance began
    window_shown: float = 1.0          # the end window's fill last sent to the indicator (R56)
    stop_check: object = None          # a stop-word check in flight (R56)
    stop_checked_at: Optional[float] = None   # the last speech the check covered, so each pause is checked once
    aborted: bool = False              # ended by "abort" (R57): nothing is sent, and that was already said
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
    """One capture unit: for one agent, or on a system daemon for each member agent (R46). Call
    ``tick`` in a loop; it returns after one frame, or at once while the microphone is closed.

    For one agent, the phrase and keys come from ``config`` and the wake model and voice lock from
    the keyword arguments. For several, ``members`` gives one binding each, and ``config`` supplies
    only what every recording shares: its pauses and its longest length."""

    def __init__(self, config: CaptureConfig, *, audio: AudioIn, lock: LockState, indicator: Indicator,
                 triggers: TriggerSource, gate: SpeechGate, transcribe: Callable[[np.ndarray, Optional[str]], str],
                 deliver: Callable[[Utterance], object], detector: Optional[WakeDetector] = None,
                 listening_on: Callable[[], bool] = lambda: True, speaking: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time,
                 executor: Optional[Executor] = None, log: Callable[[str], None] = lambda s: None,
                 speaker: Optional[Callable[[np.ndarray], bool]] = None,
                 on_voice_event: Callable[[str, dict], None] = lambda kind, data: None,
                 guard_lowered: Callable[[], bool] = lambda: False,
                 members: Optional[List[AgentBinding]] = None):
        self.config = config
        self.audio, self.lock, self.indicator, self.triggers = audio, lock, indicator, triggers
        self.gate, self._transcribe, self._deliver = gate, transcribe, deliver
        self._listening_on, self._speaking = listening_on, speaking
        self.clock, self.wall, self.log = clock, wall, log
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice-transcribe")
        if members is None:
            members = [AgentBinding(agent=config.agent, wake_phrase=config.wake_phrase, hold_key=config.hold_key,
                                    toggle_key=config.toggle_key, detector=detector,
                                    detector_bar=config.detector_bar, speaker=speaker,
                                    on_voice_event=on_voice_event, guard_lowered=guard_lowered,
                                    lockout_attempts=config.lockout_attempts,
                                    lockout_window_s=config.lockout_window_s, lockout_s=config.lockout_s,
                                    lock_keys=config.lock_keys)]
        if not members:
            raise ValueError("a capture unit listens for at least one agent")
        self.agents: List[_Agent] = [_Agent(m) for m in members]
        self.ring: Deque[np.ndarray] = collections.deque(maxlen=int(WAKE_WINDOW_S * RATE / FRAME))
        self.recording: Optional[_Recording] = None
        #: The agent whose wake model fired, and when, while the phrase settles.
        self._pending: Optional[tuple] = None
        self._quiet_until = 0.0
        #: When listening and the current recording began, for the status entries (R16).
        self.listening_since: Optional[float] = None
        self.recording_since: Optional[float] = None
        self.frames_read = 0

    # A unit for one agent reads its lockout as its own.
    @property
    def locked_out_until(self) -> Optional[float]:
        return self.agents[0].locked_out_until

    @property
    def locked_out_attempts(self) -> int:
        return self.agents[0].locked_out_attempts

    # ------------------------------------------------------------------ the loop

    @property
    def state(self) -> str:
        if self.recording is not None:
            return "recording"
        return "listening" if self.audio.is_open else "off"

    def _wakeable(self) -> bool:
        return any(a.wakeable for a in self.agents)

    def tick(self) -> None:
        for event in self.triggers.poll():
            self._key(event.key, event.down)
        if self.recording is None:
            on = self._listening_on() and self._wakeable()
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
        self._reset_detectors()
        self.gate.reset()
        self._pending = None
        if why == "listening":
            self.listening_since = self.wall()
        self.log(f"microphone open ({why})")

    def _close(self) -> None:
        self.audio.close()
        self.listening_since = None
        self.log("microphone closed")

    # ------------------------------------------------------------------ keys

    def _key(self, key: str, down: bool) -> None:
        """A key opens or closes a recording for the agent whose key it is, and only that agent
        (R47). A key nobody declared does nothing; while one agent's recording runs, another
        agent's key waits its turn rather than cutting it off."""
        rec = self.recording
        for agent in self.agents:
            if key == agent.b.hold_key:
                if down and rec is None:
                    self._start("hold_key", agent)
                elif not down and rec is not None and rec.mode == "hold_key" and rec.agent is agent:
                    self._finish(self.clock(), ended="key released")
                return
            if key == agent.b.toggle_key and down:
                if rec is not None and rec.mode == "continual_voice" and rec.agent is agent:
                    self._finish(self.clock(), closing=True, ended="toggle key")
                elif rec is None:
                    self._start("continual_voice", agent)
                return

    # ------------------------------------------------------------------ listening

    def _reset_detectors(self) -> None:
        for agent in self.agents:
            if agent.b.detector is not None:
                agent.b.detector.reset()

    def _listen(self, frame: np.ndarray, now: float) -> None:
        if not self._wakeable():
            return
        if self._speaking():                 # R27: never wake on an agent's own voice
            self._pending = None
            self._reset_detectors()
            return
        # Every wake model hears every frame, so each keeps its own state; the first to fire
        # decides whose phrase is checked (R47).
        fired = None
        for agent in self.agents:
            if agent.wakeable:
                score = agent.b.detector.score(frame)
                if fired is None and score >= agent.b.detector_bar:
                    fired = agent
        if now < self._quiet_until:
            return
        if self._pending is None:
            if fired is not None:
                self._pending = (fired, now)
            return
        agent, since = self._pending
        if now - since < SETTLE_AFTER_FIRE_S:
            return
        self._pending = None
        window = np.concatenate(self.ring)
        if not self._window_has_speech(window):
            self.log("wake fired with no speech in the window: rejected")
            self._quiet_until = now + REJECT_COOLDOWN_S
            return
        if not self._voice_lock_passes(agent, window, now):
            self._quiet_until = now + REJECT_COOLDOWN_S
            return
        heard = self._transcribe(window, agent.b.wake_phrase)
        found = agent.phrase.search(heard or "")
        if not found:
            self.log("wake fired but the phrase wasn't heard: rejected")
            self._quiet_until = now + REJECT_COOLDOWN_S
            return
        self.log(f"wake for {agent.b.agent}")
        self._start("wake_phrase", agent, preroll=list(self.ring))
        if agent.b.speaker is not None:
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

    def _start(self, mode: Mode, agent: _Agent, preroll: Optional[List[np.ndarray]] = None) -> None:
        if not self.audio.is_open:
            self._open(mode)
        now = self.clock()
        if preroll is None:
            keep = int(KEY_PREROLL_S * RATE / FRAME)
            preroll = list(self.ring)[-keep:] if keep else []
        self.recording = _Recording(mode=mode, started=now, spoken_at=self.wall(), agent=agent,
                                    frames=list(preroll), last_speech=now, utterance_started=now)
        self.recording_since = self.wall()
        self.gate.reset()
        self.indicator.show(agent.b.agent, mode)     # R21: which agent the microphone is open for

    def _record(self, frame: np.ndarray, now: float) -> None:
        rec = self.recording
        rec.frames.append(frame)
        self.indicator.feed(frame)
        if self.gate.is_speech(frame):
            rec.heard_speech, rec.last_speech = True, now
        if now - rec.started >= self.config.max_utterance_s:
            self._finish(now, closing=True, ended="longest length")
            return
        if rec.mode == "hold_key":
            return                           # the release ends it
        silent_for = now - rec.last_speech
        if not rec.heard_speech:
            limit = self.config.continual_close_s if rec.mode == "continual_voice" else NO_SPEECH_CANCEL_S
            if now - rec.utterance_started >= limit:
                self._finish(now, closing=True, ended="no speech")
            return
        self._show_window(rec, silent_for)
        said = self._stop_word_heard(rec, silent_for)
        if said == ABORT_WORD:
            self.log(f"\"{ABORT_WORD}\": the utterance is discarded, nothing sent")
            rec.frames, rec.heard_speech, rec.aborted = [], False, True
            self._finish(now, closing=rec.mode != "continual_voice", ended="abort")
            return
        if said == SEND_WORD or silent_for >= self.config.end_silence_s:
            self._finish(now, closing=rec.mode != "continual_voice",
                         ended="send" if said == SEND_WORD else "end window")

    def _show_window(self, rec: "_Recording", silent_for: float) -> None:
        """R56: how much of the end window is left, for the indicator. Full until ``end_hold_s`` of quiet,
        then draining to empty at ``end_silence_s``; speech fills it again."""
        hold, close = self.config.end_hold_s, self.config.end_silence_s
        left = 1.0 if silent_for <= hold else max(0.0, 1.0 - (silent_for - hold) / max(close - hold, 1e-6))
        if left != rec.window_shown:
            rec.window_shown = left
            self.indicator.window(left)

    def _stop_word_heard(self, rec: "_Recording", silent_for: float) -> Optional[str]:
        """R56: at a short pause after speech, transcribe the last few seconds once, in the background; a
        stop word said last ends the utterance at once (``send``) or discards it (``abort``). Speech that
        resumes before the answer makes the answer stale, so it is dropped."""
        if not self.config.stop_words or silent_for < STOP_PAUSE_S:
            rec.stop_check, rec.stop_checked_at = None, None
            return None
        if rec.stop_check is None and rec.stop_checked_at != rec.last_speech:
            tail = np.concatenate(rec.frames[-int(STOP_TAIL_S * RATE / FRAME):])
            rec.stop_checked_at = rec.last_speech
            rec.stop_check = self.executor.submit(self._transcribe, tail, None)
        if rec.stop_check is not None and rec.stop_check.done():
            future, rec.stop_check = rec.stop_check, None
            try:
                return last_stop_word(future.result() or "")
            except Exception as e:  # noqa: BLE001 - a failed check only means no early end; the window still ends it
                self.log(f"the stop-word check failed ({e}); the end window ends the utterance")
        return None

    def _finish(self, now: float, closing: bool = True, ended: str = "") -> None:
        """End the current utterance: transcribe it on the worker and deliver it. In continual voice
        a pause ends the utterance and keeps the microphone open, unless ``closing``. ``ended`` says
        why, in the log and on the utterance, so a cut that surprises the speaker can be read (idea 602)."""
        rec = self.recording
        if ended and rec.heard_speech:
            self.log(f"{rec.mode} utterance ended: {ended}")
        if rec.heard_speech:
            audio = np.concatenate(rec.frames)
            if rec.mode != "wake_phrase" and rec.agent.b.lock_keys and rec.agent.b.speaker is not None:
                if self._voice_lock_passes(rec.agent, audio, now):
                    rec.voice_lock = "matched"
                else:
                    audio = None             # discarded untranscribed (R37)
            if audio is not None:
                self.executor.submit(self._transcribe_and_deliver, audio, rec.mode, rec.spoken_at, rec.voice_lock,
                                     rec.agent, ended)
        else:
            if not rec.aborted:                  # an abort already said why nothing was sent
                self.log(f"{rec.mode} recording heard no speech: nothing sent")
        rec.frames = []                      # the audio is now the worker's alone, and is dropped after
        if rec.mode == "continual_voice" and not closing:
            rec.heard_speech, rec.utterance_started, rec.spoken_at = False, now, self.wall()
            rec.aborted = False
            return
        self.recording = None
        self.recording_since = None
        self.indicator.hide()
        self._quiet_until = now + COOLDOWN_S
        if not (self._listening_on() and self._wakeable()):
            self._close()
        else:
            self.ring.clear()
            self._reset_detectors()

    def _voice_lock_passes(self, agent: _Agent, audio: np.ndarray, now: float) -> bool:
        """``agent``'s voice lock on ``audio``, before any transcription (R23, R37). A failure
        discards the audio and tells that agent without content; enough failures in its window lock
        voice contact with it out, and during a lockout every attempt is counted and none delivered
        (R39, R41). Each agent's count is its own, so one agent's lockout never silences another."""
        b = agent.b
        if b.speaker is None:
            return True
        if agent.locked_out_until is not None:
            if now < agent.locked_out_until and b.guard_lowered():
                self.log(f"the operator lowered {b.agent}'s guard: the lockout ends early")
                agent.locked_out_until, agent.locked_out_attempts = None, 0
            elif now < agent.locked_out_until:
                agent.locked_out_attempts += 1
                self.log(f"voice locked out for {b.agent}: attempt {agent.locked_out_attempts} ignored")
                return False
            agent.locked_out_until, agent.locked_out_attempts = None, 0
        if b.speaker(audio):
            return True
        agent.failures = [t for t in agent.failures if now - t < b.lockout_window_s] + [now]
        self.log(f"voice not matched for {b.agent} ({len(agent.failures)} of {b.lockout_attempts}): "
                 f"discarded untranscribed")
        b.on_voice_event("unmatched", {"attempts": len(agent.failures), "of": b.lockout_attempts})
        if len(agent.failures) >= b.lockout_attempts:
            agent.locked_out_until = now + b.lockout_s
            agent.failures = []
            b.on_voice_event("lockout", {"until": self.wall() + b.lockout_s})
        return False

    def _transcribe_and_deliver(self, audio: np.ndarray, mode: Mode, spoken_at: float,
                                voice_lock: str = "not_declared", agent: Optional[_Agent] = None,
                                ended: str = "") -> None:
        agent = agent or self.agents[0]
        text = (self._transcribe(audio, agent.b.wake_phrase if mode == "wake_phrase" else None) or "").strip()
        if mode == "wake_phrase" and agent.phrase is not None:
            found = agent.phrase.search(text)
            if found:
                text = text[found.end():]
        text = text.strip(" ,.!?;:-")
        text, word = strip_stop_word(text)       # R56: whatever ended it, a trailing stop word is obeyed
        if word == ABORT_WORD:
            self.log(f"{mode} utterance ended in \"{ABORT_WORD}\": discarded, nothing sent")
            return
        if not text:
            self.log(f"{mode} utterance transcribed to nothing: nothing sent")
            return
        self._deliver(Utterance(trigger=mode, spoken_at=spoken_at, screen=self.lock.state(), text=text,
                                voice_lock=voice_lock, agent=agent.b.agent, ended=ended))

    # ------------------------------------------------------------------ status

    def status(self) -> dict:
        """What the capture unit's beat reports (R16): listening and recording, each with when it
        began, and the agent and mode of a recording."""
        rec = self.recording
        return {"listening_since": self.listening_since if rec is None else None,
                "recording_since": self.recording_since,
                "recording_for": rec.agent.b.agent if rec is not None else None,
                "mode": rec.mode if rec is not None else None}

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True)
        self.indicator.hide()
        self.audio.close()
        self.triggers.close()
