"""The speech worker: one per system, playing every agent's queued speech in order, a sentence at a
time (MIS-0008 R27 to R29, R33).

Messages wait in a spool folder under the agent's voice directory. The worker runs as a declared
unit and holds an exclusive lock, so a second worker never starts playing beside it (R28). While a
message plays it keeps the speaking mark fresh, so the capture unit never wakes on it (R27). Before
each sentence it waits while the capture unit is recording, so the agent never talks over the
operator or into a recording (R29). While the screen is locked and the voice section says silent,
a message is dropped unspoken, and its text stays on screen (R33).
"""
from __future__ import annotations

import fcntl
import json

import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from macf.voice import state
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from macf.voice.speech.backends import AudioOut, SpeechEngine
from macf.voice.speech import cut
from macf.voice.speech.text import clean, sentences

#: The longest the worker holds a sentence for a recording, before it says so and drops the message.
RECORDING_WAIT_S = 330.0


def queue_dir(home: Path) -> Path:
    return state.voice_dir(home) / "speech" / "queue"


def pronounce_path(home: Path) -> Path:
    return state.voice_dir(home) / "speech" / "pronounce.json"


def enqueue(home: Path, text: str, overrides: Optional[dict] = None) -> Path:
    """Queue one message and mark the agent speaking at once, before the engine has even loaded."""
    q = queue_dir(home)
    q.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns()}.json"
    tmp = q / (name + ".tmp")
    tmp.write_text(json.dumps({"text": text, **(overrides or {})}))
    tmp.replace(q / name)
    state.speaking_path(home).touch()
    return q / name


def stop(home: Path) -> int:
    """Drop every queued message; the worker stops the sentence playing within a twentieth of a second."""
    dropped = 0
    for item in queue_dir(home).glob("*.json"):
        item.unlink(missing_ok=True)
        dropped += 1
    return dropped


def accent_path(home: Path) -> Path:
    """Respellings that give the voice an accent: kept apart from the plain ones so they can be switched off."""
    return state.voice_dir(home) / "speech" / "accent.json"


def accent_off_path(home: Path) -> Path:
    return state.voice_dir(home) / "speech" / "accent_off"


def accent_on(home: Path) -> bool:
    """Whether the accent respellings are applied; on until the operator switches them off."""
    return not accent_off_path(home).exists()


