"""The capture backends for macOS (MIS-0008 R14; docs/VOICE_PORTING.md section 6).

Each keeps the promise its interface in ``backends`` makes, checked by ``contract``. The
microphone and the screen belong to the console user's login session on a Mac, so these run
in that session: a capture unit started outside it (over ssh, or as a system daemon) gets no
microphone and reads the screen as ``unknown``.
"""
from __future__ import annotations

import queue
from dataclasses import dataclass
import sys
import threading
from typing import Any, Callable, List, Optional, Sequence

import numpy as np

from macf.voice.capture.backends import FRAME, RATE, AudioEnded, AudioIn, KeyEvent, LockState, Screen, TriggerSource


#: A frame is 32 ms; this long with none means the device is gone (unplugged, or taken by another app).
READ_TIMEOUT_S = 2.0


def _open_stream(frames):
    """The default input as a 16 kHz mono int16 stream; Core Audio resamples. Each block lands in frames.

    PortAudio is re-initialized first, so the default device is the one that exists now: the device list
    it holds is a snapshot from its initialization, and a microphone plugged in or pulled since is not in it.
    """
    import sounddevice
    sounddevice._terminate()
    sounddevice._initialize()

    def arrived(indata, _frame_count, _time, status):
        frames.put((bytes(indata), bool(status.input_overflow)))

    stream = sounddevice.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME,
                                        callback=arrived)
    stream.start()
    return stream


#: AVAuthorizationStatus values: not yet asked, restricted, denied, authorized.
NOT_DETERMINED, RESTRICTED, DENIED, AUTHORIZED = 0, 1, 2, 3


def _microphone_access(wait_s: float = 120.0) -> int:
    """This process's microphone authorization, asking macOS for it if it was never asked.

    PortAudio opens a microphone this process may not use without complaint and reads zeros, so the
    capture unit would record silence and call it quiet. Asking through AVFoundation is what makes
    macOS show its prompt for the process (Python, under a daemon), and tells denied from granted."""
    import AVFoundation
    status = int(AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(AVFoundation.AVMediaTypeAudio))
    if status != NOT_DETERMINED:
        return status
    answered = threading.Event()
    result = []

    def done(granted):
        result.append(AUTHORIZED if granted else DENIED)
        answered.set()

    AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVFoundation.AVMediaTypeAudio, done)
    answered.wait(wait_s)
    return result[0] if result else NOT_DETERMINED


class MacAudioIn(AudioIn):
    """The default microphone through PortAudio (``sounddevice``), read in memory only (R13).

    Opening starts the stream and closing stops and closes it, so the orange microphone dot in
    the menu bar agrees with the capture unit: off really means not read (R15). The first open
    asks macOS for the microphone permission on behalf of the process that runs the unit.
    """

    def __init__(self) -> None:
        self._stream: Optional[Any] = None
        self._frames: "queue.Queue[tuple]" = queue.Queue()
        self.overflows = 0

    def open(self) -> None:
        if self._stream is not None:
            return
        access = _microphone_access()
        if access != AUTHORIZED:
            why = {DENIED: "was denied", RESTRICTED: "is restricted", NOT_DETERMINED: "was not answered"}[access]
            from macf.voice.capture.disclaim import own_executable
            raise AudioEnded(f"microphone access {why} for {own_executable()}; allow it in System Settings, "
                             f"Privacy & Security, Microphone, then restart the capture unit")
        try:
            self._frames = queue.Queue()
            self._stream = _open_stream(self._frames)
        except (OSError, ImportError) as e:   # sounddevice raises PortAudioError, an OSError subclass
            raise AudioEnded(f"the microphone can't be opened: {e}") from e

    def read(self) -> np.ndarray:
        if self._stream is None:
            raise AudioEnded("the microphone is closed")
        try:
            raw, overflowed = self._frames.get(timeout=READ_TIMEOUT_S)
        except queue.Empty:
            raise AudioEnded(f"the microphone sent nothing for {READ_TIMEOUT_S:.0f} s; the device may be gone") from None
        if overflowed:
            self.overflows += 1
            if self.overflows == 1:
                print("⚠️ MACF: voice: the microphone overflowed (frames were lost while the unit was busy); "
                      "counting further ones in MacAudioIn.overflows", file=sys.stderr)
        frame = np.frombuffer(bytes(raw), dtype=np.int16).copy()
        if frame.shape != (FRAME,):
            raise AudioEnded(f"the microphone returned {frame.size} samples, not a frame of {FRAME}")
        return frame

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.stop()
            stream.close()
        except OSError as e:
            print(f"⚠️ MACF: voice: closing the microphone failed ({e}); it may still be open", file=sys.stderr)

    @property
    def is_open(self) -> bool:
        return self._stream is not None


