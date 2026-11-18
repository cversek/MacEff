"""Kept audio (MIS-0008 R13 as amended, R61 to R64): the operator's recordings, kept for building a voice lock.

Off unless the voice section names a folder (``kept_audio``). Each delivered recording becomes one WAV in
that folder, named by its SHA-256, with a small JSON beside it (trigger, time, speaker, the words). The
folder and its files are readable by the unit's own account alone (R61). Each keep is an event holding the
hash, the trigger and the time, never the words or the audio (R62).

Anything made from a recording (an embedding, a spectrogram, a place in a training set) is registered
against its hash in ``derived.json``, and only inside the folder; deleting the recording deletes all of
it (R63). A training set takes only recordings whose speaker has consent recorded in ``consent.json``,
which the operator writes; nothing said elsewhere reaches it (R64).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

#: The event a keep records (R62).
EVENT_AUDIO_KEPT = "voice_audio_kept"
#: The event a deletion records, with the hash and how many items went with it (R63).
EVENT_AUDIO_DELETED = "voice_audio_deleted"
RATE = 16000


@dataclass(frozen=True)
class KeptRecording:
    sha256: str
    path: Path
    trigger: str
    spoken_at: float
    speaker: str


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _default_record(name: str, data: dict) -> None:
    from macf.agent_events_log import append_event
    append_event(name, data)


class KeptStore:
    """One agent's kept recordings, under one declared folder."""

    def __init__(self, folder: Path, record: Callable[[str, dict], None] = _default_record,
                 speaker: str = "operator"):
        self.folder = Path(folder)
        self._record = record
        self.speaker = speaker
        _private_dir(self.folder)

    # ------------------------------------------------------------------ keeping

    def keep(self, audio, trigger: str, spoken_at: float, text: str = "",
             speaker: Optional[str] = None) -> KeptRecording:
        """Write one recording as 16 kHz mono 16-bit WAV, named by its hash, and record the keep (R61, R62)."""
        import numpy as np   # here, not at import: building the voice CLI must load no voice models
        samples = np.asarray(audio, dtype=np.int16)
        sha = hashlib.sha256(samples.tobytes()).hexdigest()
        path = self.folder / f"{sha}.wav"
        tmp = self.folder / f".{sha}.wav.tmp"
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(samples.tobytes())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        who = speaker or self.speaker
        meta = {"sha256": sha, "trigger": trigger, "spoken_at": spoken_at, "speaker": who,
                "seconds": round(samples.size / RATE, 3), "text": text, "kept_at": time.time()}
        _write_private(self.folder / f"{sha}.json", json.dumps(meta, indent=1).encode())
        self._record(EVENT_AUDIO_KEPT, {"sha256": sha, "trigger": trigger, "spoken_at": spoken_at})
        return KeptRecording(sha, path, trigger, spoken_at, who)

    def recordings(self) -> List[KeptRecording]:
        out = []
        for meta_path in sorted(self.folder.glob("*.json")):
            if meta_path.name in ("derived.json", "consent.json"):
                continue
            meta = json.loads(meta_path.read_text())
            out.append(KeptRecording(meta["sha256"], self.folder / f"{meta['sha256']}.wav", meta["trigger"],
                                     meta["spoken_at"], meta.get("speaker", self.speaker)))
        return out

    # ------------------------------------------------------------------ what is derived, and deleting it

    def _derived(self) -> Dict[str, List[str]]:
        path = self.folder / "derived.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def register_derived(self, sha256: str, item: Path) -> None:
        """Record that ``item`` was made from the recording ``sha256``, so deleting it takes ``item`` too (R63).
        Derived items live inside the folder, under the same protection as the voice they came from."""
        item = Path(item).resolve()
        if self.folder.resolve() not in item.parents:
            raise ValueError(f"{item} is outside the kept-audio folder {self.folder}; derived voice stays inside it")
        table = self._derived()
        table.setdefault(sha256, [])
        if str(item) not in table[sha256]:
            table[sha256].append(str(item))
        _write_private(self.folder / "derived.json", json.dumps(table, indent=1).encode())

    def delete(self, sha256: str) -> List[Path]:
        """Delete a recording and everything registered as derived from it (R63). Returns what was removed."""
        table = self._derived()
        targets = [self.folder / f"{sha256}.wav", self.folder / f"{sha256}.json"]
        targets += [Path(p) for p in table.pop(sha256, [])]
        removed = []
        for target in targets:
            if target.exists():
                target.unlink()
                removed.append(target)
        _write_private(self.folder / "derived.json", json.dumps(table, indent=1).encode())
        self._record(EVENT_AUDIO_DELETED, {"sha256": sha256, "items": len(removed)})
        return removed

    # ------------------------------------------------------------------ consent and training (R64)

    def _consent(self) -> Dict[str, dict]:
        path = self.folder / "consent.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def record_consent(self, speaker: str, by: str) -> None:
        """The operator records that ``speaker`` consents to their recordings being used for training."""
        table = self._consent()
        table[speaker] = {"recorded_at": time.time(), "by": by}
        _write_private(self.folder / "consent.json", json.dumps(table, indent=1).encode())

    def for_training(self) -> List[KeptRecording]:
        """The recordings a training set may use: only those whose speaker's consent is recorded (R64)."""
        consented = self._consent()
        return [r for r in self.recordings() if r.speaker in consented]


