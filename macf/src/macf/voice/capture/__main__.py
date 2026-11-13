"""The capture unit, run by its agent's primal daemon as a declared unit (MIS-0008 6.3):

    python -m macf.voice.capture <agent home>

It reads the agent's voice section, builds this platform's backends, and hands each utterance to
the daemon on its control socket, logging the receipt (never the words). It beats liveness from its
loop, with what the microphone is doing (R16). A missing piece, a backend that can't start, or a
microphone stream that ends, is said on stderr and ends the unit, so its daemon restarts it and the
failure is seen, rather than a unit that runs and hears nothing.

The command line names only the home. Keys come from the declared trigger devices alone (R18).
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import List

from macf.voice import state
from macf.voice.capture.backends import AudioEnded, KeyEvent, TriggerSource
from macf.voice.capture.unit import CaptureConfig, CaptureUnit, Utterance

#: How long a pass sleeps while the microphone is closed, so an idle unit doesn't spin.
IDLE_S = 0.05
#: Exit codes: 78 for a configuration the unit can't run with, 1 for a stream that broke.
EX_CONFIG = 78


class NoKeys(TriggerSource):
    """No trigger devices declared: the wake phrase is the only way in."""

    def poll(self) -> List[KeyEvent]:
        return []

    def close(self) -> None:
        """Nothing to release."""


def guard_lowered(card: str) -> bool:
    """Whether the agent's daemon no longer shows a raised guard: the operator lowered it (R44).
    Asked only while the capture unit is locked out. A daemon that can't be asked keeps the lockout."""
    from macf.pd.client import DaemonUnavailable, ask
    try:
        return ask(card, {"op": "status"}).voice_guard_until is None
    except (DaemonUnavailable, OSError) as e:
        print(f"⚠️ MACF: voice: the daemon can't be asked about the guard, so the lockout stands: {e}", file=sys.stderr)
        return False


def voice_event(card: str, kind: str, data: dict) -> None:
    """Tell the daemon the voice lock failed or locked out: counts and a time, never words (R37, R39)."""
    from macf.pd.interface import control_socket
    request = {"op": "voice_event", "kind": kind, **{k: v for k, v in data.items() if k in ("attempts", "of", "until")}}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(5)
            conn.connect(str(control_socket(card)))
            conn.sendall(json.dumps(request).encode() + b"\n")
            reply = conn.recv(65536)
    except OSError as e:
        print(f"⚠️ MACF: voice: the daemon wasn't told of a voice-lock {kind}: {e}", file=sys.stderr)
        return
    if not json.loads(reply or b"{}").get("ok"):
        print(f"⚠️ MACF: voice: the daemon refused a voice-lock {kind} event: {reply[:300]!r}", file=sys.stderr)


def deliver(card: str, utterance: Utterance) -> None:
    """Hand one utterance to the agent's daemon and log its receipt, by id and outcome only."""
    from macf.pd.interface import control_socket
    request = {"op": "utterance", "trigger": utterance.trigger, "spoken_at": utterance.spoken_at,
               "screen": utterance.screen, "voice_lock": utterance.voice_lock, "text": utterance.text}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(5)
            conn.connect(str(control_socket(card)))
            conn.sendall(json.dumps(request).encode() + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
        reply = json.loads(data or b"{}")
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: voice: an utterance could not reach the daemon, so it was dropped: {e}", file=sys.stderr)
        return
    receipt = reply.get("receipt", "none")
    note = "" if receipt == "delivered" else f": {(reply.get('error') or '').splitlines()[0]}"
    print(f"🎙️ MACF: voice: {utterance.trigger} utterance {reply.get('utterance_id', '?')} {receipt}{note}",
          file=sys.stderr)


def build(home: Path):
    """The capture unit for the agent at ``home``, from its declaration and this platform's backends."""
    from macf.pd.core import load_declaration
    from macf.pd.interface import agent_card
    from macf.voice.capture.models import SileroGate, TrainedWakeDetector
    from macf.voice.transcribe import transcribe_array
    card = agent_card(home)
    declaration = load_declaration(home, card)
    voice = declaration.voice
    unit_name = os.environ.get("MACF_PD_UNIT")
    if voice is None:
        raise RuntimeError(f"{home} declares no voice section, so there is nothing to capture for")
    if unit_name and unit_name != voice.capture_unit:
        raise RuntimeError(f"this unit is {unit_name!r}, but the voice section names "
                         f"{voice.capture_unit!r} as its capture unit")
    if not sys.platform.startswith("linux"):
        raise RuntimeError("this platform has no capture backends yet; MIS-0008's porting "
                         "guide says what to write (R14)")
    from macf.voice.capture.linux import EvdevTriggers, LinuxLockState, OverlayIndicator, PipeWireAudio
    detector = None
    if voice.wake_model:
        model = Path(voice.wake_model)
        detector = TrainedWakeDetector(model if model.is_absolute() else home / model)

    def transcribe(audio, phrase):
        return transcribe_array(audio, initial_prompt=f"{phrase.capitalize()}, " if phrase else None).text

    config = CaptureConfig(agent=card, wake_phrase=voice.wake_phrase, hold_key=voice.hold_key,
                           toggle_key=voice.toggle_key,
                           detector_bar=voice.detector_bar if voice.detector_bar is not None else (
                               detector.threshold if detector is not None else 0.85),
                           end_silence_s=voice.end_silence_s, continual_close_s=voice.continual_close_s)
    return card, CaptureUnit(
        config, audio=PipeWireAudio(), lock=LinuxLockState(), indicator=OverlayIndicator(),
        triggers=EvdevTriggers(voice.trigger_devices) if voice.trigger_devices else NoKeys(),
        gate=SileroGate(), detector=detector, transcribe=transcribe,
        deliver=lambda u: deliver(card, u), on_voice_event=lambda kind, data: voice_event(card, kind, data),
        guard_lowered=lambda: guard_lowered(card),
        listening_on=lambda: state.listening_on(home),
        speaking=lambda: state.speaking(home), log=lambda s: print(f"🎙️ MACF: voice: {s}", file=sys.stderr))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    home = Path(argv[0] if argv else os.environ.get("MACEFF_AGENT_HOME_DIR", "")).expanduser()
    if not str(home) or not home.is_dir():
        print("usage: python -m macf.voice.capture <agent home>", file=sys.stderr)
        return EX_CONFIG
    try:
        card, unit = build(home)
    except (RuntimeError, PermissionError, ValueError) as e:
        print(f"⚠️ MACF: voice: the capture unit can't start: {e}", file=sys.stderr)
        return EX_CONFIG
    from macf.pd.liveness import Heartbeat
    interval = float(os.environ.get("MACF_PD_LIVENESS_S") or 0)
    heartbeat = None
    if interval:
        def microphone():
            return {k: v for k, v in unit.status().items() if v is not None} or None
        heartbeat = Heartbeat(card, os.environ.get("MACF_PD_UNIT", "capture"), interval,
                              microphone=microphone).start()
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
    try:
        while not stopping:
            unit.tick()
            if unit.recording is not None:
                state.mark_recording(home)   # the speech worker holds, and stops, while this is fresh (R29)
            if heartbeat is not None:
                heartbeat.tick()
            if unit.state == "off":
                time.sleep(IDLE_S)
    except AudioEnded as e:
        print(f"⚠️ MACF: voice: {e}; the capture unit exits for its daemon to restart it", file=sys.stderr)
        return 1
    finally:
        if heartbeat is not None:
            heartbeat.stop()
        unit.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
