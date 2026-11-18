"""Speech playback on macOS (MIS-0008; docs/VOICE_PORTING.md section 6): PortAudio through ``sounddevice``.

Samples go from memory to the default output in short blocks, so ``stop`` takes effect within one
block from any thread (R29: speech stops when a recording opens). No file is written.
"""
from __future__ import annotations

import sys
import threading
from typing import List

import numpy as np

from macf.voice.speech.backends import AudioOut, SpeechEngine, Spoken, soften

#: How often play() checks for the end of the sentence.
BLOCK_S = 0.05
#: The loudest a sample may be: Kokoro reaches full scale, and a clipped peak is heard as a crackle.
PEAK = 0.89


#: Quiet below this is trimmed from a sentence's ends, leaving TRIM_KEEP_S, so sentences follow closely.
TRIM_LEVEL, TRIM_KEEP_S = 0.003, 0.06


def trimmed(x: np.ndarray, rate: int) -> np.ndarray:
    """The sentence without the long silence Kokoro puts at each end."""
    loud = np.flatnonzero(np.abs(x) > TRIM_LEVEL)
    if loud.size == 0:
        return x
    keep = int(rate * TRIM_KEEP_S)
    return x[max(0, loud[0] - keep):loud[-1] + 1 + keep]


def prepared(samples: np.ndarray, rate: int, device_rate: int) -> np.ndarray:
    """The sentence as the device will play it: its silent ends trimmed, scaled under PEAK, and resampled
    to the device's own rate so Core Audio has nothing left to convert."""
    x = trimmed(np.asarray(samples, dtype=np.float64), rate)
    peak = float(np.abs(x).max()) if x.size else 0.0
    if peak > PEAK:
        x = x * (PEAK / peak)
    if device_rate and device_rate != rate:
        from math import gcd

        from scipy.signal import resample_poly
        g = gcd(int(device_rate), int(rate))
        x = resample_poly(x, int(device_rate) // g, int(rate) // g)
    return np.clip(x, -1.0, 1.0).astype(np.float32)


class _Output:
    """The one stream to the default output device, shared by every MacAudioOut in the process and
    closed at exit. A stream owned by an instance was freed with it while Core Audio still called back
    into it, and the process crashed."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pending = np.zeros(0, np.float32)
        self.drained = threading.Event()
        self.stream = None
        self.rate = 0

    def start(self) -> None:
        import atexit

        import sounddevice
        with self.lock:
            if self.stream is not None:
                return
            self.rate = int(sounddevice.query_devices(kind="output")["default_samplerate"])
            self.stream = sounddevice.OutputStream(samplerate=self.rate, channels=1, dtype="float32",
                                                   latency="high", callback=self.pull)
            self.stream.start()
        atexit.register(self.close)

    def pull(self, out, frames, _time, _status) -> None:
        with self.lock:
            chunk, self.pending = self.pending[:frames], self.pending[frames:]
            empty = self.pending.size == 0
        out[:chunk.size, 0] = chunk
        out[chunk.size:, 0] = 0.0
        if empty:
            self.drained.set()

    def close(self) -> None:
        stream, self.stream = self.stream, None
        if stream is not None:
            stream.stop()
            stream.close()


_OUTPUT = _Output()


class MacAudioOut(AudioOut):
    """The default output device; ``play`` blocks until the sentence ends or ``stop`` is called.

    One stream stays open across sentences and Core Audio pulls from it at high latency, so a busy
    Python never lets the buffer run dry (blocking writes of short blocks crackled), and a new sentence
    does not wait for a stream to open (one stream per sentence left a long pause between them). The
    stream plays silence between sentences. ``stop`` empties it at the next callback.
    """

    def play(self, spoken: Spoken) -> None:
        _OUTPUT.start()
        samples = prepared(spoken.samples, spoken.rate, _OUTPUT.rate)
        with _OUTPUT.lock:
            _OUTPUT.drained.clear()
            _OUTPUT.pending = np.concatenate([_OUTPUT.pending, samples])
        while not _OUTPUT.drained.wait(BLOCK_S):
            pass

    def stop(self) -> None:
        with _OUTPUT.lock:
            _OUTPUT.pending = np.zeros(0, np.float32)
        _OUTPUT.drained.set()


#: Kokoro's MLX weights on Hugging Face; fetched once into its cache, then run locally.
MLX_KOKORO = "prince-canuma/Kokoro-82M"
#: The language codes the worker uses, as Kokoro's MLX port names them.
MLX_LANG = {"en-us": "a", "en-gb": "b"}


class MlxKokoroEngine(SpeechEngine):
    """Kokoro on the Mac's GPU through MLX (``mlx-audio``): about 14 times faster than real time on an
    M3 Max, where the ONNX model on the CPU took twice as long as the speech it made and left a long
    pause between sentences. Nothing spoken leaves the machine. A blend of voices is spoken in its
    heaviest voice, said once, since the MLX port takes one voice by name."""

    def __init__(self, model: str = MLX_KOKORO) -> None:
        try:
            from mlx_audio.tts.utils import load_model
        except ImportError as e:
            raise RuntimeError("the MLX Kokoro engine needs mlx-audio and misaki, which macf's voice extra "
                               "installs on Apple Silicon") from e
        self._model = load_model(model)
        self._blend_said = False
        self.say("Ready.", "am_michael", 1.0, "en-us")   # the first call compiles; take that cost at start

    def _voice(self, voice: str) -> str:
        if "," not in voice and ":" not in voice:
            return voice
        parts = [(p.split(":", 1) + ["1"])[:2] for p in voice.split(",")]
        name = max(parts, key=lambda p: float(p[1] or 1))[0].strip()
        if not self._blend_said:
            self._blend_said = True
            print(f"⚠️ MACF: voice: the MLX engine speaks one voice; the blend {voice!r} is spoken as {name!r}",
                  file=sys.stderr)
        return name

    def say(self, sentence, voice, speed, lang) -> Spoken:
        parts = list(self._model.generate(text=sentence, voice=self._voice(voice), speed=speed,
                                          lang_code=MLX_LANG.get(lang, "a")))
        samples = np.concatenate([np.asarray(p.audio, dtype=np.float32) for p in parts]) if parts else np.zeros(0, np.float32)
        rate = int(getattr(self._model, "sample_rate", 24000))
        return Spoken(soften(samples, rate), rate)

    def voices(self) -> List[str]:
        from macf.voice.speech.select import VOICES
        return sorted(VOICES)
