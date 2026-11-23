"""The Mac engine drops what Whisper invents at an utterance's edges."""
from macf.voice.transcribe import segment_is_speech


def test_real_speech_is_kept():
    assert segment_is_speech({"text": "Paradigm finished, can you check?", "no_speech_prob": 0.05, "avg_logprob": -0.2})


def test_confident_silence_is_dropped_but_a_quiet_real_word_is_not():
    assert not segment_is_speech({"text": "Thank you.", "no_speech_prob": 0.8, "avg_logprob": -1.1})
    assert segment_is_speech({"text": "Okay.", "no_speech_prob": 0.8, "avg_logprob": -0.3})


def test_text_mostly_outside_latin_script_is_dropped():
    assert not segment_is_speech({"text": "защиты reven заб", "no_speech_prob": 0.1, "avg_logprob": -0.5})
    assert not segment_is_speech({"text": "結束 謝謝", "no_speech_prob": 0.1, "avg_logprob": -0.5})
    assert segment_is_speech({"text": "arkadaşlar café naïve", "no_speech_prob": 0.1, "avg_logprob": -0.5})


def test_a_loop_is_kept_once_and_real_words_around_it_stay():
    from macf.voice.transcribe import cut_repeats
    looped = "It did pop up later. " + "Bumble, " * 80 + "B Bumble, Bumble"
    out = cut_repeats(looped)
    assert out.startswith("It did pop up later.") and out.lower().count("bumble") <= 3
    assert cut_repeats("thank you thank you thank you thank you") == "thank you"
    assert cut_repeats("no no no") == "no no no"  #three is speech, not a loop


def test_a_segment_that_is_only_a_loop_is_dropped():
    assert not segment_is_speech({"text": "Bumble, " * 40, "compression_ratio": 9.0, "no_speech_prob": 0.1,
                                  "avg_logprob": -0.3})
    assert segment_is_speech({"text": "We should check the impedance again before the next run, please.",
                              "compression_ratio": 1.3, "no_speech_prob": 0.1, "avg_logprob": -0.3})
