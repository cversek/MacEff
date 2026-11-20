"""The voice service's port answers any local caller, so what a request may do is narrow
(cversek/MacEff#868): no request stops the service, and a refused file isn't echoed back."""
import signal

from macf.voice import service


def test_a_shutdown_request_is_refused():
    reply = service.handle_request({"action": "shutdown"})
    assert "error" in reply and "voice service stop" in reply["error"]


def test_a_request_that_names_a_path_is_refused_and_the_file_is_never_opened(tmp_path, monkeypatch):
    """The service read any file its account can for any local caller (#868). A request now carries the
    audio, read by the caller; one that names a path is refused whether or not the file exists."""
    opened = []
    monkeypatch.setattr("macf.voice.transcribe.transcribe", lambda **k: opened.append(k))
    secret = tmp_path / "someone-elses" / "memo.oga"
    secret.parent.mkdir()
    secret.write_bytes(b"private audio")
    for named in (secret, tmp_path / "missing.oga"):
        reply = service.handle_request({"action": "transcribe", "file": str(named)})
        assert "not a path" in reply["error"]
        assert str(named) not in str(reply) and "memo" not in str(reply)
    assert opened == []


def test_stop_signals_the_service_and_sends_no_request(monkeypatch, tmp_path):
    sent, killed = [], []
    monkeypatch.setattr(service, "get_pid_file_path", lambda: tmp_path / "voice.pid")
    (tmp_path / "voice.pid").write_text("4242")
    monkeypatch.setattr(service, "is_service_running", lambda: True)
    monkeypatch.setattr(service, "send_request", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(service.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    assert service.stop_service() == 0
    assert sent == [] and killed == [(4242, signal.SIGTERM)]


def _audio(data: bytes, suffix=".oga") -> dict:
    import base64
    return {"action": "transcribe", "audio": base64.b64encode(data).decode("ascii"), "suffix": suffix}


def test_audio_that_does_not_transcribe_gets_the_fixed_reply_and_the_detail_stays_in_the_log(capsys):
    """The #969 review: a failure used to return ffmpeg's error, which quotes the whole command line, path
    included. It gets one fixed reply, and the detail goes to the service's own stderr."""
    reply = service.handle_request(_audio(b"not audio"))
    assert reply == {"error": "the audio file can't be read"}
    assert "voice: transcription failed" in capsys.readouterr().err


def test_the_staged_audio_is_transcribed_from_a_private_directory_and_removed_after(monkeypatch):
    from pathlib import Path
    seen = {}

    def fake(audio_path, **kw):
        p = Path(audio_path)
        seen.update(path=p, bytes=p.read_bytes(), mode=p.parent.stat().st_mode & 0o777)
        raise RuntimeError("stop here")

    monkeypatch.setattr("macf.voice.transcribe.transcribe", fake)
    service.handle_request(_audio(b"the caller's own bytes", ".wav"))
    assert seen["bytes"] == b"the caller's own bytes" and seen["path"].suffix == ".wav"
    assert seen["mode"] == 0o700, "only the service's account reads the staging directory"
    assert not seen["path"].exists() and not seen["path"].parent.exists(), "removed whether or not it transcribed"


import pytest


@pytest.mark.parametrize("request_", [
    {"action": "transcribe"},                                              # no audio at all
    {"action": "transcribe", "audio": "AAAA", "suffix": ".sh"},            # not an audio suffix
    {"action": "transcribe", "audio": "not base64!!", "suffix": ".oga"},
    {"action": "transcribe", "audio": "", "suffix": ".oga"},               # empty
    {"action": "transcribe", "audio": 12345, "suffix": ".oga"},
])
def test_a_malformed_audio_request_is_refused_before_anything_is_staged(request_, monkeypatch):
    monkeypatch.setattr("macf.voice.transcribe.transcribe", lambda **k: pytest.fail("must not be reached"))
    assert "error" in service.handle_request(request_)


def test_audio_over_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(service, "MAX_AUDIO_BYTES", 8)
    reply = service.handle_request(_audio(b"123456789"))
    assert "over" in reply["error"]
