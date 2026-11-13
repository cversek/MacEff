"""A wake model: a logistic regression over openWakeWord's speech features, with the test report that
justifies its threshold stored in the same file (MIS-0008 R24).

Saved as plain arrays in a ``.npz`` file and loaded with ``allow_pickle=False``. A wake model is a
file in an agent's home that a long-lived unit reads, and a pickled model would run whatever code
the file held; weights and a JSON report can only be numbers and text.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

#: The format this module writes and reads. Anything else is refused, never guessed at.
FORMAT = "macf-wake-model/1"


@dataclass
class WakeModel:
    """Weights, bias, the threshold, and the report the threshold was chosen from."""

    weights: np.ndarray
    bias: float
    threshold: float
    phrase: str
    report: dict = field(default_factory=dict)
    trained_at: float = field(default_factory=time.time)

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Scikit-learn's shape: one row per sample, columns (not the phrase, the phrase)."""
        z = np.asarray(features, dtype=np.float64) @ self.weights + self.bias
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))
        return np.column_stack([1.0 - p, p])

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {"format": FORMAT, "phrase": self.phrase, "threshold": self.threshold, "bias": self.bias,
                "trained_at": self.trained_at, "report": self.report}
        tmp = path.with_name(path.name + ".tmp.npz")
        np.savez(tmp, weights=self.weights.astype(np.float64), meta=np.array(json.dumps(meta)))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "WakeModel":
        with np.load(Path(path), allow_pickle=False) as data:
            if "meta" not in data or "weights" not in data:
                raise ValueError(f"{path} is not a wake model: it holds no weights and meta")
            meta = json.loads(str(data["meta"]))
            if meta.get("format") != FORMAT:
                raise ValueError(f"{path} is {meta.get('format')!r}, not {FORMAT}; train it again with "
                                 f"macf_tools voice wake train")
            return cls(weights=np.array(data["weights"]), bias=float(meta["bias"]),
                       threshold=float(meta["threshold"]), phrase=meta["phrase"], report=meta.get("report") or {},
                       trained_at=float(meta["trained_at"]))


def fit_logistic(features: np.ndarray, labels: np.ndarray, sample_weight: Optional[np.ndarray] = None,
                 l2: float = 200.0, steps: int = 600, rate: float = 0.05) -> tuple:
    """A weighted, L2-regularized logistic regression by Adam, with each class weighted to balance
    (as ``class_weight="balanced"``). Returns (weights, bias). ``l2`` plays the part of 1/C."""
    X = np.asarray(features, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    n, d = X.shape
    w_sample = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=np.float64)
    for cls in (0.0, 1.0):
        mask = y == cls
        if mask.any():
            w_sample[mask] *= n / (2.0 * mask.sum())
    w_sample /= w_sample.sum()
    w, b = np.zeros(d), 0.0
    m = np.zeros(d + 1)
    v = np.zeros(d + 1)
    for t in range(1, steps + 1):
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ w + b, -60, 60)))
        err = (p - y) * w_sample
        grad = np.r_[X.T @ err + (l2 / n) * w, err.sum()]
        m = 0.9 * m + 0.1 * grad
        v = 0.999 * v + 0.001 * grad * grad
        step = rate * (m / (1 - 0.9 ** t)) / (np.sqrt(v / (1 - 0.999 ** t)) + 1e-8)
        w -= step[:-1]
        b -= step[-1]
    return w, float(b)