def set_accent(home: Path, on: bool) -> None:
    path = accent_off_path(home)
    if on:
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def _table(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        table = json.loads(path.read_text())
    except ValueError as e:
        print(f"⚠️ MACF: voice: {path} is not readable JSON, so its words are not respelled: {e}", file=sys.stderr)
        return {}
    return {str(k): str(v) for k, v in table.items()}


def pronunciations(home: Path, accent: Optional[bool] = None) -> Dict[str, str]:
    """The respellings to speak with: the plain ones, and over them the accent's while it is on."""
    table = _table(pronounce_path(home))
    if accent_on(home) if accent is None else accent:
        table.update(_table(accent_path(home)))
    return table


class WorkerLock:
    """The one-worker lock (R28): held for the worker's life, refused to a second worker."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "w")

    def acquire(self) -> bool:
        try:
            fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    def release(self) -> None:
        fcntl.flock(self._file, fcntl.LOCK_UN)
        self._file.close()


class PlaybackLock:
    """One playback lock per system (R28 as revised): an agent's worker holds it while one message plays,
    so two agents never speak at once and neither is shut out for the other's whole run."""

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            from macf.pd.names import runtime_dir
            path = runtime_dir() / "speech-playback.lock"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a")

    def acquire(self, wait_s: float = 0.0, still_wanted: Callable[[], bool] = lambda: True,
                poll_s: float = 0.05) -> bool:
        """Take the lock, waiting up to ``wait_s`` while ``still_wanted()``; False if not taken."""
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                if time.monotonic() >= deadline or not still_wanted():
                    return False
                time.sleep(poll_s)

    def release(self) -> None:
        fcntl.flock(self._file, fcntl.LOCK_UN)


#: How long a message waits for another agent's speech to finish before it is dropped, said in the log.
PLAYBACK_WAIT_S = 300.0


class SpeechWorker:
    def __init__(self, home: Path, engine: "SpeechEngine", out: "AudioOut", settings: Callable[[], object],
                 recording: Callable[[], bool], screen_locked: Callable[[], bool],
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 log: Callable[[str], None] = lambda s: print(f"🔊 MACF: voice: {s}", file=sys.stderr)):
        self.home, self.engine, self.out = Path(home), engine, out
        self._settings, self._recording, self._locked = settings, recording, screen_locked
        self.sleep, self.clock, self.log = sleep, clock, log
        self.played = 0
        self.playback: Optional[PlaybackLock] = None  # the system's, set by run(); None in a lone worker

    def _mark(self) -> None:
        state._touch(state.speaking_path(self.home), state.host_speaking_path())

    def _wait_for_the_microphone(self) -> bool:
        """Hold while the capture unit records (R29). False if it outlasted the wait."""
        deadline = self.clock() + RECORDING_WAIT_S
        while self._recording():
            if self.clock() >= deadline:
                return False
            self._mark()
            self.sleep(0.2)
        return True

    def _play_unless_recording(self, spoken, item: Path) -> Optional[tuple]:
        """Play one sentence, stopping it the moment a recording opens, or the moment ``voice speak
        --stop`` empties the queue: an operator who presses a key while the agent talks is heard, not
        talked over (R29), and a stop is immediate. Returns None when it played to the end, else why it
        was cut (``recording`` or ``stop``) and how many seconds had played."""
        done = threading.Event()
        cut: list = []
        started = self.clock()

        def watch():
            while not done.is_set():
                recording = self._recording()
                if recording or not item.exists():
                    cut.append(("recording" if recording else "stop", self.clock() - started))
                    self.out.stop()
                    return
                done.wait(0.05)

        watcher = threading.Thread(target=watch, name="speech-recording-watch", daemon=True)
        watcher.start()
        try:
            self.out.play(spoken)
        finally:
            done.set()
            watcher.join()
        return cut[0] if cut else None

    def take(self) -> bool:
        """Speak the oldest queued message, if any. Returns whether there was one."""
        items = sorted(queue_dir(self.home).glob("*.json"))
        if not items:
            return False
        item = items[0]
        try:
            job = json.loads(item.read_text())
        except (OSError, ValueError) as e:
            self.log(f"a queued message can't be read, so it is dropped: {e}")
            item.unlink(missing_ok=True)
            return True
        conf = self._settings()
        if conf.while_locked == "silent" and self._locked():
            self.log("the screen is locked and the voice section says silent: a message dropped unspoken")
            item.unlink(missing_ok=True)
            return True
        if self.playback is not None:
            if not self.playback.acquire(PLAYBACK_WAIT_S, still_wanted=item.exists):
                if item.exists():
                    self.log(f"another agent spoke for {PLAYBACK_WAIT_S:g} s; a message was dropped unspoken")
                    item.unlink(missing_ok=True)
                return True
            try:
                return self._speak(item, job, conf)
            finally:
                self.playback.release()
        return self._speak(item, job, conf)

    def _speak(self, item: Path, job: dict, conf) -> bool:
        voice, speed = job.get("voice", conf.voice), float(job.get("speed", conf.speed))
        said = list(sentences(clean(job.get("text", ""), pronunciations(self.home))))
        for index, sentence in enumerate(said):
            self._mark()
            if not item.exists():
                break                        # stopped: the queue was emptied
            spoken = self.engine.say(sentence, voice, speed, conf.lang)
            if not self._wait_for_the_microphone():
                self.log(f"the microphone stayed open {RECORDING_WAIT_S:g} s; the rest of a message was dropped")
                break
            if not item.exists():
                break
            self._mark()
            stopped = self._play_unless_recording(spoken, item)
            if stopped is not None:
                why, played_s = stopped
                self.log(f"a {why} cut the speech: the sentence stopped, the rest dropped")
                if why == "recording":
                    # R55: the agent learns which of its words the operator heard before the key cut it.
                    cut.record(self.home, said[:index], sentence, played_s, spoken.duration_s, said[index + 1:],
                               word_ends=spoken.word_ends, why=why)
                break
            self.played += 1
            self._mark()
        item.unlink(missing_ok=True)
        self._mark()
        return True


def run(worker: SpeechWorker, lock: WorkerLock, stopping: Callable[[], bool], beat: Callable[[], None]) -> int:
    """The unit's loop: take the lock or exit, then speak each message as it arrives."""
    if not lock.acquire():
        print("⚠️ MACF: voice: this agent's speech worker is already running (one per agent; the system's "
              "playback lock keeps agents from speaking at once, MIS-0008 R28)", file=sys.stderr)
        return 75
    if worker.playback is None:
        worker.playback = PlaybackLock()
    try:
        while not stopping():
            beat()
            if not worker.take():
                worker.sleep(0.2)
    finally:
        lock.release()
    return 0


def lock_path(home: Path) -> Path:
    """This agent's one-worker lock, in its own voice folder: each agent on a system runs its own
    worker, and the system's PlaybackLock keeps them from speaking at once (R28 as revised)."""
    return state.voice_dir(home) / "speech-worker.lock"


__all__ = ["SpeechWorker", "WorkerLock", "enqueue", "lock_path", "run", "stop"]
