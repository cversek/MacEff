"""``macf_tools voice speak``, ``voice show`` and ``voice select samples|choose`` (MIS-0008 6.6).

``speak`` queues text for the speech worker unit and returns at once. ``select`` is driven by the
``maceff-voice-select`` skill under the ``voice_generation`` policy: traits agreed with the operator
first (R31), samples next, the choice recorded with its traits (R30).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from macf.voice.speech import select
from macf.voice.speech import worker as speech


def add_parsers(voice_sub) -> None:
    speak = voice_sub.add_parser("speak", help="say text aloud through the speech worker, without waiting")
    speak.add_argument("text", nargs="*", help="what to say; stdin when omitted")
    speak.add_argument("--stop", action="store_true", help="stop talking and drop the queue")
    speak.add_argument("--voice", help="a voice or blend for this message only")
    speak.add_argument("--speed", type=float, help="a speed for this message only")
    speak.add_argument("--say-as", nargs="+", metavar="WORD=SPELLING", help="say WORD as SPELLING from now on")
    speak.add_argument("--unsay", nargs="+", metavar="WORD", help="stop respelling WORD")
    speak.add_argument("--accent", action="store_true",
                       help="with --say-as or --unsay: change the accent's respellings, which `voice accent off` silences")
    speak.set_defaults(func=cmd_speak)
    accent = voice_sub.add_parser("accent", help="switch the voice's accent respellings on or off, or say which")
    accent.add_argument("state", nargs="?", choices=("on", "off"))
    accent.set_defaults(func=cmd_accent)
    voice_sub.add_parser("show", help="the agent's voice settings and the traits behind them").set_defaults(func=cmd_show)
    sel = voice_sub.add_parser("select", help="choose the agent's voice with the operator")
    sel_sub = sel.add_subparsers(dest="voice_select_cmd")
    samples = sel_sub.add_parser("samples", help="speak candidate voices made from the agreed traits")
    samples.add_argument("--traits", nargs="+", required=True, help="the traits the operator agreed, a few words each")
    samples.add_argument("--count", type=int, default=4)
    samples.add_argument("--line", default=select.LINE, help="what every candidate says")
    samples.set_defaults(func=cmd_samples)
    choose = sel_sub.add_parser("choose", help="record the candidate the operator chose, with its traits")
    choose.add_argument("number", type=int)
    choose.set_defaults(func=cmd_choose)
    models = voice_sub.add_parser("models", help="the speech weights the MLX engine needs: what is cached, and fetching them")
    models_sub = models.add_subparsers(dest="voice_models_cmd")
    for verb, func, text in (("status", cmd_models_status, "which weight files the engine needs and which are cached"),
                             ("fetch", cmd_models_fetch, "fetch the missing weight files you approve, one by one")):
        p = models_sub.add_parser(verb, help=text)
        p.add_argument("--voice", action="append", default=[], metavar="NAME",
                       help="a voice to have the weights for; repeat for several (default: the agent's own)")
        p.set_defaults(func=func)
        if verb == "fetch":
            p.add_argument("--approve", action="append", default=[], metavar="FILE",
                           help="a file from the list, fetched; with none and no terminal, nothing is fetched")


def _home() -> Path:
    from macf.utils.paths import find_agent_home
    return find_agent_home()


def _worker_running() -> bool:
    """Whether a speech worker holds the lock: if this process can take it, none does."""
    lock = speech.WorkerLock(speech.lock_path())
    free = lock.acquire()
    lock.release()
    return not free


def cmd_speak(args) -> int:
    home = _home()
    if args.stop:
        print(f"stopped; {speech.stop(home)} queued message(s) dropped")
        return 0
    if args.say_as or args.unsay:
        path = speech.accent_path(home) if getattr(args, "accent", False) else speech.pronounce_path(home)
        table = speech._table(path)
        for pair in args.say_as or []:
            word, sep, spelling = pair.partition("=")
            if not sep or not word or not spelling:
                print(f"--say-as wants WORD=SPELLING, not {pair!r}", file=sys.stderr)
                return 2
            table[word] = spelling
        for word in args.unsay or []:
            if table.pop(word, None) is None:
                print(f"no respelling for {word!r}", file=sys.stderr)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n")
        print(f"{len(table)} respelling(s) in {path}")
        if not args.text:
            return 0
    text = " ".join(args.text) if args.text else ("" if sys.stdin.isatty() else sys.stdin.read())
    if not text.strip():
        print("nothing to say", file=sys.stderr)
        return 2
    # Speech nobody can play now would be spoken whenever a worker next starts, out of its time:
    # so with no worker, nothing is queued.
    if not _worker_running():
        print("not spoken: no speech worker is running (declare the speech unit: python -m macf.voice.speech)",
              file=sys.stderr)
        return 1
    overrides = {k: v for k, v in (("voice", args.voice), ("speed", args.speed)) if v is not None}
    speech.enqueue(home, text, overrides)
    return 0


def cmd_accent(args) -> int:
    home = _home()
    if args.state:
        speech.set_accent(home, args.state == "on")
    count = len(speech._table(speech.accent_path(home)))
    print(f"accent {'on' if speech.accent_on(home) else 'off'}: {count} respelling(s) in {speech.accent_path(home)}")
    return 0


def cmd_show(args) -> int:
    from macf.voice.speech.__main__ import settings_for
    settings = settings_for(_home())
    print(json.dumps(settings.model_dump(), indent=1))
    if not settings.traits:
        print("no voice chosen yet: these are the defaults (macf_tools voice select)")
    return 0


def cmd_samples(args) -> int:
    home = _home()
    if not _worker_running():
        print("no speech worker is running to play samples; nothing was made", file=sys.stderr)
        return 1
    found = select.candidates(args.traits, args.count)
    select.keep_candidates(home, args.traits, found)
    for c in found:
        speech.enqueue(home, f"Candidate {c.number}. {args.line}", {"voice": c.voice, "speed": c.speed})
        print(f"candidate {c.number}: voice {c.voice}, speed {c.speed}")
    return 0


def cmd_choose(args) -> int:
    try:
        chosen = select.record_choice(_home(), args.number)
    except (select.ChoiceRefused, ValueError, OSError) as e:
        print(f"refused: {e}")
        return 1
    print(f"recorded in the voice section: voice {chosen['voice']}, speed {chosen['speed']}, "
          f"traits {', '.join(chosen['traits'])}")
    return 0


def _voices(args):
    """The voices to have weights for: those named, else the agent's own, else the one the engine starts with."""
    from macf.voice.speech import weights
    if args.voice:
        return args.voice
    try:
        from macf.voice.speech.__main__ import settings_for
        return weights.voice_names(settings_for(_home()).voice)
    except Exception as e:  # noqa: BLE001 - an unreadable declaration shouldn't stop a fetch; say it and take the default
        print(f"⚠️ MACF: voice: the agent's voice couldn't be read ({type(e).__name__}: {e}); "
              f"listing the weights for {weights.WARMUP_VOICE}", file=sys.stderr)
        return [weights.WARMUP_VOICE]


