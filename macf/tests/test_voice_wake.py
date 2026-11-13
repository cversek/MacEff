"""A wake and its checks (MIS-0008 6.5)."""
from voice_fakes import QUIET_WAKE, SILENCE, SPEECH, WAKE, FakeAudio, ScriptedTranscriber, make_unit, secs


def test_wake_passes_its_checks_in_order():
    """R23: the wake model fires, then the window must hold speech, then its transcription must hold
    the phrase. A later check never runs when an earlier one failed. (The voice lock goes between
    speech and transcription when Phase 7 builds it.)"""
    # The model never fires on speech alone: nothing is transcribed.
    transcriber = ScriptedTranscriber("yo tom")
    rig = make_unit(FakeAudio().then((SPEECH, secs(3))), transcriber)
    rig.run(len(rig.audio.script))
    assert transcriber.calls == [] and rig.unit.recording is None

    # It fires on a window with no speech in it: still nothing transcribed.
    transcriber = ScriptedTranscriber("yo tom")
    rig = make_unit(FakeAudio().then((QUIET_WAKE, 4), (SILENCE, secs(2))), transcriber)
    rig.run(len(rig.audio.script))
    assert transcriber.calls == [] and rig.unit.recording is None

    # It fires, with speech, but the transcription doesn't hold the phrase: transcribed once, no recording.
    transcriber = ScriptedTranscriber("you told me")
    rig = make_unit(FakeAudio().then((WAKE, 4), (SPEECH, secs(1)), (SILENCE, secs(1))), transcriber)
    rig.run(len(rig.audio.script))
    assert len(transcriber.calls) == 1 and transcriber.calls[0][1] == "yo tom" and rig.unit.recording is None

    # All three pass: the recording opens.
    rig = make_unit(FakeAudio().then((WAKE, 4), (SPEECH, secs(1))), ScriptedTranscriber("Yo, Tom!"))
    rig.run(len(rig.audio.script))
    assert rig.unit.recording is not None and rig.unit.recording.mode == "wake_phrase"


def test_a_rejected_fire_leaves_the_next_real_call_heard():
    """A false fire costs only a short pause: the real call right after it still wakes."""
    transcriber = ScriptedTranscriber("you told me", "yo tom")
    rig = make_unit(FakeAudio().then((WAKE, 4), (SPEECH, secs(1)), (SILENCE, secs(1)), (WAKE, 4),
                                     (SPEECH, secs(1))), transcriber)
    rig.run(len(rig.audio.script))
    assert len(transcriber.calls) == 2 and rig.unit.recording is not None


def test_words_in_the_same_breath_as_the_phrase_are_delivered():
    """"Yo Tom, check the queue" in one breath: every word is in the wake window, and the silence
    after must end that utterance, not cancel it as one that heard nothing."""
    # The fire is judged 0.8 s after the first phrase frame, at frame 11: the speech ends there,
    # so the recording itself hears none of it.
    rig = make_unit(FakeAudio().then((WAKE, 4), (SPEECH, 6), (SILENCE, secs(6))),
                    ScriptedTranscriber("yo tom check the queue", "yo tom check the queue"))
    rig.run(len(rig.audio.script))
    assert [u.text for u in rig.delivered] == ["check the queue"]


# ---------------------------------------------------------------- training and measuring (R24, R25)

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from macf.voice.capture.backends import RATE  # noqa: E402
from macf.voice.wake.dataset import PhraseRefused, WakeSet, check_phrase  # noqa: E402
from macf.voice.wake.model import WakeModel  # noqa: E402
from macf.voice.wake.train import NotEnoughClips, train  # noqa: E402


def tone(freqs, seconds=0.25, level=0.4, rng=None):
    """Tones one after another, with a little noise: a stand-in for a spoken sound."""
    rng = rng or np.random.default_rng(0)
    parts = [np.sin(2 * np.pi * f * np.arange(int(seconds * RATE)) / RATE) * level for f in freqs]
    x = np.concatenate(parts + [np.zeros(int(0.3 * RATE))])
    return (x + rng.normal(0, 0.003, x.size)).astype(np.float32)


