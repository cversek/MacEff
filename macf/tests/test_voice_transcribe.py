"""Transcription engines: the faster-whisper path, and transcription from memory (MIS-0008 R13)."""
import builtins
from types import SimpleNamespace

import numpy as np
import pytest

from macf.voice import transcribe as tr


@pytest.fixture
def fake_faster_whisper(monkeypatch):
    """faster-whisper's model, standing in: it records what it was handed and says one segment."""
    handed = []

    class Model:
        def transcribe(self, audio, language=None, initial_prompt=None):
            handed.append((audio, language, initial_prompt))
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
