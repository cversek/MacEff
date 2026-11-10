"""The voice service's port answers any local caller, so what a request may do is narrow
(cversek/MacEff#868): no request stops the service, and a refused file isn't echoed back."""
import signal

from macf.voice import service


def test_a_shutdown_request_is_refused():
    reply = service.handle_request({"action": "shutdown"})
    assert "error" in reply and "voice service stop" in reply["error"]


def test_a_missing_file_is_refused_without_naming_it(tmp_path):
    secret = tmp_path / "someone-elses" / "memo.oga"
    reply = service.handle_request({"action": "transcribe", "file": str(secret)})
    assert reply == {"error": "the audio file can't be read"}
    assert str(secret) not in str(reply) and "memo" not in str(reply)


def test_stop_signals_the_service_and_sends_no_request(monkeypatch, tmp_path):
    sent, killed = [], []
    monkeypatch.setattr(service, "get_pid_file_path", lambda: tmp_path / "voice.pid")
    (tmp_path / "voice.pid").write_text("4242")
    monkeypatch.setattr(service, "is_service_running", lambda: True)
    monkeypatch.setattr(service, "send_request", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(service.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    assert service.stop_service() == 0
    assert sent == [] and killed == [(4242, signal.SIGTERM)]


def test_a_file_that_exists_but_isnt_audio_gets_the_same_reply(tmp_path, capsys):
    """The #969 review: a file that exists and fails to transcribe used to return ffmpeg's error,
    which quotes the whole command line, path included. It gets the same fixed reply as a missing
    one, and the detail goes to the service's own stderr."""
    notes = tmp_path / "private-notes.oga"
    notes.write_text("not audio")
    reply = service.handle_request({"action": "transcribe", "file": str(notes)})
    assert reply == {"error": "the audio file can't be read"}


def test_a_failed_correction_gets_a_fixed_reply(tmp_path, monkeypatch, capsys):
    """The #969 review, again: the correction step returned its exception's text. It works on the
    transcript, not the file, but the same fixed-reply rule closes it."""
    from types import SimpleNamespace
    from macf.voice import correction, transcribe
    audio = tmp_path / "private-notes.oga"
    audio.write_bytes(b"")
    monkeypatch.setattr(transcribe, "transcribe", lambda **kw: SimpleNamespace(
        text="hello", to_dict=lambda: {"text": "hello"}))

    def broken(text):
        raise OSError(f"cannot read {audio}")
    monkeypatch.setattr(correction, "correct_transcript", broken)
    reply = service.handle_request({"action": "transcribe", "file": str(audio), "conditioned": False})
    assert reply["correction_error"] == "the correction failed"
    assert str(audio) not in str(reply)
    assert str(audio) in capsys.readouterr().err
