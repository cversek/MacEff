"""The capture unit's Linux backends (MIS-0008 R14): PipeWire audio, the screen's lock state, keys read
from declared input devices, and a layer-shell indicator.

Each passes ``macf.voice.capture.contract``. None needs a Python package beyond NumPy: audio comes
from ``pw-record``, keys from the kernel's input events read directly, and the indicator runs as its
own process under the system's Python, which carries GTK.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from macf.voice.capture.backends import FRAME, RATE, AudioEnded, AudioIn, Indicator, KeyEvent, LockState, Screen
from macf.voice.capture.backends import TriggerSource, level

#: How long a closing microphone has to stop before the unit says it didn't.
CLOSE_WAIT_S = 2.0


class PipeWireAudio(AudioIn):
    """The default microphone through ``pw-record``, 16 kHz mono s16, read from its pipe.

    Opening starts the recorder and closing ends it, so the desktop's own microphone indicator
    agrees with the capture unit's state: off really means not read (R15).
    """

    def __init__(self, command: Sequence[str] = ("pw-record", "--rate=16000", "--channels=1", "--format=s16",
                                                 "--raw", "-")):
        self.command = list(command)
        self._proc: Optional[subprocess.Popen] = None

    def open(self) -> None:
        if self._proc is not None:
            return
        if shutil.which(self.command[0]) is None:
            raise AudioEnded(f"{self.command[0]} is not on PATH, so the microphone can't be read")
        self._proc = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def read(self) -> np.ndarray:
        if self._proc is None:
            raise AudioEnded("the microphone is closed")
        raw = self._proc.stdout.read(FRAME * 2)
        if len(raw) < FRAME * 2:
            raise AudioEnded(f"the microphone's stream ended (recorder exit {self._proc.poll()})")
        return np.frombuffer(raw, dtype=np.int16).copy()

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=CLOSE_WAIT_S)
        except subprocess.TimeoutExpired:
            print(f"⚠️ MACF: voice: the recorder (pid {proc.pid}) didn't stop within {CLOSE_WAIT_S:g} s of "
                  f"being asked; the microphone may still be open", file=sys.stderr)
        proc.stdout.close()

    @property
    def is_open(self) -> bool:
        return self._proc is not None


#: Screen lockers whose running process means the screen is locked.
LOCKERS = ("hyprlock", "swaylock", "gtklock", "i3lock", "waylock")


class LinuxLockState(LockState):
    """Locked when a known screen locker runs, or logind's lock hint says so; unlocked when logind
    says not and no locker runs; unknown when neither can be read (R07 treats that as locked)."""

    def __init__(self, session: Optional[str] = None):
        self.session = session or os.environ.get("XDG_SESSION_ID") or "auto"

    def state(self) -> Screen:
        if self._locker_running():
            return "locked"
        try:
            out = subprocess.run(["loginctl", "show-session", self.session, "-p", "LockedHint", "--value"],
                                 capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            return "unknown"
        hint = out.stdout.strip()
        if out.returncode != 0 or hint not in ("yes", "no"):
            return "unknown"
        return "locked" if hint == "yes" else "unlocked"

    @staticmethod
    def _locker_running() -> bool:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                name = Path(f"/proc/{pid}/comm").read_text().strip()
            except OSError:
                continue  # noqa: S112 - a process gone between listing and reading is not a locker
            if name in LOCKERS:
                return True
        return False


# ---------------------------------------------------------------- keys

#: struct input_event on 64-bit Linux: a timeval, then type, code and value.
_EVENT = struct.Struct("llHHi")
EV_KEY = 1
#: Key codes by name, from linux/input-event-codes.h, for the keys a voice section is likely to name.
KEY_CODES: Dict[str, int] = {
    **{f"KEY_F{n}": 58 + n for n in range(1, 11)}, "KEY_F11": 87, "KEY_F12": 88,
    **{f"KEY_F{n}": 170 + n for n in range(13, 25)},
    "KEY_PAUSE": 119, "KEY_SCROLLLOCK": 70, "KEY_INSERT": 110, "KEY_MENU": 139, "KEY_COMPOSE": 127,
    "KEY_RIGHTCTRL": 97, "KEY_RIGHTALT": 100, "KEY_RIGHTMETA": 126, "KEY_MICMUTE": 248,
}
KEY_NAMES: Dict[int, str] = {code: name for name, code in KEY_CODES.items()}


class EvdevTriggers(TriggerSource):
    """Key presses read straight from declared input devices (R17). Opened non-blocking, so a poll
    never waits. Key repeats are ignored: a held key is one press and one release.

    Reading ``/dev/input`` needs access the platform grants, on Linux a udev rule for the declared
    device; an unreadable device is refused at construction, naming it.
    """

    def __init__(self, devices: Sequence[str]):
        self._fds: List[int] = []
        self._partial: Dict[int, bytes] = {}
        for device in devices:
            try:
                fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
            except OSError as e:
                self.close()
                raise PermissionError(f"the trigger device {device} can't be read ({e.strerror}); grant this "
                                      f"account read access to it, on Linux with a udev rule") from e
            self._fds.append(fd)
            self._partial[fd] = b""

    def poll(self) -> List[KeyEvent]:
        events: List[KeyEvent] = []
        for fd in self._fds:
            data = self._partial[fd]
            while True:
                try:
                    chunk = os.read(fd, _EVENT.size * 64)
                except BlockingIOError:
                    break
                if not chunk:
                    break
                data += chunk
            whole = len(data) - len(data) % _EVENT.size
            for offset in range(0, whole, _EVENT.size):
                _sec, _usec, kind, code, value = _EVENT.unpack_from(data, offset)  # noqa: MACEFF005 - the kernel's fixed struct
                if kind == EV_KEY and value in (0, 1):
                    events.append(KeyEvent(KEY_NAMES.get(code, f"KEY_{code}"), value == 1))
            self._partial[fd] = data[whole:]
        return events

    def close(self) -> None:
        for fd in self._fds:
            try:
                os.close(fd)
            except OSError as e:
                print(f"⚠️ MACF: voice: closing a trigger device failed: {e}", file=sys.stderr)
        self._fds = []


def pack_key(name: str, down: bool) -> bytes:
    """One key event as the kernel writes it: for tests that feed a device through a pipe."""
    return _EVENT.pack(0, 0, EV_KEY, KEY_CODES[name], 1 if down else 0)


# ---------------------------------------------------------------- the indicator

#: The overlay's program, run under the system's Python, which carries GTK 4 and its layer shell.
OVERLAY = Path(importlib.util.find_spec("macf.voice.indicator_overlay").origin)  # found, not imported: it needs GTK
SYSTEM_PYTHON = "/usr/bin/python3"
LAYER_SHELL_LIB = "/usr/lib/libgtk4-layer-shell.so"
#: Points of the waveform sent per frame: enough to draw, little enough to send 12 times a second.
WAVE_POINTS = 48


class OverlayIndicator(Indicator):
    """The indicator as an overlay process (``indicator_overlay.py``), fed one JSON line per call.

    The overlay only draws what it is sent; nothing flows back. Started at construction, so a
    desktop that can't show it is refused before any recording, rather than recording unseen (R21).
    """

    def __init__(self, python: str = SYSTEM_PYTHON, overlay: Path = OVERLAY, settle_s: float = 1.0,
                 preload: Optional[str] = LAYER_SHELL_LIB):
        if not Path(python).exists():
            raise RuntimeError(f"{python} is not here, so the indicator can't be drawn")
        env = dict(os.environ)
        # gtk4-layer-shell must load before libwayland-client, which a Python program can only
        # arrange by preloading it; without that the compositor's layer shell is never found.
        if preload and Path(preload).exists():
            env["LD_PRELOAD"] = " ".join(p for p in (env.get("LD_PRELOAD", ""), preload) if p)
        self._proc = subprocess.Popen([python, str(overlay)], stdin=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self._shown = False
        try:
            code = self._proc.wait(timeout=settle_s)
        except subprocess.TimeoutExpired:
            code = None                      # still running: it found its display
        if code is None:
            return
        err = self._proc.stderr.read().decode(errors="replace").strip().splitlines()
        raise RuntimeError(f"the indicator overlay couldn't start (exit {code}): {err[-1] if err else 'no message'}")

    def _send(self, message: dict) -> None:
        if self._proc.poll() is not None:
            err = self._proc.stderr.read().decode(errors="replace").strip().splitlines()
            raise RuntimeError(f"the indicator overlay exited ({self._proc.returncode}): "
                               f"{err[-1] if err else 'no message'}")
        self._proc.stdin.write(json.dumps(message).encode() + b"\n")
        self._proc.stdin.flush()

    def show(self, agent, mode) -> None:
        self._send({"show": {"agent": agent, "mode": mode}})
        self._shown = True

    def feed(self, frame) -> None:
        step = max(1, frame.size // WAVE_POINTS)
        wave = (frame[::step][:WAVE_POINTS].astype(np.float64) / 32768.0).round(3).tolist()
        self._send({"level": round(level(frame), 4), "wave": wave})

    def hide(self) -> None:
        self._send({"hide": True})
        self._shown = False

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.stdin.close()
            self._proc.terminate()
            try:
                self._proc.wait(timeout=CLOSE_WAIT_S)
            except subprocess.TimeoutExpired:
                print("⚠️ MACF: voice: the indicator overlay didn't stop when asked", file=sys.stderr)


__all__ = ["EvdevTriggers", "LinuxLockState", "OverlayIndicator", "PipeWireAudio", "RATE", "pack_key"]
