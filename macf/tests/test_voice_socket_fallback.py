"""An utterance with no voice channel attached reaches the session's own socket, labelled as dictation."""
import json
import socket
import threading
import types

from macf.pd import voice_carriage
from macf.pd.interface import UtteranceRecord


def _record(screen="unlocked"):
    return UtteranceRecord(utterance_id="utt-1", trigger="wake_phrase", spoken_at=1795450000.0, screen=screen,
                           voice_lock="not_declared", capture_unit="capture", text="start the still minute")


def _carriage_for(monkeypatch, sock_path, pid=4242):
    carriage = voice_carriage.VoiceCarriage.__new__(voice_carriage.VoiceCarriage)
    carriage.channels, carriage.socket_fallback = {}, True
    carriage._session_client_pid = lambda: pid
    monkeypatch.setattr(voice_carriage, "find_credential_path", lambda p: "cred")
    monkeypatch.setattr(voice_carriage, "read_credential",
                        lambda path: types.SimpleNamespace(token="tok", declared_start="t0"))
    monkeypatch.setattr(voice_carriage, "verify_incarnation", lambda p, start: True)
    monkeypatch.setattr(voice_carriage, "find_socket", lambda p: sock_path)
    return carriage


def _serve_once(path):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    got = []

    def take():
        conn, _ = server.accept()
        got.append(conn.makefile().read())
        conn.close()
        server.close()
    thread = threading.Thread(target=take, daemon=True)
    thread.start()
    return got, thread


def test_with_no_channel_the_utterance_goes_to_the_session_socket_with_its_label(monkeypatch, tmp_path):
    path = tmp_path / "s.sock"
    got, thread = _serve_once(path)
    carriage = _carriage_for(monkeypatch, path)
    assert carriage._send(_record()) == 1
    thread.join(2)
    auth, message = [json.loads(line) for line in got[0].splitlines()]
    assert auth == {"type": "auth", "token": "tok"}
    text = message["message"]["content"]
    assert text.startswith("[Operator dictation") and "wake phrase" in text and "utt-1" in text
    assert text.endswith("start the still minute") and "Information only" not in text


def test_a_locked_screen_marks_the_dictation_information_only():
    assert "Information only" in voice_carriage.dictation_text(_record(screen="locked"))


def test_the_fallback_switched_off_or_no_session_delivers_nothing(monkeypatch, tmp_path):
    carriage = _carriage_for(monkeypatch, tmp_path / "none.sock")
    carriage.socket_fallback = False
    assert carriage._send(_record()) == 0
    carriage.socket_fallback = True
    carriage._session_client_pid = lambda: None
    assert carriage._send(_record()) == 0
