"""Transcription engines: the faster-whisper path, and transcription from memory (MIS-0008 R13)."""
import builtins
from types import SimpleNamespace

import numpy as np
import pytest

from macf.voice import transcribe as tr


@pytest.fixture
def fake_faster_whisper(monkeypatch):
    """faster-whisper's model, standing in: it records what it was handed, and in ``.decoded`` the decoding
    options of each call, and says one segment."""

    class Handed(list):
        decoded: list

    handed = Handed()
    handed.decoded = []

    class Model:
        def transcribe(self, audio, language=None, initial_prompt=None, **options):
            handed.append((audio, language, initial_prompt))
            handed.decoded.append(options)
            seg = SimpleNamespace(text=" check the queue", start=0.0, end=1.2, no_speech_prob=0.1)
            return iter([seg]), SimpleNamespace(language="en")

    monkeypatch.setattr(tr, "_faster_whisper_model", lambda model: Model())
    return handed


def test_a_wav_file_on_linux_reaches_faster_whisper(tmp_path, fake_faster_whisper):
    """The dispatch had no faster-whisper branch, so every Linux transcription raised
    "Unknown engine" though detection offered that engine."""
    wav = tmp_path / "said.wav"
    wav.write_bytes(b"RIFF")
    result = tr.transcribe(str(wav), engine="faster-whisper")
    assert (result.text, result.engine) == ("check the queue", "faster-whisper")
    assert fake_faster_whisper[0][0] == str(wav)


def test_samples_in_memory_are_transcribed_without_a_file(monkeypatch, fake_faster_whisper):
    """R13: the capture unit hands samples over in memory; nothing is opened for writing on the way."""
    real_open = builtins.open

    def no_writes(file, mode="r", *a, **k):
        if any(c in mode for c in "wax+"):
            raise AssertionError(f"transcription opened {file!r} for writing")
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", no_writes)
    pcm = (np.sin(np.linspace(0, 200, 16000)) * 8000).astype(np.int16)
    result = tr.transcribe_array(pcm, engine="faster-whisper", initial_prompt="Yo Tom, ")
    audio, language, prompt = fake_faster_whisper[0]
    assert audio.dtype == np.float32 and np.abs(audio).max() <= 1.0, "int16 samples must arrive scaled to float32"
    assert (language, prompt, result.text) == ("en", "Yo Tom, ", "check the queue")


def test_an_engine_nobody_knows_is_refused_by_name():
    with pytest.raises(ValueError, match="Unknown engine: vinyl"):
        tr.transcribe_array(np.zeros(160, dtype=np.float32), engine="vinyl")


def test_decoding_is_bounded_and_a_short_check_is_capped(fake_faster_whisper):
    """A live trial: Whisper's default decoding wrote "yo tom" over and over to the token limit, 38 s on the CPU.
    Every call is greedy and unconditioned; a short check is capped to a few tokens."""
    tr.transcribe_array(np.zeros(16000, np.float32), engine="faster-whisper")
    tr.transcribe_array(np.zeros(16000, np.float32), engine="faster-whisper", max_tokens=24)
    full, check = fake_faster_whisper.decoded
    assert full == {"temperature": 0.0, "condition_on_previous_text": False, "vad_filter": True}
    assert check == {"temperature": 0.0, "condition_on_previous_text": False, "without_timestamps": True,
                     "max_new_tokens": 24}


def test_a_silent_last_stretch_transcribes_to_nothing(monkeypatch):
    """A live utterance ended in "So, let's get started." a dozen times: its last stretch was the quiet before
    the end window, and Whisper primed with a vocabulary writes speech into silence. This stand-in does the
    same unless silence is cut out first, as faster-whisper's filter does."""

    class Model:
        def transcribe(self, audio, language=None, initial_prompt=None, vad_filter=False, **options):
            if vad_filter and not np.abs(audio).max() > 0.01:
                return iter([]), SimpleNamespace(language="en")
            seg = SimpleNamespace(text=" So, let's get started.", start=0.0, end=5.0, no_speech_prob=0.6)
            return iter([seg] * 12), SimpleNamespace(language="en")

    monkeypatch.setattr(tr, "_faster_whisper_model", lambda model: Model())
    quiet = (np.random.default_rng(1).standard_normal(5 * 16000) * 0.002).astype(np.float32)
    assert tr.transcribe_array(quiet, engine="faster-whisper", initial_prompt="MacEff, Harbor Master").text == ""


def test_release_drops_every_loaded_model(monkeypatch):
    """R58: what a release gives back is the cache's hold on each model; the next transcription loads it again."""
    monkeypatch.setattr(tr, "_LOADED", {("faster-whisper", "small.en"): object(), ("faster-whisper", "x"): object()})
    assert tr.release_models() == 2 and tr._LOADED == {}
    assert tr.release_models() == 0