def _session_dictionary() -> Optional[dict]:
    import Quartz
    found = Quartz.CGSessionCopyCurrentDictionary()
    return dict(found) if found is not None else None


class MacLockState(LockState):
    """From Quartz's session dictionary: locked while ``CGSSessionScreenIsLocked`` is set or the
    session is not on the console (another user switched in); unlocked only when the session is on
    the console and the lock key is absent; unknown otherwise, which R07 treats as locked."""

    def __init__(self, read: Callable[[], Optional[dict]] = _session_dictionary) -> None:
        self._read = read
        self._warned = False

    def state(self) -> Screen:
        try:
            session = self._read()
        except Exception as e:  # noqa: BLE001 - R07: any failure to read is "unknown"; said the first time
            if not self._warned:
                self._warned = True
                print(f"⚠️ MACF: voice: the screen's lock state can't be read ({e}); treating it as unknown "
                      f"(said once; later failures are silent while they last)", file=sys.stderr)
            return "unknown"
        if not session:
            return "unknown"
        if session.get("CGSSessionScreenIsLocked"):
            return "locked"
        on_console = session.get("kCGSSessionOnConsoleKey")
        if on_console is None:
            return "unknown"
        return "unlocked" if on_console else "locked"


def MacIndicator(settle_s: float = 1.0):
    """The indicator as its own AppKit process (``indicator_overlay_macos.py``) under this Python, which
    carries PyObjC; fed the same JSON lines as the Linux overlay, so the Linux driver class serves both."""
    import importlib.util
    from pathlib import Path

    from macf.voice.capture.linux import OverlayIndicator
    overlay = Path(importlib.util.find_spec("macf.voice.indicator_overlay_macos").origin)
    return OverlayIndicator(python=sys.executable, overlay=overlay, settle_s=settle_s, preload=None)


# ---------------------------------------------------------------- triggers: the HID manager, read directly

#: Keyboard usages (HID usage page 7) to the Linux key names the voice section already uses.
HID_KEY_NAMES = {**{0x04 + i: f"KEY_{chr(ord('A') + i)}" for i in range(26)},
                 **{0x3A + i: f"KEY_F{1 + i}" for i in range(12)},
                 **{0x68 + i: f"KEY_F{13 + i}" for i in range(12)},
                 0x28: "KEY_ENTER", 0x29: "KEY_ESC", 0x2B: "KEY_TAB", 0x2C: "KEY_SPACE", 0x39: "KEY_CAPSLOCK",
                 0x46: "KEY_SYSRQ", 0x47: "KEY_SCROLLLOCK", 0x48: "KEY_PAUSE", 0x49: "KEY_INSERT",
                 0x4A: "KEY_HOME", 0x4B: "KEY_PAGEUP", 0x4D: "KEY_END", 0x4E: "KEY_PAGEDOWN",
                 0x4F: "KEY_RIGHT", 0x50: "KEY_LEFT", 0x51: "KEY_DOWN", 0x52: "KEY_UP",
                 0xE0: "KEY_LEFTCTRL", 0xE1: "KEY_LEFTSHIFT", 0xE2: "KEY_LEFTALT", 0xE3: "KEY_LEFTMETA",
                 0xE4: "KEY_RIGHTCTRL", 0xE5: "KEY_RIGHTSHIFT", 0xE6: "KEY_RIGHTALT", 0xE7: "KEY_RIGHTMETA"}
K_IO_RETURN_NOT_PERMITTED = 0xE00002E2


def hid_key_name(usage_page: int, usage: int) -> Optional[str]:
    """The Linux name of a keyboard usage, or None for anything that is not a keyboard key."""
    if usage_page != 0x07 or usage in (0, 1, 2, 3) or usage > 0xE7:
        return None
    return HID_KEY_NAMES.get(usage, f"KEY_HID_{usage:02X}")


@dataclass(frozen=True, kw_only=True)
class HidIdentity:
    """Which HID device a key event came from, as a declaration can name it."""
    product: str
    vendor_id: int
    product_id: int