def _print_files(files) -> None:
    from macf.voice.speech import weights
    for f in files:
        print(f"  {'cached ' if f.cached else 'missing'}  {f.name}  ({weights.megabytes(f.size)})")


def cmd_models_status(args) -> int:
    from macf.voice.speech import weights
    try:
        files = weights.listing(weights.wanted(_voices(args)))
    except weights.WeightsMissing as e:
        print(str(e), file=sys.stderr)
        return 2
    print(f"speech weights from {weights.REPO}:")
    _print_files(files)
    return 0 if all(f.cached for f in files) else 1


def cmd_models_fetch(args) -> int:
    from macf.voice.speech import weights
    try:
        files = weights.listing(weights.wanted(_voices(args)))
    except weights.WeightsMissing as e:
        print(str(e), file=sys.stderr)
        return 2
    missing = [f for f in files if not f.cached]
    print(f"speech weights from {weights.REPO}:")
    _print_files(files)
    if not missing:
        print("everything the engine needs is cached")
        return 0
    names = {f.name for f in missing}
    unknown = [a for a in args.approve if a not in names]
    if unknown:
        print(f"not a file to fetch: {', '.join(unknown)}; the missing ones are listed above", file=sys.stderr)
        return 2
    approved = list(args.approve)
    if not approved and sys.stdin.isatty():
        approved = weights.approve_interactively(missing)
    if not approved:
        print("nothing fetched: approve each file you want with --approve FILE (the operator's yes, file by file)",
              file=sys.stderr)
        return 3
    try:
        for path in weights.fetch([f for f in missing if f.name in approved]):
            print(f"fetched {path}")
    except weights.WeightsMissing as e:
        print(str(e), file=sys.stderr)
        return 4
    left = [n for n in names if n not in approved]
    if left:
        print(f"still missing: {', '.join(sorted(left))}", file=sys.stderr)
        return 3
    return 0
