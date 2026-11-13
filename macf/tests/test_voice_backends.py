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


@pytest.mark.skipif(not (LINUX and LIVE), reason="opens the real microphone and screen: MACF_VOICE_LIVE_TESTS=1")
def test_the_live_linux_backends_pass_their_contract():
    from macf.voice.capture.linux import OverlayIndicator, PipeWireAudio
    contract.check_audio_in(PipeWireAudio)
    indicator = OverlayIndicator()
    try:
        contract.check_indicator(indicator)
    finally:
        indicator.close()


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


@pytest.mark.skipif(not LINUX, reason="Linux input events")
def test_an_unreadable_trigger_device_is_refused_by_name(tmp_path):
    from macf.voice.capture.linux import EvdevTriggers
    with pytest.raises(PermissionError, match="no-such-keyboard"):
        EvdevTriggers([str(tmp_path / "no-such-keyboard")])


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
