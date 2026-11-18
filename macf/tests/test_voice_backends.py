"""Every capture backend against its contract (MIS-0008 R14).

The fakes and the Linux backends that touch nothing personal run everywhere they can. The real
microphone and the on-screen overlay run only when MACF_VOICE_LIVE_TESTS=1: a test run should
never open someone's microphone, or show a recording sign on their screen, unasked.
"""
import os
import sys
from dataclasses import dataclass

import pytest

from macf.voice.capture import contract
from macf.voice.capture.backends import AudioEnded, KeyEvent
from voice_fakes import FakeAudio, FakeLock, PushedKeys, RecordingIndicator

LINUX = sys.platform.startswith("linux")
MACOS = sys.platform == "darwin"
LIVE = os.environ.get("MACF_VOICE_LIVE_TESTS") == "1"


@dataclass(frozen=True)
class PipeDevice:
    """A trigger 'device' made of a pipe: the read end's path, and the write end to feed it."""

    path: str
    write_fd: int
    read_fd: int

    def close(self):
        os.close(self.write_fd)
        os.close(self.read_fd)


def _pipe_device() -> PipeDevice:
    r, w = os.pipe()
    return PipeDevice(f"/proc/self/fd/{r}", w, r)


def test_every_backend_passes_its_contract():
    """R14: the fakes, and each shipped backend this machine can run without touching a person's
    microphone or screen, keep the contract a porter's backends must keep."""
    contract.check_audio_in(FakeAudio)
    contract.check_lock_state(FakeLock())
    contract.check_indicator(RecordingIndicator())
    contract.check_trigger_source(PushedKeys())
    if LINUX:
        from macf.voice.capture.linux import EvdevTriggers, LinuxLockState
        contract.check_lock_state(LinuxLockState())
        device = _pipe_device()
        try:
            contract.check_trigger_source(EvdevTriggers([device.path]))
        finally:
            device.close()
    if MACOS:
        from macf.voice.capture.macos import MacLockState
        contract.check_lock_state(MacLockState())


@pytest.mark.skipif(not (LINUX and LIVE), reason="opens the real microphone and screen: MACF_VOICE_LIVE_TESTS=1")
def test_the_live_linux_backends_pass_their_contract():
    from macf.voice.capture.linux import OverlayIndicator, PipeWireAudio
    contract.check_audio_in(PipeWireAudio)
    indicator = OverlayIndicator()
    try:
        contract.check_indicator(indicator)
    finally:
        indicator.close()


@pytest.mark.skipif(not (MACOS and LIVE), reason="opens the real microphone: MACF_VOICE_LIVE_TESTS=1")
def test_the_live_macos_backends_pass_their_contract():
    from macf.voice.capture.macos import MacAudioIn
    contract.check_audio_in(MacAudioIn)


@pytest.mark.skipif(not MACOS, reason="macOS HID usages")
def test_mac_keys_carry_the_linux_names_and_only_declared_keyboards_count():
    """R17: a key is named as the voice section names it everywhere, and a keyboard counts only when declared."""
    from macf.voice.capture.macos import declared, hid_key_name
    assert hid_key_name(0x07, 0x43) == "KEY_F10" and hid_key_name(0x07, 0x68) == "KEY_F13"
    assert hid_key_name(0x07, 0xE7) == "KEY_RIGHTMETA" and hid_key_name(0x07, 0x01) is None
    assert hid_key_name(0x0C, 0xE9) is None   # a consumer key (volume) is not a keyboard key
    assert declared("05ac:0342", "Apple Internal Keyboard / Trackpad", 0x05AC, 0x0342)
    assert declared("Apple Internal Keyboard / Trackpad", "apple internal keyboard / trackpad", 1, 2)
    assert not declared("05ac:0342", "Apple Internal Keyboard / Trackpad", 0x05AC, 0x0343)
    assert not declared("zz:01", "x", 0, 1)


@pytest.mark.skipif(not MACOS, reason="macOS audio out")
def test_the_macos_audio_out_passes_its_contract():
    """Plays only silence, so it runs without asking: stop works idle, mid-sentence and from another thread."""
    import time
    from macf.voice.speech.backends import check_audio_out
    from macf.voice.speech.macos import MacAudioOut
    started = time.monotonic()
    check_audio_out(MacAudioOut)
    assert time.monotonic() - started < 2.0, "a stop 50 ms into a 5 s sentence must end it, not let it run"


