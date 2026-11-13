"""``macf_tools voice wake define|record|train|test|status``: from a chosen phrase to a measured wake
model (MIS-0008 6.5). The ``maceff-voice-wake-training`` skill coaches an operator through it; the
``voice_input`` policy says how a model is measured and what a wake may authorize (nothing).

``record`` opens the microphone, and only because the operator ran it: it counts down, says what to
say, and keeps each clip under the agent's home as training data.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

from typing import TYPE_CHECKING

from macf.voice.wake import KINDS, PhraseRefused

if TYPE_CHECKING:
    from macf.voice.wake.dataset import WakeSet

#: How long each kind of clip runs, in seconds.
SECONDS = {"phrase": 2.5, "near_miss": 2.5, "other_phrase": 2.5, "speech": 30.0, "room": 60.0}
PROMPTS = {
    "phrase": "say the wake phrase, as you would to call the agent",
    "near_miss": "say something close to the phrase that isn't it (a near rhyme, half of it, another name)",
    "other_phrase": "say another agent's wake phrase on this machine",
    "speech": "talk or read aloud normally, with pauses",
    "room": "stay quiet: this records the room as it usually sounds",
}


def add_parsers(voice_sub) -> None:
    wake = voice_sub.add_parser("wake", help="define, record, train and measure the agent's wake phrase")
    sub = wake.add_subparsers(dest="voice_wake_cmd")
    define = sub.add_parser("define", help="choose the wake phrase; refused if it can't work")
    define.add_argument("phrase")
    define.set_defaults(func=cmd_define)
    record = sub.add_parser("record", help="record clips of one kind from the microphone")
    record.add_argument("kind", choices=KINDS)
    record.add_argument("--count", type=int, default=5)
    record.add_argument("--conditions", default="", help="what was different: mic, room, voice (e.g. 'tired, fan on')")
    record.add_argument("--phrase", help="the phrase; default: the voice section's")
    record.set_defaults(func=cmd_record)
    for name, func, text in (("train", cmd_train, "train the model and measure it on the held-out clips"),
                             ("test", cmd_test, "measure the model again on the held-out clips"),
                             ("status", cmd_status, "the clips kept and the model's numbers")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--phrase", help="the phrase; default: the voice section's")
        p.set_defaults(func=func)


def _home() -> Path:
    from macf.utils.paths import find_agent_home
    return find_agent_home()


def _wake_set(phrase: Optional[str]) -> "WakeSet":
    from macf.voice.wake.dataset import WakeSet
    home = _home()
    if not phrase:
        from macf.pd.core import load_declaration
        from macf.pd.interface import agent_card
        voice = load_declaration(home, agent_card(home)).voice
        phrase = voice.wake_phrase if voice else None
    if not phrase:
        raise PhraseRefused("no phrase given and the voice section names none; pass --phrase, or define one first")
    return WakeSet(home, phrase)


def cmd_define(args) -> int:
    from macf.voice.wake.dataset import WakeSet
    try:
        wake = WakeSet(_home(), args.phrase)
    except PhraseRefused as e:
        print(f"refused: {e}")
        return 1
    wake.define()
    rel = wake.model_path.relative_to(_home())
    print(f"wake phrase {wake.phrase!r} defined at {wake.root}")
    print("Next: record clips (voice wake record phrase), train, then declare in the voice section:")
    print(json.dumps({"wake_phrase": wake.phrase, "wake_model": str(rel)}, indent=2))
    return 0


def cmd_record(args) -> int:
    from macf.voice.capture.backends import FRAME, RATE
    from macf.voice.capture.linux import PipeWireAudio
    import numpy as np
    try:
        wake = _wake_set(args.phrase)
    except PhraseRefused as e:
        print(f"refused: {e}")
        return 1
    seconds = SECONDS[args.kind]
    mic = PipeWireAudio()
    print(f"Recording {args.count} {args.kind} clip(s) of {seconds:g} s for {wake.phrase!r}: {PROMPTS[args.kind]}.")
    for n in range(1, args.count + 1):
        for left in (3, 2, 1):
            print(f"  clip {n}: {left}…", end="\r", flush=True)
            time.sleep(1)
        print(f"  clip {n}: now                ", flush=True)
        mic.open()
        try:
            frames = [mic.read() for _ in range(int(seconds * RATE / FRAME))]
        finally:
            mic.close()
        clip = wake.add(args.kind, np.concatenate(frames), args.conditions)
        print(f"  kept as {clip.split}")
    counts = wake.counts()[args.kind]
    print(f"{args.kind}: {counts['train']} to train on, {counts['test']} held out")
    return 0


def _summary(report: dict) -> str:
    held = report.get("held_out", {})
    return (f"missed {report.get('misses')} of {held.get('phrase', 0)} held-out phrases; "
            f"{report.get('false_alarms_per_hour')} false alarms per hour over {report.get('background_seconds')} s "
            f"of held-out background; near misses fired {report.get('near_miss_fires')} of {held.get('near_miss', 0)}; "
            f"other agents' phrases fired {report.get('other_phrase_fires')} of {held.get('other_phrase', 0)}; "
            f"conditions: {', '.join(report.get('conditions') or []) or 'none recorded'}")


def cmd_train(args) -> int:
    from macf.voice.wake.train import NotEnoughClips, openwakeword_embed, train
    try:
        wake = _wake_set(args.phrase)
        model = train(wake, openwakeword_embed())
    except (PhraseRefused, NotEnoughClips, RuntimeError) as e:
        print(f"refused: {e}")
        return 1
    model.save(wake.model_path)
    print(f"trained {wake.model_path}, threshold {model.threshold:.2f}")
    print(_summary(model.report))
    return 0


def cmd_test(args) -> int:
    import numpy as np
    from macf.voice.wake.model import WakeModel
    from macf.voice.wake.train import measure, openwakeword_embed
    try:
        wake = _wake_set(args.phrase)
        model = WakeModel.load(wake.model_path)
    except (PhraseRefused, OSError, ValueError) as e:
        print(f"refused: {e}")
        return 1
    trained_on = model.report.get("trained_on", [])
    model.report = {"trained_on": trained_on, **measure(wake, model, openwakeword_embed(), np.random.default_rng(7))}
    model.save(wake.model_path)
    print(_summary(model.report))
    return 0


def cmd_status(args) -> int:
    try:
        wake = _wake_set(args.phrase)
    except PhraseRefused as e:
        print(f"refused: {e}")
        return 1
    print(f"wake phrase {wake.phrase!r}")
    for kind, n in wake.counts().items():
        print(f"  {kind}: {n['train']} to train on, {n['test']} held out")
    if not wake.model_path.exists():
        print("  no model trained yet")
        return 0
    from macf.voice.wake.model import WakeModel
    try:
        model = WakeModel.load(wake.model_path)
    except (OSError, ValueError) as e:
        print(f"  the model can't be read: {e}", file=sys.stderr)
        return 1
    age_h = (time.time() - model.trained_at) / 3600
    print(f"  model trained {age_h:.1f} h ago, threshold {model.threshold:.2f}")
    print(f"  {_summary(model.report)}")
    return 0
