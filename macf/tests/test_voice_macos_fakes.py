"""The macOS voice classes' failure paths, driven by fakes: no microphone, speaker or model needed.

The live contract tests cover these classes on a Mac with hardware and are skipped elsewhere; these run
everywhere, so a pulled device, a stalled speaker and an offline first start are held in CI.
"""
import sys
import threading
import time
import types

import numpy as np
import pytest

from macf.voice.capture import macos as capture_macos
from macf.voice.capture.backends import FRAME, AudioEnded
from macf.voice.speech import __main__ as speech_main
from macf.voice.speech import macos as speech_macos


def _mic_with(monkeypatch, frames_to_send):
    def fake_open(frames):
        for block, overflowed in frames_to_send:
            frames.put((block, overflowed))
        return types.SimpleNamespace(stop=lambda: None, close=lambda: None)
    monkeypatch.setattr(capture_macos, "_open_stream", fake_open)
    monkeypatch.setattr(capture_macos, "_microphone_access", lambda: capture_macos.AUTHORIZED)
    monkeypatch.setattr(capture_macos, "READ_TIMEOUT_S", 0.05)
    mic = capture_macos.MacAudioIn()
    mic.open()
    return mic


def test_frames_from_the_stream_come_back_in_order_and_overflows_are_counted(monkeypatch):
    first, second = np.full(FRAME, 1, np.int16), np.full(FRAME, 2, np.int16)
    mic = _mic_with(monkeypatch, [(first.tobytes(), False), (second.tobytes(), True)])
    assert (mic.read() == first).all()
    assert (mic.read() == second).all()
    assert mic.overflows == 1


def test_a_microphone_that_sends_nothing_ends_the_stream_within_the_timeout(monkeypatch):
    mic = _mic_with(monkeypatch, [])
    started = time.monotonic()
    with pytest.raises(AudioEnded, match="sent nothing"):
        mic.read()
    assert time.monotonic() - started < 1.0


def test_each_open_reinitializes_portaudio_before_opening_the_stream(monkeypatch):
    calls = []

    class FakeStream:
        def __init__(self, **kwargs):
            calls.append("RawInputStream")
        def start(self):
            calls.append("start")

    fake = types.SimpleNamespace(_terminate=lambda: calls.append("_terminate"),
                                 _initialize=lambda: calls.append("_initialize"), RawInputStream=FakeStream)
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    capture_macos._open_stream(None)
    assert calls == ["_terminate", "_initialize", "RawInputStream", "start"]


class _DeadStream:
    def __init__(self, active):
        self.active, self.closed = active, False
    def stop(self):
        pass
    def close(self):
        self.closed = True


@pytest.mark.parametrize("active", [False, True])
def test_a_speaker_that_stops_taking_audio_returns_within_the_bound_and_closes(monkeypatch, capsys, active):
    """Inactive at once, or active but never pulling: either way play() gives up past the sentence's
    length plus the margin, says so, and closes the stream so the next sentence reopens it."""
    stream = _DeadStream(active)
    output = speech_macos._Output()
    output.stream, output.rate = stream, 1000
    monkeypatch.setattr(output, "start", lambda: None)
    monkeypatch.setattr(speech_macos, "_OUTPUT", output)
    monkeypatch.setattr(speech_macos, "PLAY_MARGIN_S", 0.1)
    monkeypatch.setattr(speech_macos, "BLOCK_S", 0.02)
    monkeypatch.setattr(speech_macos, "prepared", lambda samples, rate, device_rate: np.zeros(100, np.float32))
    started = time.monotonic()
    worker = threading.Thread(target=speech_macos.MacAudioOut().play,
                              args=(types.SimpleNamespace(samples=np.zeros(100, np.float32), rate=1000),), daemon=True)
    worker.start()
    worker.join(2.0)
    assert not worker.is_alive()
    assert time.monotonic() - started < 1.0
    assert stream.closed and output.stream is None
    assert "stopped taking audio" in capsys.readouterr().err


def test_a_gpu_engine_that_fails_to_load_offline_falls_back_to_the_cpu_model(monkeypatch, capsys, tmp_path):
    def offline():
        raise OSError("couldn't reach the model hub")
    built = []
    monkeypatch.setattr(speech_macos, "MlxKokoroEngine", offline)
    from macf.voice.speech import backends
    monkeypatch.setattr(backends, "KokoroEngine", lambda model, voices: built.append((model, voices)) or "onnx")
    assert speech_main.choose_engine(tmp_path, darwin=True) == "onnx"
    assert built and built[0][0].name == "kokoro-v1.0.onnx"
    err = capsys.readouterr().err
    assert "OSError" in err and "couldn't reach the model hub" in err


def test_a_model_that_cannot_load_at_all_exits_with_its_reason(monkeypatch, capsys, tmp_path):
    def missing(home, darwin=sys.platform == "darwin"):
        raise FileNotFoundError("kokoro-v1.0.onnx")
    monkeypatch.setattr(speech_main, "choose_engine", missing)
    assert speech_main.main([str(tmp_path)]) == speech_main.EX_CONFIG
    err = capsys.readouterr().err
    assert "FileNotFoundError" in err and "kokoro-v1.0.onnx" in err
