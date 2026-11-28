"""What the speech worker reaches: a speech engine, and audio out, the fifth platform backend
(MIS-0008 6.6, R14).

The engine turns a sentence into samples; audio out plays them and can be stopped. Both are small
classes, so a new engine or a new platform is a subclass that passes ``check_audio_out``.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class Spoken:
    """One sentence as audio: float32 samples in -1..1, at ``rate`` samples per second, and, from an
    engine that knows them, when each word ends, in seconds from the first sample. Without them, a
    cut sentence's heard words are estimated (``cut.heard_in_sentence``)."""

    samples: np.ndarray
    rate: int
    word_ends: Optional[Tuple[float, ...]] = None

    @property
    def duration_s(self) -> float:
        return len(self.samples) / float(self.rate) if self.rate else 0.0


class SpeechEngine(ABC):
    @abstractmethod
    def say(self, sentence: str, voice: str, speed: float, lang: str) -> Spoken:
        """The sentence spoken in ``voice`` (a name, or a blend such as ``a:0.6,b:0.4``)."""

    @abstractmethod
    def voices(self) -> List[str]:
        """The voice names this engine has."""


class AudioOut(ABC):
    @abstractmethod
    def play(self, spoken: Spoken) -> None:
        """Play it, returning when it has finished or was stopped."""

    @abstractmethod
    def stop(self) -> None:
        """Stop what is playing now, from any thread. Safe when nothing plays."""


def soften(samples: np.ndarray, rate: int) -> np.ndarray:
    """Lead-in silence and short fades, so a sentence never starts or stops with a click."""
    out = np.array(samples, dtype=np.float32)
    fade = min(int(rate * 0.012), out.size // 2)
    if fade:
        out[:fade] *= np.linspace(0, 1, fade)
        out[-fade:] *= np.linspace(1, 0, fade)
    return np.r_[np.zeros(int(rate * 0.12), np.float32), out, np.zeros(int(rate * 0.05), np.float32)]


class KokoroEngine(SpeechEngine):
    """Kokoro, run locally: nothing spoken leaves the machine. Its model and voices files are the
    operator's to install; a missing one is named."""

    def __init__(self, model: Path, voices: Path):
        for path in (model, voices):
            if not Path(path).exists():
                raise RuntimeError(f"the Kokoro file {path} is not there; install the model and voices files")
        try:
            from kokoro_onnx import Kokoro
        except ImportError as e:
            raise RuntimeError("the Kokoro engine needs kokoro-onnx, which macf's voice extra installs") from e
        self._kokoro = Kokoro(str(model), str(voices))

    def _style(self, voice: str):
        if "," not in voice and ":" not in voice:
            return voice
        style, total = None, 0.0
        for part in voice.split(","):
            name, weight = (part.split(":", 1) + ["1"])[:2]
            w = float(weight or 1)
            v = self._kokoro.get_voice_style(name.strip()) * w
            style, total = (v if style is None else style + v), total + w
        return style / total

    def say(self, sentence, voice, speed, lang) -> Spoken:
        samples, rate = self._kokoro.create(sentence, voice=self._style(voice), speed=speed, lang=lang)
        return Spoken(soften(samples, rate), int(rate))

    def voices(self) -> List[str]:
        return list(self._kokoro.get_voices())


class PipeWireOut(AudioOut):
    """Playback through ``pw-cat``, fed raw float samples on its stdin: no file is written."""

    def __init__(self, command: Sequence[str] = ("pw-cat", "--playback", "--raw", "--format", "f32",
                                                 "--channels", "1")):
        self.command = list(command)
        self._proc = None
        self._lock = threading.Lock()

    def play(self, spoken: Spoken) -> None:
        if shutil.which(self.command[0]) is None:
            raise RuntimeError(f"{self.command[0]} is not on PATH, so speech can't be played")
        with self._lock:
            self._proc = subprocess.Popen(self.command + ["--rate", str(spoken.rate), "-"], stdin=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL)
        proc = self._proc
        try:
            proc.stdin.write(np.asarray(spoken.samples, dtype=np.float32).tobytes())
            proc.stdin.close()
        except BrokenPipeError:
            print("⚠️ MACF: voice: playback ended before the sentence did (stopped?)", file=sys.stderr)
        proc.wait()
        with self._lock:
            self._proc = None

    def stop(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                self._proc.terminate()


def check_audio_out(make) -> None:
    """The contract a porter's audio out keeps: play returns, stop is safe idle and from another thread."""
    out = make()
    out.stop()
    out.play(Spoken(np.zeros(1600, np.float32), 16000))
    stopper = threading.Timer(0.05, out.stop)
    stopper.start()
    out.play(Spoken(np.zeros(16000 * 5, np.float32), 16000))
    stopper.join()
    out.stop()
