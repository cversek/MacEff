"""The recording indicator, as the capture logic drives it (MIS-0008 R21, R22)."""
from voice_fakes import SILENCE, SPEECH, WAKE, FakeAudio, ScriptedTranscriber, make_unit, secs


def shown_modes(rig) -> list:
    return [call[2] for call in rig.indicator.calls if call[0] == "show"]


def test_indicator_shown_while_microphone_open():
    """R21: shown with the agent's name from a recording's start, fed every recorded frame for the
    waveform and volume trace, hidden when it ends; never shown while merely listening."""
    rig = make_unit(FakeAudio().then((SILENCE, 10), (SPEECH, 6)), ScriptedTranscriber("held"))
    rig.run(10)
    assert rig.indicator.calls == [], "the indicator showed while the unit was only listening"
    rig.keys.press("KEY_F9")
    rig.run(6)
    assert rig.indicator.calls[0] == ("show", "Tester_abc123", "hold_key")
    assert rig.indicator.calls[1:] == [("feed",)] * 6
    rig.keys.release("KEY_F9")
    rig.run(1)
    assert rig.indicator.calls[-1] == ("hide",) and rig.indicator.shown is None


def test_indicator_shows_mode():
    """R22: the indicator names the mode that started the recording."""
    woken = make_unit(FakeAudio().then((WAKE, 4), (SPEECH, secs(1)), (SILENCE, secs(2))),
                      ScriptedTranscriber("yo tom", "yo tom hi"))
    woken.run(len(woken.audio.script))
    toggled = make_unit(FakeAudio().then((SPEECH, 5)), ScriptedTranscriber("x"))
    toggled.keys.press("KEY_F10")
    toggled.run(2)
    toggled.keys.press("KEY_F9")      # a hold pressed during continual voice doesn't change the mode
    toggled.run(2)
    assert shown_modes(woken) + shown_modes(toggled) == ["wake_phrase", "continual_voice"]
