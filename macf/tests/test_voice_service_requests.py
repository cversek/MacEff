"""The voice service's port answers any local caller, so what a request may do is narrow
(cversek/MacEff#868): no request stops the service, and a refused file isn't echoed back."""
import signal

import pytest

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


def test_a_failed_correction_gets_a_fixed_reply(monkeypatch, capsys, tmp_path):
    """The #969 review: the correction step returned its exception's text. It works on the transcript,
    not the audio, but the same fixed-reply rule closes it, and the detail stays in the log."""
    from types import SimpleNamespace

    from macf.voice import correction, transcribe
    secret = tmp_path / "private-notes.oga"
    monkeypatch.setattr(transcribe, "transcribe", lambda **kw: SimpleNamespace(
        text="hello", to_dict=lambda: {"text": "hello"}))

    def broken(text):
        raise OSError(f"cannot read {secret}")
    monkeypatch.setattr(correction, "correct_transcript", broken)
    reply = service.handle_request({**_audio(b"x"), "conditioned": False})
    assert reply["correction_error"] == "the correction failed"
    assert str(secret) not in str(reply)
    assert str(secret) in capsys.readouterr().err


class _Endless:
    """A connection whose caller sends without end and never sends a newline."""

    def __init__(self):
        self.received = 0

    def recv(self, n):
        self.received += n
        assert self.received < 1_000_000, "the reader never stopped"      # a missing bound fails, not hangs
        return b"A" * n


def test_a_request_line_is_read_only_up_to_its_bound(monkeypatch):
    monkeypatch.setattr(service, "MAX_REQUEST_BYTES", 10_000)
    conn = _Endless()
    with pytest.raises(service.RequestTooLarge):
        service.read_request_line(conn)
    assert conn.received <= 10_000 + 4096        # it stopped reading at the bound, not at the end of the stream


def test_a_request_at_the_bound_is_still_read(monkeypatch):
    monkeypatch.setattr(service, "MAX_REQUEST_BYTES", 10_000)

    class Whole:
        sent = False

        def recv(self, n):
            if self.sent:
                return b""
            self.sent = True
            return b"x" * 9_000 + b"\n"
    assert service.read_request_line(Whole()).endswith(b"\n")


def test_the_bound_leaves_room_for_the_largest_audio_in_base64():
    import base64
    largest = base64.b64encode(b"\0" * service.MAX_AUDIO_BYTES)
    assert len(largest) < service.MAX_REQUEST_BYTES


class _Stream:
    """A connection that delivers *total* bytes in 4 KB chunks, then a newline."""

    def __init__(self, total):
        self.left = total

    def recv(self, n):
        if self.left <= 0:
            return b"\n"
        self.left -= n
        return b"A" * n


def test_a_long_request_line_is_read_in_linear_time():
    """Ira's review of #1082: joining bytes on every chunk copies the buffer each time, so 80 MB took
    109 s to read and a caller sending slowly could hold the service for minutes. In place it is
    milliseconds; the budget here is wide, and the quadratic version is far past it."""
    import time
    start = time.monotonic()
    assert len(service.read_request_line(_Stream(40 * 1024 * 1024))) > 40 * 1024 * 1024
    assert time.monotonic() - start < 5


def test_the_clients_reply_is_read_with_the_same_bound(monkeypatch):
    monkeypatch.setattr(service, "MAX_REQUEST_BYTES", 10_000)

    class Sock:
        def settimeout(self, t): pass
        def connect(self, a): pass
        def sendall(self, b): pass
        def close(self): pass
        def recv(self, n): return b"A" * n
    monkeypatch.setattr(service.socket, "socket", lambda *a, **k: Sock())
    with pytest.raises(service.RequestTooLarge):
        service.send_request({"action": "transcribe"})


def _transcribe_args(path):
    from argparse import Namespace
    return Namespace(file=str(path), initial_prompt=None, conditioned=False, language=None, engine=None,
                     model=None, correct=False, json_output=False)


class _Sock:
    """A stand-in socket that answers with *reply*, forever when *endless*."""

    def __init__(self, reply=b"", endless=False):
        self.reply, self.endless = reply, endless

    def settimeout(self, t): pass
    def connect(self, a): pass
    def sendall(self, b): pass
    def close(self): pass

    def recv(self, n):
        if self.endless:
            return b"A" * n
        out, self.reply = self.reply[:n], self.reply[n:]
        return out


@pytest.mark.parametrize("sock", [_Sock(endless=True), _Sock(reply=b"this is not json\n"), _Sock(reply=b"\xff\xfe\n")],
                         ids=["endless reply", "reply that is not JSON", "reply that is not UTF-8"])
def test_a_service_that_answers_wrongly_sends_the_command_to_direct_transcription(sock, monkeypatch, tmp_path, capsys):
    """Ira's review of the bounded client read: the command falls back only on OSError, so a reply that
    broke the protocol crashed it instead of falling back."""
    from types import SimpleNamespace

    from macf import cli
    audio = tmp_path / "clip.oga"
    audio.write_bytes(b"x")
    monkeypatch.setattr(service, "MAX_REQUEST_BYTES", 10_000)
    monkeypatch.setattr(service, "is_service_running", lambda: True)
    monkeypatch.setattr(service.socket, "socket", lambda *a, **k: sock)
    direct = []
    monkeypatch.setattr("macf.voice.transcribe.transcribe", lambda **kw: direct.append(kw) or SimpleNamespace(
        text="heard directly", engine="e", model="m", duration_audio=1.0, duration_transcribe=1.0,
        to_dict=lambda: {}))
    assert cli.cmd_voice_transcribe(_transcribe_args(audio)) == 0
    assert len(direct) == 1, "the command did not fall back to direct transcription"
    captured = capsys.readouterr()
    assert "falling back to direct transcription" in captured.err and "heard directly" in captured.out


def test_the_status_call_reports_a_service_that_answers_wrongly_instead_of_raising(monkeypatch):
    """The other caller of send_request: a squatted port's endless reply reads as not responding."""
    monkeypatch.setattr(service, "MAX_REQUEST_BYTES", 10_000)
    monkeypatch.setattr(service, "is_service_running", lambda: True)
    monkeypatch.setattr(service.socket, "socket", lambda *a, **k: _Sock(endless=True))
    assert service.get_service_status() == {"running": False, "error": "PID exists but service not responding"}
