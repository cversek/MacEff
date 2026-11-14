"""``macf_tools voice capture trial``: the capture unit on the real microphone, printing each utterance
on this terminal and delivering nothing. It's for trying a wake model with the operator before it's
trusted: say the phrase, see whether it woke, how close a miss came, and why each utterance ended.

While the trial runs, this agent's own listening is switched off, so its capture unit doesn't take the
same words, and the switch is put back however the trial ends. The words heard are printed here and
nowhere else; nothing is written to disk (MIS-0008 R13).
"""
from __future__ import annotations

import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from macf.voice import state
from macf.voice.capture.backends import WakeDetector

#: A phrase model's score above this, then back below it, is a near-fire worth printing.
NEAR = 0.3


class PeakReporting(WakeDetector):
    """Any wake detector, printing each near-fire: when its score climbs past ``NEAR`` and falls back,
    the peak and the bar, so a live miss shows whether the model came close."""

    def __init__(self, inner: WakeDetector, label: str, bar: float, say: Callable[[str], None]):
        self.inner, self.label, self.bar, self.say = inner, label, bar, say
        self.threshold = bar
        self.peak = 0.0

    def score(self, frame: np.ndarray) -> float:
        s = self.inner.score(frame)
        if s >= NEAR:
            self.peak = max(self.peak, s)
        elif self.peak:
            self._report()
        return s

    def reset(self) -> None:
        if self.peak:
            self._report()
        self.inner.reset()

    def _report(self) -> None:
        mark = "fired" if self.peak >= self.bar else "under the bar"
        self.say(f"{self.label} peaked {self.peak:.3f} (bar {self.bar:.2f}): {mark}")
        self.peak = 0.0


@dataclass
class Tally:
    wakes: int = 0
    utterances: int = 0


@dataclass(frozen=True, kw_only=True)
class Trial:
    """What ``build`` makes: the unit, what it has taken so far, and a line naming what it listens for."""

    unit: object
    tally: Tally
    listening: str


def printer(tally: Tally, out=print) -> Callable:
    """The trial's ``deliver``: the utterance on this terminal, with why it ended, and nowhere else."""
    def deliver(u) -> None:
        tally.utterances += 1
        when = time.strftime("%H:%M:%S", time.localtime(u.spoken_at))
        out(f"\n✅ utterance {tally.utterances} → {u.agent} [{u.trigger}, spoken {when}, "
            f"ended: {u.ended or 'unknown'}, screen {u.screen}]: {u.text}\n")
    return deliver


def logger(tally: Tally, out=print) -> Callable[[str], None]:
    def log(line: str) -> None:
        if line.startswith("wake for"):
            tally.wakes += 1
        out(f"   {time.strftime('%H:%M:%S')} {line}")
    return log


def run(unit, home: Path, out=print, stopping: Optional[List] = None) -> None:
    """Tick ``unit`` until Ctrl-C (or ``stopping`` fills), with this agent's listening off throughout and
    restored after, as it was."""
    was_on = state.listening_on(home)
    state.set_listening(home, False)
    if was_on:
        out("(this agent's listening is off for the trial, and comes back on when it ends)")
    stopping = [] if stopping is None else stopping
    previous = signal.signal(signal.SIGINT, lambda *_: stopping.append(True))
    try:
        while not stopping:
            unit.tick()
    finally:
        signal.signal(signal.SIGINT, previous)
        unit.shutdown()
        state.set_listening(home, was_on)


def build(home: Path, phrases: List[str], models: List[str], vocabulary: Optional[str], out=print):
    """The trial's capture unit, its tally, and a line naming what it listens for: each ``--phrase`` with its ``--model``, or the voice section's own
    when none is given. Wake phrase only; keys need a granted trigger device and aren't tried here."""
    from macf.pd.core import load_declaration
    from macf.pd.interface import agent_card
    from macf.voice.capture.models import SileroGate, TrainedWakeDetector
    from macf.voice.capture.unit import AgentBinding, CaptureConfig, CaptureUnit
    from macf.voice.capture.__main__ import NoKeys, whisper_prompt
    from macf.voice.transcribe import transcribe_array
    card = agent_card(home)
    voice = None
    try:
        voice = load_declaration(home, card).voice
    except Exception as e:  # noqa: BLE001 - the trial runs without a declaration when phrase and model are given; say why it wasn't read
        out(f"(the declaration wasn't read: {e})")
    if not phrases and voice is not None and voice.wake_phrase and voice.wake_model:
        phrases, models = [voice.wake_phrase], [voice.wake_model]
    if not phrases:
        raise ValueError("no wake phrase to try: give --phrase and --model, or declare them in the voice section")
    if len(phrases) != len(models):
        raise ValueError("give one --model for each --phrase, in the same order")
    if vocabulary is None and voice is not None:
        vocabulary = voice.transcription_prompt
    if not sys.platform.startswith("linux"):
        raise RuntimeError("this platform has no capture backends yet; docs/VOICE_PORTING.md says what to write (MIS-0008 R14)")
    from macf.voice.capture.linux import LinuxLockState, OverlayIndicator, PipeWireAudio
    tally = Tally()
    log = logger(tally, out)
    members = []
    for i, (phrase, model) in enumerate(zip(phrases, models)):
        path = Path(model).expanduser()
        detector = TrainedWakeDetector(path if path.is_absolute() else home / path)
        agent = card if i == 0 else f"{card} (as {phrase!r})"
        members.append(AgentBinding(agent=agent, wake_phrase=phrase, detector_bar=detector.threshold,
                                    detector=PeakReporting(detector, phrase, detector.threshold, log)))

    def transcribe(audio, phrase):
        return transcribe_array(audio, initial_prompt=whisper_prompt(phrase, vocabulary)).text
    unit = CaptureUnit(CaptureConfig(agent=card), members=members, audio=PipeWireAudio(), lock=LinuxLockState(),
                       indicator=OverlayIndicator(), triggers=NoKeys(), gate=SileroGate(), transcribe=transcribe,
                       deliver=printer(tally, out), log=log)
    listening = ", ".join(f'"{m.wake_phrase}" (bar {m.detector_bar:.2f})' for m in members)
    return Trial(unit=unit, tally=tally, listening=listening)
