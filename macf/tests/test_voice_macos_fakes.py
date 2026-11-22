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


### privacy paths: the operator's microphone and recordings

def test_close_stops_and_closes_the_microphone_and_reading_after_it_ends(monkeypatch):
    events = []
    monkeypatch.setattr(capture_macos, "_open_stream",
                        lambda frames: types.SimpleNamespace(stop=lambda: events.append("stop"),
                                                             close=lambda: events.append("close")))
    monkeypatch.setattr(capture_macos, "_microphone_access", lambda: capture_macos.AUTHORIZED)
    mic = capture_macos.MacAudioIn()
    mic.open()
    mic.close()
    assert events == ["stop", "close"] and not mic.is_open
    with pytest.raises(AudioEnded, match="closed"):
        mic.read()


@pytest.mark.parametrize("session, expected", [
    ({"CGSSessionScreenIsLocked": True, "kCGSSessionOnConsoleKey": True}, "locked"),
    ({"kCGSSessionOnConsoleKey": True}, "unlocked"),
    ({"kCGSSessionOnConsoleKey": False}, "locked"),
    ({}, "unknown"),
    (None, "unknown"),
    ({"SomethingElse": 1}, "unknown"),   # the console key missing: never read as unlocked
])
def test_the_lock_state_is_unlocked_only_on_the_console_with_no_lock_key(session, expected):
    assert capture_macos.MacLockState(read=lambda: session).state() == expected


def test_a_lock_state_that_cannot_be_read_is_unknown_and_said_once(capsys):
    def broken():
        raise OSError("no session")
    lock = capture_macos.MacLockState(read=broken)
    assert lock.state() == "unknown" and lock.state() == "unknown"
    assert capsys.readouterr().err.count("can't be read") == 1


def test_stop_empties_pending_audio_and_releases_the_waiting_sentence(monkeypatch):
    output = speech_macos._Output()
    output.pending = np.ones(1000, np.float32)
    monkeypatch.setattr(speech_macos, "_OUTPUT", output)
    speech_macos.MacAudioOut().stop()
    assert output.pending.size == 0 and output.drained.is_set()


def test_the_authorization_numbers_are_avfoundations():
    assert (capture_macos.NOT_DETERMINED, capture_macos.RESTRICTED, capture_macos.DENIED,
            capture_macos.AUTHORIZED) == (0, 1, 2, 3)


@pytest.mark.parametrize("status, text", [("DENIED", "was denied"), ("RESTRICTED", "is restricted"),
                                          ("NOT_DETERMINED", "was not answered")])
def test_a_microphone_without_permission_is_refused_with_its_reason_and_never_opened(monkeypatch, status, text):
    opened = []
    monkeypatch.setattr(capture_macos, "_open_stream", lambda frames: opened.append(1))
    monkeypatch.setattr(capture_macos, "_microphone_access", lambda: getattr(capture_macos, status))
    with pytest.raises(AudioEnded, match=text):
        capture_macos.MacAudioIn().open()
    assert opened == []


def test_run_disclaimed_returns_the_childs_exit_code(monkeypatch):
    import signal
    import subprocess
    from macf.voice.capture import disclaim
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        monkeypatch.setattr(disclaim, "_spawn_disclaimed",
                            lambda argv, env: subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(3)"]).pid)
        assert disclaim.run_disclaimed(["unused"]) == 3
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)


def test_a_stop_that_arrives_while_the_child_starts_is_passed_on_once_it_exists(monkeypatch):
    """The stop must reach the child holding the microphone, not only this parent."""
    import os
    import signal
    import subprocess
    from macf.voice.capture import disclaim
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}

    def spawn_after_a_stop(argv, env):
        os.kill(os.getpid(), signal.SIGTERM)   # arrives before the child's pid is known: held
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]).pid
    try:
        monkeypatch.setattr(disclaim, "_spawn_disclaimed", spawn_after_a_stop)
        started = time.monotonic()
        assert disclaim.run_disclaimed(["unused"]) == 128 + signal.SIGTERM
        assert time.monotonic() - started < 10
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)
