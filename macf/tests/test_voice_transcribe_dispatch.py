"""#1013: every engine detect_engine can return is one transcribe() dispatches.

detect_engine() returned "faster-whisper" on Linux while transcribe() had no branch for it, so every Linux run
ended in "Unknown engine". These tests read the names detect_engine can return from its own source, so a new
engine added there without a dispatch branch fails here.
"""
import inspect
import re

import pytest

from macf.voice import transcribe as t


def _detectable():
    return set(re.findall(r'return "([^"]+)"', inspect.getsource(t.detect_engine)))


def test_detect_engine_names_are_the_three_known():
    assert _detectable() == {"mlx", "faster-whisper", "whisper"}


@pytest.mark.parametrize("engine,fn", [("mlx", "transcribe_mlx"), ("faster-whisper", "transcribe_faster_whisper"),
                                       ("whisper", "transcribe_whisper")])
def test_each_detectable_engine_is_dispatched(tmp_path, monkeypatch, engine, fn):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    called = []
    monkeypatch.setattr(t, fn, lambda path, **kw: called.append((path, kw)) or "result")
    assert t.transcribe(str(wav), engine=engine) == "result"
    assert called and called[0][0] == str(wav)


def test_every_detectable_name_has_a_dispatch(tmp_path, monkeypatch):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    for name in ("transcribe_mlx", "transcribe_faster_whisper", "transcribe_whisper"):
        monkeypatch.setattr(t, name, lambda path, **kw: "ok")
    for engine in _detectable():
        assert t.transcribe(str(wav), engine=engine) == "ok", engine


def test_detected_faster_whisper_is_used_when_no_engine_is_named(tmp_path, monkeypatch):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(t, "detect_engine", lambda: "faster-whisper")
    monkeypatch.setattr(t, "transcribe_faster_whisper", lambda path, **kw: "fw")
    assert t.transcribe(str(wav)) == "fw"