# ---------------------------------------------------------------------- the command line


def _store_for_home():
    from macf.pd.core import load_declaration
    from macf.pd.interface import agent_card
    from macf.utils.paths import find_agent_home
    home = Path(find_agent_home())
    voice = load_declaration(home, agent_card(home)).voice
    if voice is None or not voice.kept_audio:
        return None
    folder = Path(voice.kept_audio)
    return KeptStore(folder if folder.is_absolute() else home / folder, speaker=voice.kept_speaker or "operator")


def add_parsers(voice_sub) -> None:
    kept = voice_sub.add_parser("kept", help="the recordings kept for the voice lock (MIS-0008 R61 to R64)")
    sub = kept.add_subparsers(dest="voice_kept_cmd")
    sub.add_parser("list", help="each kept recording: hash, trigger, length, speaker").set_defaults(func=cmd_list)
    delete = sub.add_parser("delete", help="delete a recording and everything derived from it (R63)")
    delete.add_argument("sha256")
    delete.set_defaults(func=cmd_delete)
    consent = sub.add_parser("consent", help="record that a speaker consents to training on their recordings (R64)")
    consent.add_argument("speaker")
    consent.add_argument("--by", required=True, help="who recorded the consent, and how it was given")
    consent.set_defaults(func=cmd_consent)


def cmd_list(args) -> int:
    store = _store_for_home()
    if store is None:
        print("no kept audio: the voice section declares no kept_audio folder")
        return 0
    recs = store.recordings()
    for r in recs:
        print(f"{r.sha256[:12]}  {r.trigger:<15} {r.speaker:<10} {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r.spoken_at))}")
    print(f"{len(recs)} kept in {store.folder}; {len(store.for_training())} usable for training (consent recorded)")
    return 0


def cmd_delete(args) -> int:
    store = _store_for_home()
    if store is None:
        print("no kept audio is declared")
        return 1
    matches = [r.sha256 for r in store.recordings() if r.sha256.startswith(args.sha256)]
    if len(matches) != 1:
        print(f"{args.sha256!r} matches {len(matches)} recordings; give more of the hash")
        return 1
    removed = store.delete(matches[0])
    print(f"deleted {matches[0][:12]} and {len(removed) - 2} item(s) derived from it")
    return 0


def cmd_consent(args) -> int:
    store = _store_for_home()
    if store is None:
        print("no kept audio is declared")
        return 1
    store.record_consent(args.speaker, by=args.by)
    print(f"consent recorded for {args.speaker} in {store.folder / 'consent.json'}")
    return 0
