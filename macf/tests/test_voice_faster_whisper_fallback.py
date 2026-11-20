"""#1024: faster-whisper falls back to the CPU when CUDA fails at its first inference.

The model builds on a machine with a driver but a missing or mismatched cuDNN, and the failure comes
only when the first inference loads the library. The segments are read lazily, so the failure arrives
while they are consumed, after transcribe() has returned.
"""
import sys
import types

import pytest

from macf.voice import transcribe as t


class _Seg:
    def __init__(self, text, start, end):
        self.text, self.start, self.end, self.no_speech_prob = text, start, end, 0.0


def _install(monkeypatch, behaviour):
    """A fake faster_whisper whose model, built for a device, acts as behaviour[device] says:
    'ok', 'fail_build' (raises when built) or 'fail_read' (raises while the segments are read)."""
    built = []

    class WhisperModel:
        def __init__(self, model, device, compute_type):
            built.append((device, compute_type))
            if behaviour[device] == "fail_build":
                raise RuntimeError("CUDA driver version is insufficient")
            self.device = device

        def transcribe(self, path, **kw):
            def segments():
                if behaviour[self.device] == "fail_read":
                    raise RuntimeError("Library libcudnn_ops.so.9 is not found or cannot be loaded")
                yield _Seg(f" heard on {self.device} ", 0.0, 1.5)
            return segments(), types.SimpleNamespace(language="en")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WhisperModel))
    monkeypatch.setattr(t, "_faster_whisper_cpu_only", False)
    return built


def test_a_failure_at_the_first_inference_retries_on_the_cpu(monkeypatch, capsys):
    built = _install(monkeypatch, {"cuda": "fail_read", "cpu": "ok"})
    result = t.transcribe_faster_whisper("x.wav")
    assert result.text == "heard on cpu"
    assert built == [("cuda", "float16"), ("cpu", "int8")]
    assert "can't use the GPU" in capsys.readouterr().err


def test_a_failure_building_the_model_still_falls_back(monkeypatch):
    built = _install(monkeypatch, {"cuda": "fail_build", "cpu": "ok"})
    assert t.transcribe_faster_whisper("x.wav").text == "heard on cpu"
    assert built == [("cuda", "float16"), ("cpu", "int8")]


def test_later_calls_go_straight_to_the_cpu_and_say_nothing(monkeypatch, capsys):
    built = _install(monkeypatch, {"cuda": "fail_read", "cpu": "ok"})
    t.transcribe_faster_whisper("x.wav")
    capsys.readouterr()
    assert t.transcribe_faster_whisper("y.wav").text == "heard on cpu"
    assert built[2:] == [("cpu", "int8")]
    assert capsys.readouterr().err == ""


def test_a_working_gpu_is_used_and_never_falls_back(monkeypatch, capsys):
    built = _install(monkeypatch, {"cuda": "ok", "cpu": "fail_read"})
    assert t.transcribe_faster_whisper("x.wav").text == "heard on cuda"
    assert built == [("cuda", "float16")]
    assert capsys.readouterr().err == ""


def test_a_failure_on_both_devices_raises_and_keeps_the_gpu_on(monkeypatch):
    _install(monkeypatch, {"cuda": "fail_read", "cpu": "fail_read"})
    with pytest.raises(RuntimeError):
        t.transcribe_faster_whisper("x.wav")
    assert t._faster_whisper_cpu_only is False
