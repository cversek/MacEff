"""``macf_tools voice listen`` and ``voice capture status`` (MIS-0008 R15, R16)."""
from types import SimpleNamespace

from macf.voice import cli as voice_cli
from macf.voice import state


def test_listen_off_and_on_flip_the_switch_the_capture_unit_reads(tmp_path, monkeypatch, capsys):
    """With no capture unit running, the switch still flips and the reply says no unit is there to agree."""
    monkeypatch.setattr(voice_cli, "_home", lambda: tmp_path)
    monkeypatch.setattr(voice_cli, "microphone", lambda home: voice_cli.Reading(None, "no capture unit is running"))
    assert voice_cli.cmd_voice_listen(SimpleNamespace(switch="off")) == 0
    assert not state.listening_on(tmp_path)
    assert "listening turned off; the capture unit: no capture unit is running" in capsys.readouterr().out
    assert voice_cli.cmd_voice_listen(SimpleNamespace(switch="on")) == 0
    assert state.listening_on(tmp_path)


def test_listen_says_when_the_capture_unit_does_not_agree(tmp_path, monkeypatch, capsys):
    """Say what happened, not what was meant: a unit still listening after "off" is reported, and fails."""
    monkeypatch.setattr(voice_cli, "_home", lambda: tmp_path)
    monkeypatch.setattr(voice_cli, "AGREE_WAIT_S", 0.6)
    monkeypatch.setattr(voice_cli, "microphone", lambda home: voice_cli.Reading({"listening_since": 1.0}))
    assert voice_cli.cmd_voice_listen(SimpleNamespace(switch="off")) == 1
    assert "didn't agree" in capsys.readouterr().out


def test_the_microphone_is_described_as_its_status_says():
    now = 1794600100.0
    assert voice_cli.describe(voice_cli.Reading(None, "the primal daemon can't be asked: gone"), now) == "the primal daemon can't be asked: gone"
    assert voice_cli.describe(voice_cli.Reading({}), now) == "microphone closed"
    assert voice_cli.describe(voice_cli.Reading({"listening_since": now - 40}), now) == "listening for the wake phrase, 40 s"
    assert voice_cli.describe(voice_cli.Reading({"recording_since": now - 3, "recording_for": "Tester_abc123",
                                                 "mode": "hold_key"}),
                              now) == "recording for Tester_abc123 (hold key), 3 s"


def test_speaking_counts_until_the_echo_has_passed(tmp_path):
    """R27's input: the agent is deaf while its speech plays and for a moment after."""
    path = state.speaking_path(tmp_path)
    assert not state.speaking(tmp_path)
    path.parent.mkdir(parents=True)
    path.touch()
    touched = path.stat().st_mtime
    assert state.speaking(tmp_path, now=touched + 1.0)
    assert not state.speaking(tmp_path, now=touched + state.DEAF_AFTER_SPEECH_S + 0.1)


def test_the_commands_are_on_the_cli():
    from macf.cli import _build_parser
    parser = _build_parser()
    assert parser.parse_args(["voice", "listen", "off"]).func is voice_cli.cmd_voice_listen
    assert parser.parse_args(["voice", "capture", "status"]).func is voice_cli.cmd_voice_capture_status


def test_a_reading_says_why_it_has_no_microphone(tmp_path):
    """A home with no voice section reads as exactly that, not as a capture unit that isn't running."""
    from test_primal_daemon import make_home
    reading = voice_cli.microphone(make_home(tmp_path, []))
    assert reading.mic is None and reading.why == "this agent declares no voice section"
