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
