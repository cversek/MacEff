"""Train a wake model from an agent's kept clips, and measure it on the clips held out (MIS-0008 R24, R25).

Ported from the first host's trainer. What carried over:
  * windows end-aligned as a streaming detector sees them, with random gaps, gains and room noise;
  * each stretch of ordinary speech up to a pause as its own negative, since speech followed by
    quiet looks most like a wake phrase;
  * three rounds of retraining with more weight on the negatives still scored high.
What changed:
  * the threshold is chosen from training scores only, so the held-out clips are never used to
    pick it and the report on them is a measurement, not a fit;
  * the report states its conditions, and counts false alarms per hour of held-out audio and
    false wakes on other agents' phrases (R24).

The detector is a low bar by design: a fire is checked again for speech and then by transcription
(R23), so the threshold trades only how often the transcriber runs.
"""
from __future__ import annotations

import time
from typing import Callable, List

import numpy as np

from macf.voice.capture.backends import FRAME, RATE
from macf.voice.wake.dataset import WakeSet, load_clip
from macf.voice.wake.model import WakeModel, fit_logistic

#: What 16 of openWakeWord's feature frames cover: the window the detector scores.
WINDOW = 2 * RATE
#: The fewest clips of the phrase to train on, and to hold out, before training is worth trying.
MIN_TRAIN_PHRASES = 12
MIN_TEST_PHRASES = 3

Embed = Callable[[List[np.ndarray]], np.ndarray]


class NotEnoughClips(ValueError):
    """Too few clips to train or to measure, with what is missing."""


def openwakeword_embed() -> Embed:
    """openWakeWord's speech features for whole windows, as the live detector computes them."""
    try:
        from openwakeword.utils import AudioFeatures
    except ImportError as e:
        raise RuntimeError("training needs openwakeword, which macf's voice extra installs: "
                           "pip install 'macf[voice]'") from e
    features = AudioFeatures()

    def embed(windows: List[np.ndarray]) -> np.ndarray:
        pcm = (np.clip(np.array(windows), -1, 1) * 32767).astype(np.int16)
        return features.embed_clips(pcm, batch_size=64)[:, -16:, :].reshape(len(windows), -1)
    return embed


def _speech_end(x: np.ndarray) -> int:
    hop = 800
    energy = np.array([np.sqrt((x[i:i + hop] ** 2).mean()) for i in range(0, max(1, x.size - hop), hop)])
    above = np.nonzero(energy > 0.15 * energy.max())[0] if energy.size and energy.max() > 0 else []
    return int((above[-1] + 1) * hop) if len(above) else x.size


def end_aligned(x: np.ndarray, tail: int) -> np.ndarray:
    """A window with the speech ending ``tail`` samples before its end."""
    x = x[:_speech_end(x)][-(WINDOW - tail):]
    out = np.zeros(WINDOW, np.float32)
    out[WINDOW - tail - x.size:WINDOW - tail] = x
    return out


def variants(x: np.ndarray, n: int, rng: np.random.Generator) -> List[np.ndarray]:
    out = []
    for _ in range(n):
        v = end_aligned(x, int(rng.integers(800, 6400))) * rng.uniform(0.5, 2.0)
        out.append(np.clip(v + rng.normal(0, rng.uniform(0.0003, 0.002), WINDOW), -1, 1).astype(np.float32))
    return out


def sliding(x: np.ndarray, hop: int) -> List[np.ndarray]:
    """Every window across a long clip, as the detector would see it streaming."""
    if x.size < WINDOW:
        x = np.r_[x, np.zeros(WINDOW - x.size, np.float32)]
    return [x[s:s + WINDOW] for s in range(0, x.size - WINDOW + 1, hop)]


def phrase_windows(x: np.ndarray, rng: np.random.Generator) -> List[np.ndarray]:
    """Each stretch of speech up to a pause, as its own negative."""
    hop = 800
    energy = np.array([np.sqrt((x[i:i + hop] ** 2).mean()) for i in range(0, max(1, x.size - hop), hop)])
    if not energy.size or energy.max() <= 0:
        return []
    loud = energy > 0.1 * energy.max()
    out, start = [], None
    for i, on in enumerate(loud):
        if on and start is None:
            start = i
        if not on and start is not None:
            seg = x[start * hop:(i + 1) * hop]
            if seg.size > 1600:
                out += variants(seg, 3, rng) + variants(seg[-RATE:], 3, rng)
            start = None
    return out


