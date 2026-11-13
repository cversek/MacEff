"""An agent's voice section in its declaration (MIS-0008)."""
import pytest

from macf.pd.interface import VoiceSection


def test_lockout_defaults():
    """R40: three unmatched attempts start a ten-minute lockout unless the voice section says otherwise."""
    section = VoiceSection(capture_unit="capture")
    assert (section.lockout_attempts, section.lockout_s) == (3, 600.0)
    declared = VoiceSection(capture_unit="capture", lockout_attempts=5, lockout_s=120)
    assert (declared.lockout_attempts, declared.lockout_s) == (5, 120.0)


@pytest.mark.parametrize("field, value", [("lockout_attempts", 0), ("lockout_s", 0), ("lockout_window_s", -1)])
def test_a_lockout_setting_that_cannot_work_is_refused(field, value):
    with pytest.raises(ValueError):
        VoiceSection(capture_unit="capture", **{field: value})
