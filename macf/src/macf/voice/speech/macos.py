"""Speech playback on macOS (MIS-0008; docs/VOICE_PORTING.md section 6): PortAudio through ``sounddevice``.

Samples go from memory to the default output in short blocks, so ``stop`` takes effect within one
block from any thread (R29: speech stops when a recording opens). No file is written.
"""
from __future__ import annotations

import threading

import numpy as np

from macf.voice.speech.backends import AudioOut, Spoken

#: How often play() checks for the end of the sentence.
BLOCK_S = 0.05
#: The loudest a sample may be: Kokoro reaches full scale, and a clipped peak is heard as a crackle.
PEAK = 0.89


def prepared(samples: np.ndarray, rate: int, device_rate: int) -> np.ndarray:
    """The sentence as the device will play it: scaled under PEAK, and resampled to the device's own rate
    so Core Audio has nothing left to convert."""
    x = np.asarray(samples, dtype=np.float64)
    peak = float(np.abs(x).max()) if x.size else 0.0
    if peak > PEAK:
        x = x * (PEAK / peak)
    if device_rate and device_rate != rate:
        from math import gcd

        from scipy.signal import resample_poly
        g = gcd(int(device_rate), int(rate))
        x = resample_poly(x, int(device_rate) // g, int(rate) // g)
    return np.clip(x, -1.0, 1.0).astype(np.float32)


class MacAudioOut(AudioOut):
    """The default output device; ``play`` blocks until the sentence ends or ``stop`` is called.

    PortAudio pulls the samples through a callback with Core Audio's high latency, so a busy Python
    never lets the buffer run dry (blocking writes of short blocks did, and the speech crackled).
    ``stop`` ends the stream at the next callback, a few tens of milliseconds.
    """

    def __init__(self) -> None:
        self._stopping = threading.Event()

    def play(self, spoken: Spoken) -> None:
        import sounddevice
        self._stopping.clear()
        device_rate = int(sounddevice.query_devices(kind="output")["default_samplerate"])
        samples = prepared(spoken.samples, spoken.rate, device_rate)
        position = [0]
        done = threading.Event()

        def pull(out, frames, _time, _status):
            start = position[0]
            chunk = samples[start:start + frames]
            out[:len(chunk), 0] = chunk
            out[len(chunk):, 0] = 0.0
            position[0] = start + frames
            if self._stopping.is_set() or position[0] >= len(samples):
                raise sounddevice.CallbackStop

        with sounddevice.OutputStream(samplerate=device_rate, channels=1, dtype="float32", latency="high",
                                      callback=pull, finished_callback=done.set):
            while not done.wait(BLOCK_S):
                pass

    def stop(self) -> None:
        self._stopping.set()
