"""The capture unit: the daemon's carriage of its utterances (MIS-0008 R10 to R12), and its own
logic on fakes (R13, R15, R16, R18, R27).

In the daemon tests the capture unit is a real declared unit: a short script the daemon starts,
which waits for the test's go, hands its daemon one utterance on the control socket, and writes
the receipt it got. So the accepted path runs in a process of the declared unit, and the refused
path in the test's own process, which is no such process.
"""
from __future__ import annotations

import builtins
import json
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from macf.agent_events_log import read_events
from macf.pd.interface import (EVENT_VOICE_UTTERANCE, Declaration, Unit, UtteranceRecord, VoiceSection,
                               control_socket, declaration_path, voice_socket)

from test_primal_daemon import CARD, ME, ask, base, make_core, make_home, run_daemon, script  # noqa: F401 - fixtures
from voice_fakes import SILENCE, SPEECH, WAKE, FakeAudio, ScriptedTranscriber, make_unit, secs

WORDS = "merge the voice branch when CI is green"

#: The capture unit's stand-in: wait for the go file, send the utterance it holds, keep the receipt, stay up.
CAPTURE_SCRIPT = r'''
import json, os, socket, sys, time
control, go, out = sys.argv[1], sys.argv[2], sys.argv[3]
while not os.path.exists(go):
    time.sleep(0.02)
with open(go) as f:
    request = f.read()
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
    conn.settimeout(5)
    conn.connect(control)
    conn.sendall(request.encode() + b"\n")
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
with open(out + ".tmp", "wb") as f:
    f.write(data)
os.replace(out + ".tmp", out)
time.sleep(120)
'''


@dataclass(frozen=True, kw_only=True)
class VoiceHome:
    """An agent home with a capture unit; ``go`` hands the unit its utterance, ``out`` gets the receipt."""

    home: Path
    go: Path
    out: Path


def utterance_request(**over) -> dict:
    request = {"op": "utterance", "trigger": "wake_phrase", "spoken_at": 1794600000.0, "screen": "unlocked",
               "voice_lock": "not_declared", "text": WORDS}
    request.update(over)
    return request


def voice_home(tmp_path, base, *, voice=True) -> VoiceHome:
    """An agent home declaring a capture unit, and a voice section naming it unless ``voice`` is False.
    The unit reads its request from the go file, so the words are in no declaration and no command
    line, and the whole log can be searched for them."""
    script = tmp_path / "capture.py"
    script.write_text(CAPTURE_SCRIPT)
    go, out = tmp_path / "go", tmp_path / "receipt.json"
    unit = Unit(name="capture", command=[sys.executable, str(script), str(control_socket(CARD, base)), str(go),
                                         str(out)],
                account=ME, restart="never", liveness_interval_s=60.0, memory_limit_mb=64, stop_grace_s=1.0)
    home = make_home(tmp_path, [unit])
    declaration_path(home).write_text(Declaration(
        version=1, agent=CARD, units=[unit],
        voice=VoiceSection(capture_unit="capture") if voice else None).model_dump_json())
    return VoiceHome(home=home, go=go, out=out)


def speak(go, **over):
    """Hand the capture unit its utterance: written whole, then renamed, so it never reads half."""
    tmp = go.with_suffix(".tmp")
    tmp.write_text(json.dumps(utterance_request(**over)))
    tmp.replace(go)


