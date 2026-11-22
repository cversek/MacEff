"""A voice lock trained from kept audio, under R63 read strictly (MIS-0008 R61 to R64; the reading agreed
on #1008).

Every copy of a kept recording the lock uses, and the trained lock itself, lives inside the kept-audio
folder and is registered against the recordings it came from, so deleting any one recording deletes its
clip and the lock. The lock is then gone, not stale: a declared lock whose model is missing refuses every
utterance (speaker_check), and it is retrained only when the operator asks.

Only recordings a training set may use go in: a known speaker whose consent is recorded (for_training).
Other speakers and synthetic speech are added to the same set by hand, as for any voice lock.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np

from macf.voice.kept import KeptStore
from macf.voice.lock.model import LockRefused, VoiceLock
from macf.voice.lock.train import LockSet, train
from macf.voice.wake.dataset import Clip, load_clip

Embed = Callable[[np.ndarray], np.ndarray]
#: The trained lock's name among the folder's derived items.
LOCK_NAME = "voice_lock.npz"
MISSING = ("the voice lock's model is gone (a recording it was trained on was deleted, or it was never "
           "trained): every utterance is refused until the operator retrains it")


class KeptLockSet(LockSet):
    """A voice lock's clip set kept inside the kept-audio folder, under the same protection as the voice
    it came from; a clip whose file was deleted with its recording is no longer listed."""

    def __init__(self, store: KeptStore):  # noqa: D107 - the set lives in the store's folder
        self.phrase = "voice lock"
        self.root = store.folder / "derived" / "lock"
        self.manifest = self.root / "manifest.jsonl"
        self.model_path = store.folder / "derived" / LOCK_NAME

    def clips(self, kind: Optional[str] = None, split: Optional[str] = None) -> List[Clip]:
        return [c for c in super().clips(kind, split) if c.path.exists()]


def lock_set_in(store: KeptStore) -> KeptLockSet:
    return KeptLockSet(store)


def _imported(store: KeptStore, lock_set: KeptLockSet) -> List[str]:
    """The recordings that have a clip in the set, by the derived items registered against them."""
    clips_dir = str(lock_set.root / "clips")
    return sorted(sha for sha, items in store._derived().items() if any(p.startswith(clips_dir) for p in items))


def import_consented(store: KeptStore, lock_set: KeptLockSet) -> int:
    """Add each consented, verified recording not yet in the set as an operator clip, registered against
    it. Returns how many were added."""
    done = set(_imported(store, lock_set))
    added = 0
    for rec in store.for_training():
        if rec.sha256 in done:
            continue
        clip = lock_set.add("operator", load_clip(rec.path), conditions="kept " + rec.trigger)
        store.register_derived(rec.sha256, clip.path)
        added += 1
    return added


def enroll_from_kept(store: KeptStore, lock_set: KeptLockSet, embed: Embed) -> Path:
    """Import the consented recordings, train, and save the lock as a derived item of every kept
    recording among its operator clips. Run on the operator's command only."""
    import_consented(store, lock_set)
    lock = train(lock_set, embed)
    used = _imported(store, lock_set)
    if not used:
        raise LockRefused("no kept recording went into this lock; nothing to register it against")
    return store.derive_shared(used, LOCK_NAME, lock.to_bytes())


def speaker_check(path: Path, embed: Embed) -> Tuple[Callable[[np.ndarray], bool], Optional[str]]:
    """The capture unit's speaker check for a declared lock at ``path``, and why it refuses everything
    (None when the lock loaded). A missing or unreadable model fails closed."""
    try:
        lock = VoiceLock.load(path)
    except (OSError, LockRefused, ValueError) as error:
        reason = MISSING if not Path(path).exists() else f"the voice lock can't be read ({error}); {MISSING}"
        return (lambda audio: False), reason
    return (lambda audio: lock.matches(embed(audio))), None
