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


def test_agents_with_queued_messages_take_turns(tmp_path):
    """flock grants no order, so a worker that releases and takes the lock straight back could win every
    time; each release leaves a waiting worker its turn, and two agents' queues alternate."""
    a, b = tmp_path / "a", tmp_path / "b"
    order = []
    worker_a, _ = make_worker(a, out=FakeOut(seconds=0.15, during=lambda: order.append("a")))
    worker_b, _ = make_worker(b, out=FakeOut(seconds=0.15, during=lambda: order.append("b")))
    worker_a.playback, worker_b.playback = speech.PlaybackLock(), speech.PlaybackLock()
    for n in range(2):
        speech.enqueue(a, f"Agent A, message {n}.")
        speech.enqueue(b, f"Agent B, message {n}.")
    runners = [threading.Thread(target=lambda w=w: [None for _ in iter(w.take, False)])
               for w in (worker_a, worker_b)]
    for r in runners:
        r.start()
    for r in runners:
        r.join()
    assert order in (["a", "b", "a", "b"], ["b", "a", "b", "a"])


def test_a_message_dropped_for_another_agent_is_told_to_its_agent_once(tmp_path, monkeypatch):
    """A message dropped unspoken is told, as a cut is (R55): otherwise the agent believes it was heard."""
    from macf.voice.speech import cut
    monkeypatch.setattr(speech, "PLAYBACK_WAIT_S", 0.1)
    held = speech.PlaybackLock()
    assert held.acquire(wait_s=0)
    home = tmp_path / "b"
    worker, engine = make_worker(home)
    worker.playback = speech.PlaybackLock()
    speech.enqueue(home, "The board is ready.")
    worker.take()
    held.release()
    assert engine.said == []
    line = cut.prompt_line(home)
    assert "The board is ready." in line and "another agent" in line
    assert cut.prompt_line(home) == ""  # told once
