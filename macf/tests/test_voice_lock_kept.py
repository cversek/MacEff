"""The voice lock trained from kept audio under R63: everything made from a recording, the trained lock
included, goes when that recording is deleted, and a declared lock whose model is gone refuses."""
import numpy as np

from macf.voice import kept
from macf.voice.lock import kept_enroll

RATE = 16000


def voice(pitch_hz, seconds=0.4, seed=0):
    t = np.arange(int(RATE * seconds)) / RATE
    noise = np.random.default_rng(seed).normal(0, 0.01, t.size)
    return ((np.sin(2 * np.pi * pitch_hz * t) * 0.3 + noise) * 32767).astype(np.int16)


def embed(samples):
    """A stand-in speaker embedder: the dominant frequency, which tells the test voices apart."""
    x = np.asarray(samples, dtype=np.float64)
    spectrum = np.abs(np.fft.rfft(x))
    peak = float(np.argmax(spectrum[1:]) + 1)
    return np.array([np.cos(peak / 200.0), np.sin(peak / 200.0), 1.0])


def consented_store(tmp_path, recordings=12):
    store = kept.KeptStore(tmp_path / "kept", record=lambda name, data: None)
    shas = [store.keep(voice(220, seed=i), trigger="hold_key", spoken_at=float(i), text="x",
                       voice_lock="matched").sha256 for i in range(recordings)]
    store.record_consent("operator", by="test")
    return store, shas


def others(lock_set):
    for i in range(4):
        lock_set.add("other_speaker", voice(330, seed=100 + i))
        lock_set.add("synthetic", voice(440, seed=200 + i))


def test_a_shared_derived_item_is_registered_against_every_recording_it_came_from(tmp_path):
    store, shas = consented_store(tmp_path, recordings=3)
    item = store.derive_shared(shas, "voice_lock.npz", b"model")
    assert item.parent == store.folder / "derived"
    store.delete(shas[1])
    assert not item.exists()  # deleting any one recording takes the shared item with it


def test_enrollment_from_kept_audio_keeps_every_copy_inside_the_folder_and_registered(tmp_path):
    store, shas = consented_store(tmp_path)
    lock_set = kept_enroll.lock_set_in(store)
    others(lock_set)
    path = kept_enroll.enroll_from_kept(store, lock_set, embed)
    assert store.folder in path.parents and path.exists()
    for clip in lock_set.clips("operator"):
        assert store.folder in clip.path.parents
    store.delete(shas[0])
    assert not path.exists()  # the trained lock went with the recording
    assert all(c.path.exists() for c in lock_set.clips("operator"))  # the deleted one's clip is gone from the set


def test_a_declared_lock_whose_model_is_gone_refuses_every_utterance(tmp_path):
    check, reason = kept_enroll.speaker_check(tmp_path / "kept" / "derived" / "voice_lock.npz", embed)
    assert reason and "retrain" in reason
    assert check(voice(220)) is False  # fail closed: no model, no match


def test_a_present_lock_matches_its_operator_and_not_another_voice(tmp_path):
    store, shas = consented_store(tmp_path)
    lock_set = kept_enroll.lock_set_in(store)
    others(lock_set)
    path = kept_enroll.enroll_from_kept(store, lock_set, embed)
    check, reason = kept_enroll.speaker_check(path, embed)
    assert reason is None
    assert check(voice(220, seed=999)) is True and check(voice(440, seed=998)) is False


def test_only_consented_verified_recordings_are_enrolled(tmp_path):
    store = kept.KeptStore(tmp_path / "kept", record=lambda name, data: None)
    store.keep(voice(220), trigger="wake_phrase", spoken_at=1.0, text="x")  # unverified: no voice lock
    lock_set = kept_enroll.lock_set_in(store)
    assert kept_enroll.import_consented(store, lock_set) == 0
