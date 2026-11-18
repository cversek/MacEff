"""Kept audio (MIS-0008 R13 as amended, R61 to R64): off unless declared, one private folder, an event without
content for each keep, and deletion that takes everything derived from the recording with it."""
import os
import stat
import wave

import numpy as np
import pytest

from macf.voice import kept


def tone(seconds=0.5):
    t = np.arange(int(16000 * seconds)) / 16000
    return (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)


def test_kept_audio_goes_only_under_the_declared_folder_for_its_account_alone(tmp_path):
    """R61."""
    store = kept.KeptStore(tmp_path / "kept")
    record = store.keep(tone(), trigger="hold_key", spoken_at=1795029317.5, text="testing one two three")
    folder = tmp_path / "kept"
    assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700
    assert record.path.parent == folder and stat.S_IMODE(os.stat(record.path).st_mode) == 0o600
    with wave.open(str(record.path)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
    with pytest.raises(ValueError, match="outside"):
        store.register_derived(record.sha256, tmp_path / "elsewhere.npy")


def test_a_kept_recording_is_an_event_without_content(tmp_path):
    """R62: the hash, the trigger and the time; never the words or the audio."""
    events = []
    store = kept.KeptStore(tmp_path / "kept", record=lambda name, data: events.append((name, data)))
    record = store.keep(tone(), trigger="wake_phrase", spoken_at=1795029317.5, text="a private sentence")
    (name, data), = events
    assert name == "voice_audio_kept"
    assert data == {"sha256": record.sha256, "trigger": "wake_phrase", "spoken_at": 1795029317.5}


def test_deleting_a_kept_recording_deletes_what_was_derived_from_it(tmp_path):
    """R63: a derived item is registered against its recording, and goes with it."""
    store = kept.KeptStore(tmp_path / "kept")
    record = store.keep(tone(), trigger="hold_key", spoken_at=1.0, text="x")
    embedding = tmp_path / "kept" / "derived" / f"{record.sha256}.embedding.npy"
    embedding.parent.mkdir(parents=True, exist_ok=True)
    embedding.write_bytes(b"\x00")
    store.register_derived(record.sha256, embedding)
    removed = store.delete(record.sha256)
    assert not record.path.exists() and not embedding.exists()
    assert set(removed) >= {record.path, embedding}
    assert store.recordings() == []


def test_a_training_set_takes_only_speakers_whose_consent_is_recorded(tmp_path):
    """R64's record: the builder reads it, and an operator's word elsewhere doesn't reach it."""
    store = kept.KeptStore(tmp_path / "kept")
    store.keep(tone(), trigger="hold_key", spoken_at=1.0, text="x", speaker="operator", voice_lock="matched")
    store.keep(tone(0.7), trigger="hold_key", spoken_at=2.0, text="y", speaker="visitor", voice_lock="matched")
    assert store.for_training() == []
    store.record_consent("operator", by="the operator, typed")
    assert [r.speaker for r in store.for_training()] == ["operator"]


def test_a_recording_no_voice_lock_vouched_for_is_unverified_and_never_trained_on_unconfirmed(tmp_path):
    """R64 is a person's consent: without a voice-lock match, the declared speaker is not assumed."""
    store = kept.KeptStore(tmp_path / "kept", speaker="operator")
    record = store.keep(tone(), trigger="wake_phrase", spoken_at=1.0, text="x")   # voice lock not declared
    store.record_consent("operator", by="the operator, typed")
    assert record.speaker == kept.UNVERIFIED and store.for_training() == []
    store.confirm_speaker(record.sha256, "operator")
    assert [r.sha256 for r in store.for_training()] == [record.sha256]


def test_derive_writes_inside_the_folder_and_a_derived_directory_goes_with_its_recording(tmp_path):
    """R63 made unavoidable: derive registers as it writes, and deletion handles a directory too."""
    store = kept.KeptStore(tmp_path / "kept")
    record = store.keep(tone(), trigger="hold_key", spoken_at=1.0, text="x")
    item = store.derive(record.sha256, "embedding.npy", b"\x00\x01")
    assert stat.S_IMODE(os.stat(item).st_mode) == 0o600 and item.parent.parent == tmp_path / "kept"
    folder = tmp_path / "kept" / "derived" / f"{record.sha256}.spectrograms"
    folder.mkdir()
    (folder / "0.png").write_bytes(b"x")
    store.register_derived(record.sha256, folder)
    removed = store.delete(record.sha256)
    assert not item.exists() and not folder.exists() and not record.path.exists()
    assert len(removed) == 4


def test_a_delivered_utterance_is_kept_whole_and_nothing_is_kept_when_off():
    """The unit hands every frame of a delivered recording to the store, streamed-ahead stretches
    included; with no store (the default) it keeps nothing, and R13's never-written test still holds."""
    from voice_fakes import SPEECH, FakeAudio, ScriptedTranscriber, make_unit
    kept_calls = []
    rig = make_unit(FakeAudio().then((SPEECH, 10)), ScriptedTranscriber("held words"))
    rig.unit.keep = lambda audio, **meta: kept_calls.append((audio.size, meta))
    rig.run(2)
    rig.keys.press("KEY_F9")
    rig.run(8)
    rig.keys.release("KEY_F9")
    rig.run(3)
    assert len(rig.delivered) == 1
    (size, meta), = kept_calls
    assert size > 0 and meta["trigger"] == "hold_key" and meta["text"] == "held words"
    off = make_unit(FakeAudio().then((SPEECH, 10)), ScriptedTranscriber("held words"))
    assert off.unit.keep is None