def band_embed(windows):
    """A stand-in for openWakeWord's features: band energies over 16 time slices of each window."""
    out = []
    for w in windows:
        rows = []
        for piece in np.array_split(np.asarray(w, np.float64), 16):
            spectrum = np.abs(np.fft.rfft(piece))
            rows += [float(np.log1p(band.sum())) for band in np.array_split(spectrum, 8)]
        out.append(rows)
    return np.array(out)


def recorded_set(home, rng, phrases=20) -> WakeSet:
    wake = WakeSet(home, "yo harbor")
    for _ in range(phrases):
        wake.add("phrase", tone([300 + rng.integers(-20, 20), 900 + rng.integers(-30, 30)], rng=rng), "desk mic")
    for _ in range(8):
        wake.add("near_miss", tone([300 + rng.integers(-20, 20)], seconds=0.5, rng=rng), "desk mic")
        wake.add("other_phrase", tone([1500, 2200], rng=rng), "desk mic")
    for _ in range(4):
        wake.add("speech", tone(list(rng.integers(200, 2500, size=24)), seconds=0.15, level=0.3, rng=rng),
                 "reading aloud")
        wake.add("room", rng.normal(0, 0.004, 6 * RATE).astype(np.float32), "fans on")
    return wake


def test_model_stored_with_report(tmp_path):
    """R24: the model file carries its test report: misses, false alarms per hour, false wakes on
    other agents' phrases, and the conditions it was measured under."""
    rng = np.random.default_rng(11)
    wake = recorded_set(tmp_path, rng)
    model = train(wake, band_embed)
    model.save(wake.model_path)
    report = WakeModel.load(wake.model_path).report
    for key in ("misses", "false_alarms_per_hour", "other_phrase_fires", "near_miss_fires", "conditions"):
        assert key in report, f"the stored report has no {key}"
    assert report["held_out"]["phrase"] == 5 and report["conditions"] == ["desk mic", "fans on", "reading aloud"]
    # The counts agree with the scores they were made from: what was measured, not what was hoped.
    threshold = WakeModel.load(wake.model_path).threshold
    assert report["misses"] == sum(s < threshold for s in report["phrase_scores"])
    assert len(report["phrase_scores"]) == report["held_out"]["phrase"]
    assert report["background_seconds"] > 0 and report["false_alarms_per_hour"] is not None


def test_test_set_disjoint_from_training(tmp_path):
    """R25: no clip the model trained on is among the clips that measured it, and a clip's set,
    fixed when it was recorded, never moves as more are recorded."""
    rng = np.random.default_rng(5)
    wake = recorded_set(tmp_path, rng)
    held_out = {c.clip_id for c in wake.clips(split="test")}
    model = train(wake, band_embed)
    assert held_out and not held_out & set(model.report["trained_on"])
    before = {c.clip_id: c.split for c in wake.clips()}
    for _ in range(9):
        wake.add("phrase", tone([300, 900], rng=rng))
    after = {c.clip_id: c.split for c in wake.clips()}
    assert all(after[k] == v for k, v in before.items()), "recording more clips moved an earlier clip's set"


def test_too_few_clips_are_refused_with_what_is_missing(tmp_path):
    wake = recorded_set(tmp_path, np.random.default_rng(1), phrases=6)
    with pytest.raises(NotEnoughClips, match="record at least 15 of the phrase"):
        train(wake, band_embed)


@pytest.mark.parametrize("phrase, why", [("Tom", "one word"), ("yo yo", "too short"), ("thank you", "too often")])
def test_a_phrase_that_cannot_work_is_refused(phrase, why):
    with pytest.raises(PhraseRefused, match=why):
        check_phrase(phrase)
    assert check_phrase("Yo, Tom!") == "yo tom"
