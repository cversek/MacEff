"""The speech worker, run by its agent's primal daemon as a declared unit (MIS-0008 6.6):

    python -m macf.voice.speech <agent home>

It takes the one-worker lock or exits 75, then speaks each queued message in the voice its voice
section declares. The Kokoro model and voices files live in the agent's voice directory, under
``models/``; a missing one is said and the unit exits 78.
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

from macf.voice import state
from macf.voice.speech import worker as speech

EX_CONFIG = 78


def settings_for(home: Path):
    """The voice section's speech settings, read fresh for each message so a new choice takes
    effect without a restart; the framework's defaults where none is declared."""
    from macf.pd.core import load_declaration
    from macf.pd.interface import SpeechSettings, agent_card
    voice = load_declaration(home, agent_card(home)).voice
    return (voice.speech if voice and voice.speech else None) or SpeechSettings()


def models_dir(home: Path) -> Path:
    return state.voice_dir(home) / "models"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    home = Path(argv[0] if argv else os.environ.get("MACEFF_AGENT_HOME_DIR", "")).expanduser()
    if not str(home) or not home.is_dir():
        print("usage: python -m macf.voice.speech <agent home>", file=sys.stderr)
        return EX_CONFIG
    from macf.voice.speech.backends import KokoroEngine, PipeWireOut
    try:
        engine = KokoroEngine(models_dir(home) / "kokoro-v1.0.onnx", models_dir(home) / "voices-v1.0.bin")
    except RuntimeError as e:
        print(f"⚠️ MACF: voice: the speech worker can't start: {e}", file=sys.stderr)
        return EX_CONFIG
    lock_state = None
    if sys.platform.startswith("linux"):
        from macf.voice.capture.linux import LinuxLockState
        lock_state = LinuxLockState()
    worker = speech.SpeechWorker(
        home, engine, PipeWireOut(), settings=lambda: settings_for(home),
        recording=lambda: state.recording(home),
        screen_locked=lambda: lock_state is None or lock_state.state() != "unlocked")
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
    beat = lambda: None  # noqa: E731 - replaced below when the daemon asks for liveness
    interval = float(os.environ.get("MACF_PD_LIVENESS_S") or 0)
    heartbeat = None
    if interval:
        from macf.pd.interface import agent_card
        from macf.pd.liveness import Heartbeat
        heartbeat = Heartbeat(agent_card(home), os.environ.get("MACF_PD_UNIT", "speech"), interval).start()
        beat = heartbeat.tick
    try:
        return speech.run(worker, speech.WorkerLock(speech.lock_path()), stopping=lambda: bool(stopping), beat=beat)
    finally:
        if heartbeat is not None:
            heartbeat.stop()


if __name__ == "__main__":
    sys.exit(main())