def train(wake: WakeSet, embed: Embed, seed: int = 7) -> WakeModel:
    """Fit a wake model on the train set, measure it on the test set, and keep both in the model file."""
    rng = np.random.default_rng(seed)
    train_phrases = wake.clips("phrase", "train")
    test_phrases = wake.clips("phrase", "test")
    if len(train_phrases) < MIN_TRAIN_PHRASES or len(test_phrases) < MIN_TEST_PHRASES:
        raise NotEnoughClips(f"{len(train_phrases)} phrase clips to train on and {len(test_phrases)} held out; "
                             f"record at least {MIN_TRAIN_PHRASES + MIN_TEST_PHRASES} of the phrase")
    positives: List[np.ndarray] = []
    negatives: List[np.ndarray] = []
    used = []
    for clip in train_phrases:
        positives += variants(load_clip(clip.path), 12, rng)
        used.append(clip.clip_id)
    for kind, n in (("near_miss", 30), ("other_phrase", 30)):
        for clip in wake.clips(kind, "train"):
            negatives += variants(load_clip(clip.path), n, rng)
            used.append(clip.clip_id)
    for kind in ("speech", "room"):
        for clip in wake.clips(kind, "train"):
            x = load_clip(clip.path)
            negatives += [w * rng.uniform(0.5, 1.5) for w in sliding(x, FRAME if kind == "speech" else 3200)]
            if kind == "speech":
                negatives += phrase_windows(x, rng)
            used.append(clip.clip_id)
    negatives += [rng.normal(0, rng.uniform(0.0003, 0.003), WINDOW).astype(np.float32) for _ in range(100)]
    X = np.vstack([embed(positives), embed(negatives)])
    y = np.r_[np.ones(len(positives)), np.zeros(len(negatives))]
    weights = np.ones(len(y))
    w, b = fit_logistic(X, y)
    for _ in range(3):
        scores = WakeModel(weights=w, bias=b, threshold=0.5, phrase=wake.phrase).predict_proba(X)[:, 1]
        weights[(y == 0) & (scores > 0.3)] *= 4
        w, b = fit_logistic(X, y, sample_weight=weights)
    scores = WakeModel(weights=w, bias=b, threshold=0.5, phrase=wake.phrase).predict_proba(X)[:, 1]
    negative_ceiling = float(np.quantile(scores[y == 0], 0.999))
    positive_floor = float(np.quantile(scores[y == 1], 0.05))
    threshold = float(np.clip((negative_ceiling + positive_floor) / 2, 0.3, 0.95))
    model = WakeModel(weights=w, bias=b, threshold=threshold, phrase=wake.phrase,
                      report={"trained_on": sorted(used)})
    model.report.update(measure(wake, model, embed, rng))
    return model


def measure(wake: WakeSet, model: WakeModel, embed: Embed, rng: np.random.Generator) -> dict:
    """What the model does on the held-out clips alone (R24, R25)."""
    def best(path) -> float:
        return float(model.predict_proba(embed(variants(load_clip(path), 5, rng)))[:, 1].max())

    held = {kind: wake.clips(kind, "test") for kind in ("phrase", "near_miss", "other_phrase", "speech", "room")}
    phrase_scores = [best(c.path) for c in held["phrase"]]
    near = [best(c.path) for c in held["near_miss"]]
    other = [best(c.path) for c in held["other_phrase"]]
    fires, seconds = 0, 0.0
    for clip in held["speech"] + held["room"]:
        x = load_clip(clip.path)
        seconds += x.size / RATE
        scores = model.predict_proba(embed(sliding(x, FRAME)))[:, 1]
        above = scores >= model.threshold
        fires += int(np.sum(above[1:] & ~above[:-1]) + (above[0] if above.size else 0))  # each run of fires once
    conditions = sorted({c.conditions for clips in held.values() for c in clips if c.conditions})
    return {
        "measured_at": time.time(),
        "threshold_from": "training scores only; the held-out clips below were never used to choose it",
        "held_out": {kind: len(clips) for kind, clips in held.items()},
        "misses": sum(s < model.threshold for s in phrase_scores),
        "phrase_scores": [round(s, 3) for s in sorted(phrase_scores)],
        "near_miss_fires": sum(s >= model.threshold for s in near),
        "other_phrase_fires": sum(s >= model.threshold for s in other),
        "false_alarms": fires,
        "background_seconds": round(seconds, 1),
        "false_alarms_per_hour": round(fires / (seconds / 3600.0), 2) if seconds else None,
        "conditions": conditions,
        "caveat": "a held-out test measures what was held out; only live use measures the real room",
    }