def wait_for(predicate, what, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    pytest.fail(f"timed out waiting for {what}")


def receipt_of(out) -> dict:
    return json.loads(wait_for(lambda: out.exists() and out.read_text(), "the capture unit's receipt"))


def utterance_events() -> list:
    return [e["data"] for e in read_events(reverse=False, scope="all", only=(EVENT_VOICE_UTTERANCE,))]


def closed_by_daemon(conn) -> bool:
    """Whether the daemon closed ``conn``: an end of file, or a reset when it closed with our
    hello unread. A timeout means it kept the channel."""
    try:
        return conn.recv(16) == b""
    except ConnectionResetError:
        return True


def connect_voice(daemon, hello: bytes) -> socket.socket:
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(5)
    conn.connect(str(daemon.voice.path))
    try:
        conn.sendall(hello)
    except (BrokenPipeError, ConnectionResetError):
        # The daemon refused at accept, before the hello was written: the refusal arrived early,
        # not a failure of the test. The caller's own assertion reads the closed connection.
        pass  # noqa: S110 - an early refusal is the outcome the caller checks next
    return conn


def attach_voice_channel(daemon) -> socket.socket:
    """Connect as the session's Voice Input Channel and say hello. The lineage check is the
    daemon's own, tested for the Notification Channel (MIS-0002-R122); here it is told this test
    process is the session's, so the rest of the path can be driven."""
    daemon.voice._outside_session = lambda peer: ""
    conn = connect_voice(daemon, b'{"hello":{"takes":["utterance"]}}\n')
    wait_for(lambda: any(a.ready for a in daemon.voice.channels.values()), "the voice channel's hello")
    return conn


# ---------------------------------------------------------------- the daemon's carriage

def test_undeclared_capture_unit_refused(tmp_path, base, run_daemon, isolated_events_log):
    """R12: an utterance from a process that isn't the declared capture unit is refused, with a
    receipt naming why, while the same request from the capture unit's own process is taken."""
    vh = voice_home(tmp_path, base)
    daemon = run_daemon(vh.home, base)
    refused = ask(daemon, utterance_request())
    assert (refused["ok"], refused["receipt"]) == (False, "refused")
    assert "not a process of the capture unit 'capture'" in refused["error"] and "R12" in refused["error"]
    speak(vh.go)
    taken = receipt_of(vh.out)
    assert taken["receipt"] == "refused" and "no Voice Input Channel is attached" in taken["error"], (
        "the capture unit's own utterance must pass the R12 check and fail only for want of a channel")
    assert [e["capture_unit"] for e in utterance_events()] == [None, "capture"]


def test_an_agent_without_a_voice_section_takes_no_utterance(tmp_path, base, run_daemon, isolated_events_log):
    """Voice is opt-in: with no voice section the daemon serves no voice socket, and an utterance,
    even from the unit, is refused with a receipt."""
    vh = voice_home(tmp_path, base, voice=False)
    daemon = run_daemon(vh.home, base)
    assert daemon.voice is None and not voice_socket(CARD, base).exists()
    speak(vh.go)
    receipt = receipt_of(vh.out)
    assert receipt["receipt"] == "refused" and "no voice section" in receipt["error"]
    assert [e["receipt"] for e in utterance_events()] == ["refused"]


def test_utterance_from_the_capture_unit_reaches_the_voice_channel(tmp_path, base, run_daemon,
                                                                   isolated_events_log):
    """R04, R05: the capture unit's utterance arrives on the voice socket as a closed record whose
    id and capture unit the daemon set, and the capture unit's receipt names the same id."""
    vh = voice_home(tmp_path, base)
    daemon = run_daemon(vh.home, base)
    conn = attach_voice_channel(daemon)
    speak(vh.go)
    data = b""
    while not data.endswith(b"\n"):
        data += conn.recv(65536)
    record = UtteranceRecord.model_validate_json(data)
    receipt = receipt_of(vh.out)
    assert receipt["ok"] and receipt["receipt"] == "delivered"
    assert record.utterance_id == receipt["utterance_id"]
    assert (record.capture_unit, record.text, record.trigger) == ("capture", WORDS, "wake_phrase")
    conn.close()


def test_a_voice_channel_outside_the_session_is_refused(tmp_path, base, run_daemon, isolated_events_log):
    """MIS-0002-R122 on the voice socket: with no session unit running, a channel that connects is
    closed without being attached."""
    daemon = run_daemon(voice_home(tmp_path, base).home, base)
    conn = connect_voice(daemon, b'{"hello":{"takes":["utterance"]}}\n')
    assert closed_by_daemon(conn), "the daemon kept a voice channel from outside the session"
    assert not daemon.voice.channels


def test_a_channel_that_does_not_take_utterances_is_dropped(tmp_path, base, run_daemon, isolated_events_log):
    """A Notification Channel's hello on the voice socket is not a voice channel's, so it is dropped."""
    daemon = run_daemon(voice_home(tmp_path, base).home, base)
    daemon.voice._outside_session = lambda peer: ""
    conn = connect_voice(daemon, b'{"hello":{"takes":["mail"]}}\n')
    assert closed_by_daemon(conn)
    wait_for(lambda: not daemon.voice.channels, "the channel to be dropped")


@pytest.mark.parametrize("voice, why", [
    ({"capture_unit": "nobody"}, "not a declared unit"),
    ({"capture_unit": "capture", "extra": 1}, "Extra inputs"),
])
def test_a_voice_section_must_name_a_declared_capture_unit(voice, why):
    """R12 at load: the capture unit is a unit this declaration runs, and the section is closed."""
    unit = {"name": "capture", "command": ["true"], "account": ME, "restart": "never",
            "liveness_interval_s": 60, "memory_limit_mb": 64}
    with pytest.raises(ValueError, match=why):
        Declaration.model_validate({"version": 1, "agent": CARD, "units": [unit], "voice": voice})


def test_a_voice_section_under_an_allowlist_that_leaves_voice_out_is_refused():
    """MIS-0002-R124: where an allowlist is declared, the voice channel must be on it, or it would
    never load; with it listed, the same declaration loads."""
    unit = {"name": "capture", "command": ["true"], "account": ME, "restart": "never",
            "liveness_interval_s": 60, "memory_limit_mb": 64}
    notification = {"plugin": "maceff-notification-channel", "marketplace": "maceff"}
    declared = {"version": 1, "agent": CARD, "units": [unit], "voice": {"capture_unit": "capture"},
                "allowlisted_channels": [notification]}
    with pytest.raises(ValueError, match="needs the Voice Input Channel admitted"):
        Declaration.model_validate(declared)
    declared["allowlisted_channels"].append({"plugin": "maceff-voice-input-channel", "marketplace": "maceff"})
    assert Declaration.model_validate(declared).voice.capture_unit == "capture"


def test_the_session_is_not_a_capture_unit():
    unit = {"name": "session", "kind": "session", "command": ["true"], "account": ME, "restart": "always",
            "liveness_interval_s": 60, "memory_limit_mb": 64}
    with pytest.raises(ValueError, match="the session unit"):
        Declaration.model_validate({"version": 1, "agent": CARD, "units": [unit],
                                    "voice": {"capture_unit": "session"}})


# ---------------------------------------------------------------- the capture logic

def wake_script() -> FakeAudio:
    """Quiet, the phrase, words run on, a pause: one wake and one utterance."""
    return FakeAudio().then((SILENCE, 5), (WAKE, 4), (SPEECH, secs(1.0)), (SPEECH, secs(1.0)),
                            (SILENCE, secs(2.0)))


def test_a_wake_a_hold_and_a_toggle_each_deliver_their_utterance():
    """Phase 4: the wake phrase, the hold key and continual voice each deliver what was said, with
    their own trigger; continual voice delivers one utterance per pause and stays open between."""
    woken = make_unit(wake_script(), ScriptedTranscriber("yo tom", "Yo Tom, check the queue."))
    woken.run(len(woken.audio.script) + 2)
    assert woken.texts() == [("wake_phrase", "check the queue")]

    held = make_unit(FakeAudio().then((SPEECH, 10)), ScriptedTranscriber("hold this"))
    held.keys.press("KEY_F9")
    held.run(10)
    held.keys.release("KEY_F9")
    held.run(3)
    assert held.texts() == [("hold_key", "hold this")]

    toggled = make_unit(FakeAudio().then((SPEECH, 10), (SILENCE, secs(1.5)), (SPEECH, 10), (SILENCE, secs(1.5))),
                        ScriptedTranscriber("first", "second"))
    toggled.keys.press("KEY_F10")
    toggled.run(len(toggled.audio.script))
    assert toggled.unit.state == "recording", "continual voice must stay open across a pause"
    toggled.keys.press("KEY_F10")
    toggled.run(2)
    assert toggled.texts() == [("continual_voice", "first"), ("continual_voice", "second")]
    assert toggled.unit.recording is None


def test_raw_audio_never_written(monkeypatch):
    """R13: through a wake and a hold, nothing is opened for writing and no temporary file is made:
    the audio goes to the transcriber as an array, in memory."""
    import tempfile
    real_open = builtins.open

    def no_writes(file, mode="r", *a, **k):
        if any(c in mode for c in "wax+"):
            raise AssertionError(f"the capture unit opened {file!r} for writing")
        return real_open(file, mode, *a, **k)

    def no_temp(*a, **k):
        raise AssertionError("the capture unit made a temporary file")

    monkeypatch.setattr(builtins, "open", no_writes)
    for name in ("NamedTemporaryFile", "TemporaryFile", "mkstemp", "SpooledTemporaryFile"):
        monkeypatch.setattr(tempfile, name, no_temp)
    transcriber = ScriptedTranscriber("yo tom", "yo tom check", "held")
    rig = make_unit(wake_script().then((SPEECH, 10)), transcriber)
    rig.run(len(rig.audio.script) - 10)
    rig.keys.press("KEY_F9")
    rig.run(10)
    rig.keys.release("KEY_F9")
    rig.run(2)
    assert len(rig.delivered) == 2
    assert all(isinstance(call[0], np.ndarray) for call in transcriber.calls)


def test_no_audio_read_while_listening_off():
    """R15: with listening off, the microphone stays closed and not one frame is read; a hold key
    opens it for that recording only, and it closes again after."""
    rig = make_unit(FakeAudio().then((WAKE, 20), (SPEECH, 10)), ScriptedTranscriber("only this"),
                    listening_on=lambda: False)
    rig.run(40)
    assert (rig.audio.reads, rig.audio.is_open, rig.unit.state) == (0, False, "off")
    rig.keys.press("KEY_F9")
    rig.run(30)
    rig.keys.release("KEY_F9")
    rig.run(1)
    read = rig.audio.reads
    # 30 frames while held; the release is polled first on the next tick, closing it before any read.
    assert read == 30 and not rig.audio.is_open and [u.trigger for u in rig.delivered] == ["hold_key"]
    rig.run(20)
    assert rig.audio.reads == read, "the microphone was read after the recording ended with listening off"


def test_live_microphone_is_status_entry():
    """R16: listening reports when it began; a recording reports when it began, its agent and its mode."""
    rig = make_unit(FakeAudio().then((SILENCE, 3), (SPEECH, 10)), ScriptedTranscriber("x"))
    rig.run(3)
    status = rig.unit.status()
    assert status["listening_since"] is not None and status["recording_since"] is None
    rig.keys.press("KEY_F9")
    rig.run(2)
    status = rig.unit.status()
    assert (status["recording_for"], status["mode"]) == ("Tester_abc123", "hold_key")
    assert status["recording_since"] is not None and status["listening_since"] is None


def test_no_trigger_over_socket():
    """R18: the capture code opens no socket, pipe or listener a trigger could arrive on; keys come
    only from the trigger devices it reads itself."""
    import macf.voice.capture as capture
    forbidden = ("socket.socket(", ".bind(", ".listen(", "mkfifo", "socketserver", "http.server",
                 "argparse", "sys.argv", "sys.stdin")
    for path in Path(capture.__file__).parent.rglob("*.py"):
        if path.name == "__main__.py":
            continue                   # the entry point reads its home from the command line, never a key
        text = path.read_text()
        found = [f for f in forbidden if f in text]
        assert not found, f"{path.name} uses {found}: a trigger could arrive that way"


def test_no_wake_during_own_speech():
    """R27: while the agent's own speech plays, the phrase wakes nothing and isn't even transcribed."""
    transcriber = ScriptedTranscriber("yo tom", "yo tom check")
    rig = make_unit(wake_script(), transcriber, speaking=lambda: True)
    rig.run(len(rig.audio.script))
    assert (transcriber.calls, rig.delivered, rig.unit.recording) == ([], [], None)


def test_the_daemon_shows_a_capture_units_microphone_in_status(tmp_path, script, make_core, isolated_events_log):
    """R16, the daemon's half: a capture unit's beat says what its microphone is doing, and status shows it."""
    from test_primal_daemon import drive
    from test_primal_daemon import make_unit as make_beating_unit
    recording = {"recording_since": 1794600000.0, "recording_for": "Tester_abc123", "mode": "hold_key"}
    core = make_core([make_beating_unit("capture", script, {"microphone": recording})])
    core.boot()
    assert drive(core, lambda: (core.statuses()[0].microphone or None) is not None), "no microphone in status"
    shown = core.statuses()[0].microphone
    assert (shown.recording_for, shown.mode, shown.recording_since) == ("Tester_abc123", "hold_key", 1794600000.0)


def test_the_heartbeat_carries_the_microphone_and_beats_early_when_it_changes():
    """R16, the unit's half: each beat carries the microphone, and a change, a recording opening,
    goes out within seconds rather than a whole interval later."""
    from macf.pd import liveness
    beats, mic = [], [{"listening_since": 1794600000.0}]
    hb = liveness.Heartbeat(CARD, "capture", 60.0, append=lambda kind, data: beats.append(data) or True,
                            microphone=lambda: mic[0])
    hb.start()
    hb.tick()
    wait_for(lambda: beats, "the first beat")
    mic[0] = {"recording_since": 1794600001.0, "recording_for": CARD, "mode": "hold_key"}
    hb.tick()
    wait_for(lambda: len(beats) > 1, "an early beat for the change", timeout=liveness.CHANGE_CHECK_S + 3)
    hb.stop()
    assert beats[0]["microphone"] == {"listening_since": 1794600000.0}
    assert beats[1]["microphone"]["mode"] == "hold_key"


# ---------------------------------------------------------------- R56: the end window and the stop words

from macf.voice.capture.unit import last_stop_word, strip_stop_word  # noqa: E402


class ByPrompt:
    """Answers the wake check and the final transcription (both prompted with the phrase) in order,
    and a stop-word check (no prompt) with ``tail``."""

    def __init__(self, *prompted, tail=""):
        self.prompted, self.tail = list(prompted), tail

    def __call__(self, audio, prompt):
        if prompt:
            return self.prompted.pop(0) if self.prompted else ""
        return self.tail


def test_the_end_window_holds_through_a_pause_then_drains_and_speech_refills_it():
    """R56: a 3 s pause no longer ends the utterance; the window stays full for the hold, drains after
    it, fills again when speech returns, and empties as the utterance ends."""
    audio = FakeAudio().then((SILENCE, 3), (WAKE, secs(0.5)), (SPEECH, secs(1)), (SILENCE, secs(3)),
                             (SPEECH, secs(1)), (SILENCE, secs(6)))
    rig = make_unit(audio, ByPrompt("yo tom", "yo tom one thought then another"), end_hold_s=2.0,
                    end_silence_s=5.0)
    rig.run(len(rig.audio.script))
    assert [u.text for u in rig.delivered] == ["one thought then another"], "the pause ended the utterance"
    w = rig.indicator.windows
    drained = next(i for i, v in enumerate(w) if v < 1.0)
    assert 1.0 in w[drained:], "speech didn't fill the window again"
    assert w[-1] == 0.0 and all(0.0 <= v <= 1.0 for v in w)


def test_send_said_last_ends_the_utterance_at_once_without_the_word():
    """R56: "send" as the last word ends the utterance at the next short pause, not at the window's end,
    and isn't in the words delivered."""
    audio = FakeAudio().then((SILENCE, 3), (WAKE, secs(0.5)), (SPEECH, secs(1)), (SILENCE, secs(6)))
    rig = make_unit(audio, ByPrompt("yo tom", "yo tom deploy it, send.", tail="deploy it, send."),
                    end_hold_s=2.0, end_silence_s=5.0, stop_words=True)
    rig.run(3 + secs(0.5) + secs(1) + secs(1.2))
    assert rig.unit.recording is None, "send didn't end the utterance before the window ran out"
    assert [u.text for u in rig.delivered] == ["deploy it"]


def test_abort_said_last_discards_the_utterance():
    audio = FakeAudio().then((SILENCE, 3), (WAKE, secs(0.5)), (SPEECH, secs(1)), (SILENCE, secs(6)))
    rig = make_unit(audio, ByPrompt("yo tom", "yo tom scrap that abort", tail="scrap that abort"),
                    end_hold_s=2.0, end_silence_s=5.0, stop_words=True)
    rig.run(3 + secs(0.5) + secs(1) + secs(1.2))
    assert rig.unit.recording is None and rig.delivered == []


def test_abort_at_the_end_of_a_held_key_recording_discards_it():
    """R56 on every trigger: a held key's transcript ending in "abort" is discarded too."""
    audio = FakeAudio().then((SPEECH, secs(2)), (SILENCE, secs(1)))
    rig = make_unit(audio, ScriptedTranscriber("never mind, abort"))
    rig.keys.press("KEY_F9")
    rig.run(secs(2))
    rig.keys.release("KEY_F9")
    rig.run(secs(1))
    assert rig.delivered == []


def test_a_stop_word_counts_only_as_the_last_word():
    assert strip_stop_word("deploy it, send.") == ("deploy it", "send")
    assert strip_stop_word("Scrap that. Abort!") == ("Scrap that", "abort")
    assert last_stop_word("don't stop the server") is None
    assert last_stop_word("send the report to Ira") is None
    assert strip_stop_word("check the build") == ("check the build", None)


def test_the_end_window_defaults_are_the_operators():
    """R56 as ruled on 2026-11-13: full for 2 s of quiet, empty at 5 s, with the stop words on."""
    from macf.pd.interface import VoiceSection
    from macf.voice.capture.unit import CaptureConfig
    voice = VoiceSection(capture_unit="voice-capture")
    config = CaptureConfig(agent="Tester_abc123")
    assert (voice.end_hold_s, voice.end_silence_s) == (2.0, 5.0)
    assert (config.end_hold_s, config.end_silence_s, config.stop_words) == (2.0, 5.0, True)