@pytest.mark.skipif(not MACOS, reason="macOS session dictionary")
def test_a_session_dictionary_that_cannot_be_read_is_unknown():
    """R07: no dictionary, or one without the lock key's companion fields, is unknown, never unlocked."""
    from macf.voice.capture.macos import MacLockState
    assert MacLockState(read=lambda: None).state() == "unknown"
    assert MacLockState(read=lambda: {"CGSSessionScreenIsLocked": 1}).state() == "locked"
    assert MacLockState(read=lambda: {"kCGSSessionOnConsoleKey": 1}).state() == "unlocked"
    assert MacLockState(read=lambda: {"kCGSSessionOnConsoleKey": 0}).state() == "locked"  # switched away
    def broken():
        raise RuntimeError("Quartz went away")
    assert MacLockState(read=broken).state() == "unknown"


@pytest.mark.skipif(not MACOS, reason="macOS audio")
def test_a_microphone_that_cannot_open_is_said_not_read_as_silence(monkeypatch):
    from macf.voice.capture import macos
    def refuse(*args, **kwargs):
        raise OSError("no default input device")
    monkeypatch.setattr(macos, "_open_stream", refuse)
    mic = macos.MacAudioIn()
    with pytest.raises(AudioEnded, match="no default input device"):
        mic.open()
    assert not mic.is_open


@pytest.mark.skipif(not LINUX, reason="Linux input events")
def test_keys_are_read_from_a_declared_device_as_presses_and_releases():
    """A press and a release each arrive once; a key's repeat while held is ignored; half an event
    waits for the rest rather than being misread."""
    from macf.voice.capture.linux import EvdevTriggers, _EVENT, pack_key
    device = _pipe_device()
    w = device.write_fd
    keys = EvdevTriggers([device.path])
    try:
        held = pack_key("KEY_F9", True)
        repeat = _EVENT.pack(0, 0, 1, 67, 2)
        os.write(w, held + repeat + pack_key("KEY_F9", False)[:10])
        assert keys.poll() == [KeyEvent("KEY_F9", True)]
        os.write(w, pack_key("KEY_F9", False)[10:])
        assert keys.poll() == [KeyEvent("KEY_F9", False)]
        assert keys.poll() == []
    finally:
        keys.close()
        device.close()


@pytest.mark.skipif(not LINUX or os.geteuid() == 0, reason="Linux input events; root reads any file")
def test_an_unreadable_trigger_device_is_refused_by_name(tmp_path):
    from macf.voice.capture.linux import EvdevTriggers
    locked = tmp_path / "locked-keyboard"
    locked.write_bytes(b"")
    locked.chmod(0)
    with pytest.raises(PermissionError, match="locked-keyboard.*udev rule"):
        EvdevTriggers([str(locked)])


@pytest.mark.skipif(not LINUX, reason="Linux input events")
def test_a_trigger_device_that_is_not_there_is_skipped_and_said(tmp_path, capsys):
    """An unplugged keyboard turned off its keys, never the unit: refusing it crash-looped a capture unit
    every five minutes for half a day, taking the wake phrase down too. And it is said as missing, not as
    a grant to add."""
    from macf.voice.capture.linux import EvdevTriggers
    present = _pipe_device()
    keys = EvdevTriggers([str(tmp_path / "no-such-keyboard"), present.path])
    try:
        err = capsys.readouterr().err
        assert "no-such-keyboard is not there" in err and "udev" not in err
        assert keys.missing == [str(tmp_path / "no-such-keyboard")]
        os.write(present.write_fd, __import__("macf.voice.capture.linux", fromlist=["pack_key"]).pack_key("KEY_F9", True))
        assert keys.poll() == [KeyEvent("KEY_F9", True)]     # the device that is there still works
    finally:
        keys.close()
        present.close()


def test_a_missing_recorder_is_said_not_read_as_silence():
    from macf.voice.capture.linux import PipeWireAudio
    mic = PipeWireAudio(command=("no-such-recorder-xyz", "--raw"))
    with pytest.raises(AudioEnded, match="no-such-recorder-xyz is not on PATH"):
        mic.open()


def test_an_indicator_that_cannot_start_is_refused_before_any_recording(tmp_path):
    """R21: a desktop that can't show the indicator is refused at construction, with the overlay's
    own reason, so nothing is ever recorded unseen."""
    from macf.voice.capture.linux import OverlayIndicator
    failing = tmp_path / "overlay.py"
    failing.write_text('import sys\nprint("indicator overlay: no display to draw on", file=sys.stderr)\nsys.exit(2)\n')
    with pytest.raises(RuntimeError, match="couldn't start .exit 2.: indicator overlay: no display"):
        OverlayIndicator(python=sys.executable, overlay=failing, preload=None)