def declared(device: str, product: str, vendor_id: int, product_id: int) -> bool:
    """Whether a HID device is the one a declaration names: ``vvvv:pppp`` in hex, or its product name."""
    if ":" in device:
        vendor, prod = device.split(":", 1)
        try:
            return int(vendor, 16) == vendor_id and int(prod, 16) == product_id
        except ValueError:
            return False
    return device.strip().lower() == (product or "").strip().lower()


class MacTriggers(TriggerSource):
    """Key presses read from declared keyboards through the HID manager (R17), on a run loop thread of
    its own; ``poll`` only drains what arrived. Nothing outside this process can press a key for it
    (R18): no socket, no event tap, no synthetic events, since the HID manager sees hardware reports.

    Reading keyboards needs the Input Monitoring permission for the process that runs the unit. Without
    it opening is refused naming the grant. A declared keyboard that isn't attached simply sends no
    keys; the HID manager can't tell an absent device from a quiet one, and the wake phrase still works.
    """

    def __init__(self, devices: Sequence[str]):
        import ctypes
        import ctypes.util
        import queue
        self._devices = [d for d in devices if d.strip()]
        self._events: "queue.SimpleQueue[KeyEvent]" = queue.SimpleQueue()
        self._iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
        self._cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        self._prepare_ctypes(ctypes)
        self._manager = self._iokit.IOHIDManagerCreate(None, 0)
        self._iokit.IOHIDManagerSetDeviceMatching(self._manager, self._keyboard_matching(ctypes))
        callback_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        self._callback = callback_type(self._on_value)          # kept alive as long as the manager
        self._iokit.IOHIDManagerRegisterInputValueCallback(self._manager, self._callback, None)
        self._loop = None
        ready = threading.Event()
        self._opened: list = []
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True, name="voice-hid-triggers")
        self._thread.start()
        ready.wait(5.0)
        result = self._opened[0] if self._opened else None
        if result == K_IO_RETURN_NOT_PERMITTED:
            self.close()
            raise PermissionError("the keyboards can't be read: grant Input Monitoring to the process that runs "
                                  "the capture unit (System Settings, Privacy & Security, Input Monitoring)")
        if result not in (0, None):
            self.close()
            raise PermissionError(f"the HID manager refused to open (IOReturn 0x{result & 0xFFFFFFFF:08X})")

    @staticmethod
    def _cfstr(cf, ctypes, text: str):
        return cf.CFStringCreateWithCString(None, text.encode(), 0x08000100)  # kCFStringEncodingUTF8

    def _prepare_ctypes(self, ctypes) -> None:
        io, cf = self._iokit, self._cf
        vp = ctypes.c_void_p
        io.IOHIDManagerCreate.restype = vp
        io.IOHIDManagerCreate.argtypes = [vp, ctypes.c_uint32]
        io.IOHIDManagerSetDeviceMatching.argtypes = [vp, vp]
        io.IOHIDManagerRegisterInputValueCallback.argtypes = [vp, vp, vp]
        io.IOHIDManagerScheduleWithRunLoop.argtypes = [vp, vp, vp]
        io.IOHIDManagerOpen.restype = ctypes.c_int32
        io.IOHIDManagerOpen.argtypes = [vp, ctypes.c_uint32]
        io.IOHIDManagerClose.argtypes = [vp, ctypes.c_uint32]
        io.IOHIDManagerUnscheduleFromRunLoop.argtypes = [vp, vp, vp]
        io.IOHIDValueGetElement.restype = vp
        io.IOHIDValueGetElement.argtypes = [vp]
        io.IOHIDValueGetIntegerValue.restype = ctypes.c_long
        io.IOHIDValueGetIntegerValue.argtypes = [vp]
        io.IOHIDElementGetUsagePage.restype = ctypes.c_uint32
        io.IOHIDElementGetUsagePage.argtypes = [vp]
        io.IOHIDElementGetUsage.restype = ctypes.c_uint32
        io.IOHIDElementGetUsage.argtypes = [vp]
        io.IOHIDElementGetDevice.restype = vp
        io.IOHIDElementGetDevice.argtypes = [vp]
        io.IOHIDDeviceGetProperty.restype = vp
        io.IOHIDDeviceGetProperty.argtypes = [vp, vp]
        cf.CFStringCreateWithCString.restype = vp
        cf.CFStringCreateWithCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFStringGetCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        cf.CFNumberCreate.restype = vp
        cf.CFNumberCreate.argtypes = [vp, ctypes.c_int, vp]
        cf.CFNumberGetValue.restype = ctypes.c_bool
        cf.CFNumberGetValue.argtypes = [vp, ctypes.c_int, vp]
        cf.CFDictionaryCreate.restype = vp
        cf.CFDictionaryCreate.argtypes = [vp, vp, vp, ctypes.c_long, vp, vp]
        cf.CFRunLoopGetCurrent.restype = vp
        cf.CFRunLoopGetCurrent.argtypes = []
        cf.CFRunLoopRun.restype = None
        cf.CFRunLoopStop.argtypes = [vp]
        self._mode = ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode").value
        self._keys_cb = ctypes.addressof(ctypes.c_char.in_dll(cf, "kCFTypeDictionaryKeyCallBacks"))
        self._vals_cb = ctypes.addressof(ctypes.c_char.in_dll(cf, "kCFTypeDictionaryValueCallBacks"))
        self._prop = {name: self._cfstr(cf, ctypes, name) for name in ("Product", "VendorID", "ProductID")}

    def _keyboard_matching(self, ctypes):
        cf = self._cf
        def number(n):
            value = ctypes.c_int32(n)
            return cf.CFNumberCreate(None, 3, ctypes.byref(value))   # kCFNumberSInt32Type
        keys = (ctypes.c_void_p * 2)(self._cfstr(cf, ctypes, "DeviceUsagePage"), self._cfstr(cf, ctypes, "DeviceUsage"))
        values = (ctypes.c_void_p * 2)(number(0x01), number(0x06))   # generic desktop, keyboard
        return cf.CFDictionaryCreate(None, keys, values, 2, self._keys_cb, self._vals_cb)

    def _run(self, ready) -> None:
        self._loop = self._loop_ref = self._cf.CFRunLoopGetCurrent()
        self._iokit.IOHIDManagerScheduleWithRunLoop(self._manager, self._loop, self._mode)
        self._opened.append(self._iokit.IOHIDManagerOpen(self._manager, 0) & 0xFFFFFFFF)
        ready.set()
        self._cf.CFRunLoopRun()
        # the manager lives on this thread's run loop, so it is taken down here, after the loop stops
        self._iokit.IOHIDManagerUnscheduleFromRunLoop(self._manager, self._loop_ref, self._mode)
        self._iokit.IOHIDManagerClose(self._manager, 0)

    def _device_identity(self, device):
        import ctypes
        def text(prop):
            ref = self._iokit.IOHIDDeviceGetProperty(device, self._prop[prop])
            buf = ctypes.create_string_buffer(256)
            return buf.value.decode(errors="replace") if ref and self._cf.CFStringGetCString(ref, buf, 256, 0x08000100) else ""
        def integer(prop):
            ref = self._iokit.IOHIDDeviceGetProperty(device, self._prop[prop])
            value = ctypes.c_int32(0)
            return value.value if ref and self._cf.CFNumberGetValue(ref, 3, ctypes.byref(value)) else -1
        return HidIdentity(product=text("Product"), vendor_id=integer("VendorID"), product_id=integer("ProductID"))

    def _on_value(self, _context, _result, _sender, value) -> None:
        try:
            element = self._iokit.IOHIDValueGetElement(value)
            name = hid_key_name(self._iokit.IOHIDElementGetUsagePage(element), self._iokit.IOHIDElementGetUsage(element))
            if name is None:
                return
            identity = self._device_identity(self._iokit.IOHIDElementGetDevice(element))
            if not any(declared(d, identity.product, identity.vendor_id, identity.product_id) for d in self._devices):
                return
            self._events.put(KeyEvent(name, self._iokit.IOHIDValueGetIntegerValue(value) != 0))
        except Exception as e:  # noqa: BLE001 - a callback from C must not raise; say it and drop this report
            print(f"⚠️ MACF: voice: a key report couldn't be read ({e}); dropped", file=sys.stderr)

    def poll(self) -> List[KeyEvent]:
        out: List[KeyEvent] = []
        while not self._events.empty():
            out.append(self._events.get_nowait())
        return out

    def close(self) -> None:
        loop, self._loop = self._loop, None
        if loop is not None:
            self._cf.CFRunLoopStop(loop)
            self._thread.join(2.0)
            if self._thread.is_alive():
                print("⚠️ MACF: voice: the key reader's run loop didn't stop; its keyboards may stay open",
                      file=sys.stderr)
