"""The capture unit's models on real audio: the speech gate and the wake detector (MIS-0008 R23).

Both come from openWakeWord, as on the first host that ran this: Silero's speech detector for the
gate, and openWakeWord's audio features under a small trained classifier for the wake phrase. They
are imported only here, when a capture unit starts, and a missing one is named with the extra that
installs it.

Lessons carried from that host:
  * the gate reads speech, not volume: on the operator's clips at a 0.3 bar, taps, chewing, sniffs
    and the room scored as no speech, a cough barely, and his sentences clearly;
  * a quiet call needs its level raised before the gate reads it, up to 24 dB, or it is missed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from macf.voice.capture.backends import FRAME, SpeechGate, WakeDetector

#: Silero's score at which a frame counts as speech.
SPEECH_PROB = 0.3
#: The most a quiet frame's level is raised before the gate reads it (24 dB).
MAX_GAIN = 16.0
#: The wake classifier reads this many of openWakeWord's feature frames.
FEATURE_FRAMES = 16

MISSING = ("{what} needs {module}, which macf's voice extra installs: "
           "pip install 'macf[voice]' in the interpreter the capture unit runs")


def _need(module: str, what: str):
    try:
        return __import__(module, fromlist=["_"])
    except ImportError as e:
        raise RuntimeError(MISSING.format(what=what, module=module)) from e


class SileroGate(SpeechGate):
    """Speech or not, by Silero, on each frame with its level raised as far as MAX_GAIN."""

    def __init__(self, threshold: float = SPEECH_PROB):
        vad = _need("openwakeword.vad", "the speech gate")
        self._vad = vad.VAD()
        self.threshold = threshold

    def is_speech(self, frame: np.ndarray) -> bool:
        x = frame.astype(np.float64)
        x = x * min(MAX_GAIN, 16384.0 / max(1.0, float(np.abs(x).max())))
        pcm = np.clip(x, -32768, 32767).astype(np.int16)
        return float(self._vad.predict(pcm, frame_size=480)) >= self.threshold

    def reset(self) -> None:
        self._vad.reset_states()


class TrainedWakeDetector(WakeDetector):
    """openWakeWord's features under the agent's own wake model (``macf.voice.wake.model``), as
    ``macf_tools voice wake train`` writes it: plain weights, loaded without unpickling anything."""

    def __init__(self, model_path: Path):
        from macf.voice.wake.model import WakeModel
        utils = _need("openwakeword.utils", "the wake detector")
        try:
            self._clf = WakeModel.load(model_path)
            #: The bar its test report measured (R24), used unless the voice section overrides it.
            self.threshold = self._clf.threshold
        except (OSError, ValueError) as e:
            raise RuntimeError(f"the wake model can't be read: {e}") from e
        self._features_cls = utils.AudioFeatures
        self._features = self._features_cls()

    def score(self, frame: np.ndarray) -> float:
        if frame.size != FRAME:
            raise ValueError(f"the wake detector takes frames of {FRAME} samples, not {frame.size}")
        self._features(frame)
        features = self._features.get_features(FEATURE_FRAMES).reshape(1, -1)
        return float(self._clf.predict_proba(features)[0, 1])

    def reset(self) -> None:
        self._features = self._features_cls()
