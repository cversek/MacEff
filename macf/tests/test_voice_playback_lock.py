"""Several agents speaking on one system (MIS-0008 R27 to R29 as revised): each runs its own speech
worker, one playback lock per system serializes them, and speech or recording anywhere on the system is
seen by every agent's capture unit and speech worker."""
import threading
import time

import pytest

from macf.voice import state
from macf.voice.speech import worker as speech
from tests.test_voice_speech import FakeOut, make_worker


@pytest.fixture(autouse=True)
def own_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))


def test_each_agent_runs_its_own_worker(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert speech.lock_path(a) != speech.lock_path(b)
    first, second = speech.WorkerLock(speech.lock_path(a)), speech.WorkerLock(speech.lock_path(b))
    assert first.acquire() and second.acquire()  # two agents' workers run side by side
    first.release()
    second.release()


def test_playback_lock_serializes_agents(tmp_path):
    """R28 as revised: while one agent's message plays, another agent's waits, then plays."""
    a, b = tmp_path / "a", tmp_path / "b"
    order = []
    out_a = FakeOut(seconds=0.3, during=lambda: order.append("a starts"))
    out_b = FakeOut(during=lambda: order.append("b starts"))
    worker_a, _ = make_worker(a, out=out_a)
    worker_b, _ = make_worker(b, out=out_b)
    worker_a.playback = worker_b.playback = speech.PlaybackLock()
    speech.enqueue(a, "Agent A speaking.")
    speech.enqueue(b, "Agent B speaking.")
    runner = threading.Thread(target=worker_a.take)
    runner.start()
    time.sleep(0.05)
    worker_b.take()
    runner.join()
    assert order == ["a starts", "b starts"]  # B never started while A played


def test_a_stopped_message_stops_waiting_for_the_playback_lock(tmp_path):
    held = speech.PlaybackLock()
    assert held.acquire(wait_s=0)
    worker, engine = make_worker(tmp_path / "b")
    worker.playback = speech.PlaybackLock()
    item = speech.enqueue(tmp_path / "b", "Never said.")
    threading.Timer(0.1, lambda: item.unlink()).start()
    worker.take()
    assert engine.said == []
    held.release()


def test_speech_and_recording_anywhere_on_the_system_are_seen_by_every_agent(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    worker_a, _ = make_worker(a)
    worker_a._mark()
    assert state.speaking(b)  # R27: B's capture unit won't wake on A's speech
    state.mark_recording(a)
    assert state.recording(b)  # R29: B's speech holds while A's microphone records
