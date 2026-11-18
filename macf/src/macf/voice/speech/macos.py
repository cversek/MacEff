"""Speech playback on macOS (MIS-0008; docs/VOICE_PORTING.md section 6): PortAudio through ``sounddevice``.

Samples go from memory to the default output in short blocks, so ``stop`` takes effect within one
block from any thread (R29: speech stops when a recording opens). No file is written.
"""
from __future__ import annotations

import threading

import numpy as np

from macf.voice.speech.backends import AudioOut, Spoken

#: How much audio is handed to the device at a time; the longest a stop waits to be heard.
BLOCK_S = 0.05


class MacAudioOut(AudioOut):
    """The default output device; ``play`` blocks until the sentence ends or ``stop`` is called."""

    def __init__(self) -> None:
        self._stopping = threading.Event()

    def play(self, spoken: Spoken) -> None:
        import sounddevice
        self._stopping.clear()
        samples = np.asarray(spoken.samples, dtype=np.float32).reshape(-1, 1)
        block = max(1, int(spoken.rate * BLOCK_S))
        with sounddevice.OutputStream(samplerate=spoken.rate, channels=1, dtype="float32") as stream:
            for start in range(0, len(samples), block):
                if self._stopping.is_set():
                    break
                stream.write(samples[start:start + block])

    def stop(self) -> None:
        self._stopping.set()
