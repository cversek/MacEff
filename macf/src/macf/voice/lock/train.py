"""Enroll the operator's voice and measure the lock against other speakers and synthetic speech
(MIS-0008 R35, R36).

Clips are annotated by who spoke: the operator, another speaker, or synthetic speech. As for a
wake model, each clip's set is fixed when it is recorded. The lock is the centroid of the operator's
training embeddings; its threshold is chosen from training scores only, and the held-out report of
false accepts and false rejects is stored with it.

The speaker embedder is injected. Which model embeds speakers well enough is a measurement to make
on the operator's own voice, live, before any lock is trusted; a borrowed embedding can measure
clip length instead of the speaker, so its sanity is checked on the operator's clips first.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import numpy as np

from macf.voice.lock.model import LockRefused, VoiceLock, check_report
from macf.voice.state import voice_dir
from macf.voice.wake.dataset import WakeSet, load_clip

#: Who spoke a kept clip.
KINDS = ("operator", "other_speaker", "synthetic")
MIN_TRAIN_OPERATOR = 9

Embed = Callable[[np.ndarray], np.ndarray]


class LockSet(WakeSet):
    """The annotated clips for one agent's voice lock: the same split rule as a wake set."""

    kinds = KINDS

    def __init__(self, home: Path):  # noqa: D107 - a wake set without a phrase
        self.phrase = "voice lock"
        self.root = voice_dir(home) / "lock"
        self.manifest = self.root / "manifest.jsonl"
        self.model_path = self.root / "lock.npz"


def train(lock: LockSet, embed: Embed) -> VoiceLock:
    """Enroll from the operator's training clips; measure on every held-out clip."""
    operator = [embed(load_clip(c.path)) for c in lock.clips("operator", "train")]
    if len(operator) < MIN_TRAIN_OPERATOR:
        raise LockRefused(f"{len(operator)} operator clips to enroll from; record at least "
                          f"{MIN_TRAIN_OPERATOR * 4 // 3 + 1} of the operator")
    centroid = np.mean([e / (np.linalg.norm(e) + 1e-12) for e in operator], axis=0)
    draft = VoiceLock(centroid=centroid, threshold=0.0, report={})
    own = [draft.score(e) for e in operator]
    others = [draft.score(embed(load_clip(c.path))) for k in ("other_speaker", "synthetic")
              for c in lock.clips(k, "train")]
    # Midway between the operator's low scores and the others' high ones, from training clips only.
    floor = float(np.quantile(own, 0.1))
    ceiling = float(max(others)) if others else floor - 0.1
    threshold = float((floor + ceiling) / 2)
    held = {k: lock.clips(k, "test") for k in KINDS}

    def scores(kind):
        return [draft.score(embed(load_clip(c.path))) for c in held[kind]]

    report = {
        "measured_at": time.time(),
        "threshold_from": "training scores only; the held-out clips below were never used to choose it",
        "held_out": {k: len(v) for k, v in held.items()},
        "false_rejects": sum(s < threshold for s in scores("operator")),
        "false_accepts": {k: sum(s >= threshold for s in scores(k)) for k in ("other_speaker", "synthetic")},
        "conditions": sorted({c.conditions for clips in held.values() for c in clips if c.conditions}),
        "trained_on": sorted(c.clip_id for k in KINDS for c in lock.clips(k, "train")),
        "caveat": "a match is evidence, never proof of who spoke; a recording or a cloned voice can pass",
    }
    check_report(report)
    return VoiceLock(centroid=centroid, threshold=threshold, report=report)
