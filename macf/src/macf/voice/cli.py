"""``macf_tools voice listen`` and ``voice capture status``: the operator's switch for listening, and
what the capture unit's microphone is doing (MIS-0008 R15, R16).

Neither can trigger a recording. Listening off closes the microphone between recordings; only a
declared trigger device or the wake phrase opens one (R17, R18).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from macf.voice import state

#: How long ``listen on|off`` waits for the capture unit's status to agree before saying it didn't.
AGREE_WAIT_S = 6.0


def add_parsers(voice_sub) -> None:
    listen = voice_sub.add_parser("listen", help="turn listening for the wake phrase on or off, or say which it is")
    listen.add_argument("switch", nargs="?", choices=("on", "off"), help="on or off; omit to ask")
    listen.set_defaults(func=cmd_voice_listen)
    capture = voice_sub.add_parser("capture", help="the capture unit")
    capture_sub = capture.add_subparsers(dest="voice_capture_cmd")
    capture_sub.add_parser("status", help="what the capture unit's microphone is doing now").set_defaults(
        func=cmd_voice_capture_status)


def _home() -> Path:
    from macf.utils.paths import find_agent_home
    return find_agent_home()


@dataclass(frozen=True)
class Reading:
    """The capture unit's microphone as its daemon's status shows it: ``mic`` is a dict (``{}`` when
    the unit runs and reports none), or None with ``why`` saying what stood in the way."""

    mic: Optional[dict]
    why: str = ""


def microphone(home: Path) -> Reading:
    from macf.pd.client import DaemonUnavailable, ask
    from macf.pd.core import DeclarationRefused, load_declaration
    from macf.pd.interface import agent_card
    try:
        card = agent_card(home)
        declaration = load_declaration(home, card)
    except (OSError, ValueError, DeclarationRefused) as e:
        return Reading(None, f"the declaration can't be read: {e}")
    voice = declaration.voice
    if declaration.voice_dispatch is not None:
        unit_name = declaration.voice_dispatch.capture_unit       # a system's one unit for its members
    elif voice is None:
        return Reading(None, "this agent declares no voice section")
    elif voice.capture_unit is None:
        return Reading(None, f"this agent's voice comes from {voice.dispatched_by}'s capture unit; that system's "
                             f"status shows its microphone")
    else:
        unit_name = voice.capture_unit
    try:
        reply = ask(card, {"op": "status"})
    except (DaemonUnavailable, OSError) as e:
        return Reading(None, f"the primal daemon can't be asked: {e}")
    unit = next((u for u in reply.units or [] if u.unit == unit_name), None)
    if unit is None or unit.state != "running":
        return Reading(None, f"the capture unit {unit_name!r} is {unit.state if unit else 'not declared'}")
    return Reading(unit.microphone.model_dump(exclude_none=True) if unit.microphone else {})


def describe(reading: Reading, now: Optional[float] = None) -> str:
    now = now or time.time()
    mic = reading.mic
    if mic is None:
        return reading.why or "no capture unit is running"
    if mic.get("recording_since"):
        mode = (mic.get("mode") or "").replace("_", " ")
        return (f"recording for {mic.get('recording_for')} ({mode}), "
                f"{now - mic['recording_since']:.0f} s")
    if mic.get("listening_since"):
        return f"listening for the wake phrase, {now - mic['listening_since']:.0f} s"
    return "microphone closed"


def cmd_voice_listen(args) -> int:
    home = _home()
    if args.switch is None:
        print(f"listening is {'on' if state.listening_on(home) else 'off'}; the capture unit: {describe(microphone(home))}")
        return 0
    state.set_listening(home, args.switch == "on")
    want = args.switch == "on"

    def agrees(mic: dict) -> bool:
        return bool(mic.get("listening_since")) == want or bool(mic.get("recording_since"))

    # Say what happened, not what was meant: wait for the capture unit's own status to agree.
    deadline = time.monotonic() + AGREE_WAIT_S
    reading = microphone(home)
    while reading.mic is not None and not agrees(reading.mic) and time.monotonic() < deadline:
        time.sleep(0.5)
        reading = microphone(home)
    print(f"listening turned {args.switch}; the capture unit: {describe(reading)}")
    if reading.mic is not None and not agrees(reading.mic):
        print(f"⚠️ the capture unit's status didn't agree within {AGREE_WAIT_S:g} s; it may not have read the switch yet")
        return 1
    return 0


def cmd_voice_capture_status(args) -> int:
    reading = microphone(_home())
    print(describe(reading))
    return 0 if reading.mic is not None else 1
