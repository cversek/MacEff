"""An agent's wake-phrase clips: what was recorded, of what kind, and which set each belongs to
(MIS-0008 R24, R25).

Each clip's set, train or test, is fixed the moment it is recorded and kept in the manifest; it
never moves. Training reads only the train set and the test only the test set, so no clip a model
trained on can ever be in the numbers that justify it (R25). One clip in every four of each kind
is held out.

These clips are kept on purpose: the operator records them for training, and they stay in the
agent's home until deleted. They are not the capture unit's audio, which is never written (R13).

Layout, under the agent's home:
    .maceff/voice/wake/<phrase slug>/phrase.json      the phrase, and when it was defined
    .maceff/voice/wake/<phrase slug>/manifest.jsonl   one line per clip
    .maceff/voice/wake/<phrase slug>/clips/<kind>/<id>.wav
    .maceff/voice/wake/<phrase slug>/model.npz        the trained model, with its report
"""
from __future__ import annotations

import json
import sys
import re
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from macf.voice.capture.backends import RATE
from macf.voice.state import voice_dir

#: What a clip can be:
#:   phrase        the wake phrase, said by the operator
#:   near_miss     something that sounds close but isn't it
#:   speech        ordinary talk, read or spoken
#:   room          the room with nobody speaking: fans, keys, the street
#:   other_phrase  another agent's wake phrase on this machine, which must not wake this one (R24)
from macf.voice.wake import KINDS, PhraseRefused  # noqa: E402,F401 - defined in the light package init for the CLI
#: One clip in this many, of each kind, is held out for the test.
HOLD_OUT_EVERY = 4
#: Phrases too common in ordinary talk to make a wake: they would fire all day.
COMMON = {"hey", "hello", "hi", "okay", "ok", "yes", "no", "stop", "go", "wait", "computer", "listen",
          "hey you", "excuse me", "thank you", "thanks"}




def slug(phrase: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", phrase.lower()).strip("_")


def check_phrase(phrase: str) -> str:
    """The phrase, normalized, or PhraseRefused naming why it can't work."""
    words = re.findall(r"[a-z']+", phrase.lower())
    normalized = " ".join(words)
    if len(words) < 2:
        raise PhraseRefused(f"{phrase!r} is one word; a wake phrase needs two or more, or ordinary talk sets it off")
    if sum(len(w) for w in words) < 5:
        raise PhraseRefused(f"{phrase!r} is too short to tell apart from other speech; use a longer phrase")
    if normalized in COMMON:
        raise PhraseRefused(f"{phrase!r} is said too often in ordinary talk to be a wake phrase")
    return normalized


@dataclass(frozen=True, kw_only=True)
class Clip:
    clip_id: str
    kind: str
    split: str
    path: Path
    recorded_at: float
    conditions: str


def defined_phrases(home: Path) -> List[str]:
    """Every wake phrase defined in ``home``, as ``define`` recorded it, in name order. A folder whose
    phrase file can't be read is skipped and said on stderr, never guessed at."""
    found = []
    for path in sorted((voice_dir(home) / "wake").glob("*/phrase.json")):
        try:
            found.append(str(json.loads(path.read_text())["phrase"]))
        except (OSError, ValueError, KeyError) as e:
            print(f"⚠️ MACF: voice: {path} can't be read, so its phrase is not offered: {e}", file=sys.stderr)
    return found


class WakeSet:
    """The clips for one agent's wake phrase."""

    #: The kinds of clip this store keeps; a voice lock's store keeps its own.
    kinds = KINDS

    def __init__(self, home: Path, phrase: str):
        self.phrase = check_phrase(phrase)
        self.root = voice_dir(home) / "wake" / slug(self.phrase)
        self.manifest = self.root / "manifest.jsonl"
        self.model_path = self.root / "model.npz"

    def define(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "phrase.json"
        if not path.exists():
            path.write_text(json.dumps({"phrase": self.phrase, "defined_at": time.time()}) + "\n")

    def clips(self, kind: Optional[str] = None, split: Optional[str] = None) -> List[Clip]:
        if not self.manifest.exists():
            return []
        out = []
        for line in self.manifest.read_text().splitlines():
            row = json.loads(line)
            if (kind is None or row["kind"] == kind) and (split is None or row["split"] == split):
                out.append(Clip(clip_id=row["id"], kind=row["kind"], split=row["split"],
                                path=self.root / row["path"], recorded_at=row["recorded_at"],
                                conditions=row.get("conditions", "")))
        return out

    def counts(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {k: {"train": 0, "test": 0} for k in self.kinds}
        for clip in self.clips():
            out[clip.kind][clip.split] += 1
        return out

    def add(self, kind: str, samples: np.ndarray, conditions: str = "") -> Clip:
        """Keep one clip of ``kind``. Its set is decided now, by its place among the clips of its
        kind, and written beside it; nothing ever changes it."""
        if kind not in self.kinds:
            raise ValueError(f"unknown clip kind {kind!r}; one of {', '.join(self.kinds)}")
        self.define()
        index = len(self.clips(kind))
        split = "test" if index % HOLD_OUT_EVERY == HOLD_OUT_EVERY - 1 else "train"
        clip_id = f"{kind}-{time.time_ns()}"
        rel = Path("clips") / kind / f"{clip_id}.wav"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        pcm = np.asarray(samples)
        if pcm.dtype != np.int16:
            pcm = (np.clip(pcm, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        row = {"id": clip_id, "kind": kind, "split": split, "path": str(rel), "recorded_at": time.time(),
               "conditions": conditions}
        with self.manifest.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return Clip(clip_id=clip_id, kind=kind, split=split, path=path, recorded_at=row["recorded_at"],
                    conditions=conditions)


def load_clip(path: Path) -> np.ndarray:
    """A kept clip's samples as float32 in -1..1."""
    with wave.open(str(path)) as w:
        if w.getframerate() != RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path} is not 16 kHz mono 16-bit, as every kept clip is")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
