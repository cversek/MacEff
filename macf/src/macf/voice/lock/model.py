"""A voice lock: the enrolled operator's voice as a centroid of speaker embeddings, a threshold on
cosine similarity, and the test report that chose it (MIS-0008 R34 to R36, R45).

Saved as plain arrays with a JSON report, loaded without unpickling, like a wake model. A threshold
is never stored without its report (R35), and a report is refused unless its held-out set held
other speakers and synthetic speech (R36). A match is evidence, never proof of who spoke (R45).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

FORMAT = "macf-voice-lock/1"
#: What a report must carry for a threshold to be stored with it (R35, R36).
REPORT_FIELDS = ("false_accepts", "false_rejects", "held_out", "conditions")


class LockRefused(ValueError):
    """A voice lock that can't be stored or trained, with the reason."""


def check_report(report: dict) -> None:
    missing = [f for f in REPORT_FIELDS if f not in report]
    if missing:
        raise LockRefused(f"a voice lock's threshold is stored only with its test report; it lacks {missing} (R35)")
    held = report["held_out"]
    if not held.get("other_speaker") or not held.get("synthetic"):
        raise LockRefused("the held-out set must hold other speakers and synthetic speech, each annotated, "
                          f"before a threshold means anything; it held {held} (R36)")


@dataclass
class VoiceLock:
    centroid: np.ndarray
    threshold: float
    report: dict
    trained_at: float = field(default_factory=time.time)

    def score(self, embedding: np.ndarray) -> float:
        """Cosine similarity of one utterance's embedding to the enrolled voice."""
        e = np.asarray(embedding, dtype=np.float64)
        c = self.centroid
        return float(e @ c / (np.linalg.norm(e) * np.linalg.norm(c) + 1e-12))

    def matches(self, embedding: np.ndarray) -> bool:
        return self.score(embedding) >= self.threshold

    def save(self, path: Path) -> None:
        check_report(self.report)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {"format": FORMAT, "threshold": self.threshold, "trained_at": self.trained_at, "report": self.report}
        tmp = path.with_name(path.name + ".tmp.npz")
        np.savez(tmp, centroid=self.centroid.astype(np.float64), meta=np.array(json.dumps(meta)))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "VoiceLock":
        with np.load(Path(path), allow_pickle=False) as data:
            if "meta" not in data or "centroid" not in data:
                raise LockRefused(f"{path} is not a voice lock")
            meta = json.loads(str(data["meta"]))
            if meta.get("format") != FORMAT:
                raise LockRefused(f"{path} is {meta.get('format')!r}, not {FORMAT}")
            check_report(meta.get("report") or {})
            return cls(centroid=np.array(data["centroid"]), threshold=float(meta["threshold"]),
                       report=meta["report"], trained_at=float(meta["trained_at"]))
