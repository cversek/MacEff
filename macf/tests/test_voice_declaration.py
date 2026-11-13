"""An agent's voice section in its declaration (MIS-0008)."""
import pytest

from macf.pd.interface import VoiceSection


def test_lockout_defaults():
    """R40: three unmatched attempts start a ten-minute lockout unless the voice section says otherwise."""
    section = VoiceSection(capture_unit="capture")
    assert (section.lockout_attempts, section.lockout_s) == (3, 600.0)
    declared = VoiceSection(capture_unit="capture", lockout_attempts=5, lockout_s=120)
    assert (declared.lockout_attempts, declared.lockout_s) == (5, 120.0)


def test_trigger_devices_declared():
    """R17: a hotkey is read only from a declared trigger device, so a key with no device is refused."""
    with pytest.raises(ValueError, match="no trigger_devices"):
        VoiceSection(capture_unit="capture", hold_key="KEY_F9")
    section = VoiceSection(capture_unit="capture", hold_key="KEY_F9", toggle_key="KEY_F10",
                           trigger_devices=["/dev/input/by-id/usb-keyboard-event-kbd"])
    assert section.trigger_devices == ["/dev/input/by-id/usb-keyboard-event-kbd"]


@pytest.mark.parametrize("keys, why", [
    ({"hold_key": "KEY_F9", "toggle_key": "KEY_F9"}, "both the hold key and the toggle key"),
    ({"hold_key": "F9"}, "should match pattern"),
])
def test_a_key_that_cannot_work_is_refused(keys, why):
    with pytest.raises(ValueError, match=why):
        VoiceSection(capture_unit="capture", trigger_devices=["/dev/input/event3"], **keys)


def test_a_wake_needs_its_phrase_and_its_model():
    with pytest.raises(ValueError, match="a wake needs both"):
        VoiceSection(capture_unit="capture", wake_phrase="yo tom")
    assert VoiceSection(capture_unit="capture", wake_phrase="yo tom", wake_model="wake/yo_tom.joblib").wake_phrase


@pytest.mark.parametrize("field, value", [("lockout_attempts", 0), ("lockout_s", 0), ("lockout_window_s", -1)])
def test_a_lockout_setting_that_cannot_work_is_refused(field, value):
    with pytest.raises(ValueError):
        VoiceSection(capture_unit="capture", **{field: value})


def _member(phrase=None, hold=None, toggle=None):
    keyed = {"trigger_devices": ["/dev/input/event3"]} if hold or toggle else {}
    wake = {"wake_phrase": phrase, "wake_model": "wake.npz"} if phrase else {}
    return VoiceSection(capture_unit="capture", hold_key=hold, toggle_key=toggle, **wake, **keyed)


def test_duplicate_phrase_or_key_refused():
    """R26: one capture unit refuses two agents with the same wake phrase, as words, or the same key
    in any role, naming every clash; distinct agents load."""
    from macf.voice.capture.members import MembersRefused, check_members
    check_members({"A_1": _member("yo tom", "KEY_F9"), "B_2": _member("hey ira", "KEY_F10")})
    with pytest.raises(MembersRefused) as refused:
        check_members({"A_1": _member("Yo, Tom!", "KEY_F9"), "B_2": _member("yo tom", toggle="KEY_F9")})
    assert "both declare the wake phrase 'yo tom'" in str(refused.value)
    assert "both declare the key KEY_F9" in str(refused.value)
    check_members({"A_1": _member(hold="KEY_F9", toggle="KEY_F10")})   # one agent, two keys of its own
