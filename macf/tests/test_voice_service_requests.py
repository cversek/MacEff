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
