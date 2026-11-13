"""The speech worker (MIS-0008 R27 to R29, R33) and what it says aloud."""
import threading
import time

import numpy as np

from macf.pd.interface import SpeechSettings
from macf.voice import state
from macf.voice.speech import worker as speech
from macf.voice.speech.backends import AudioOut, SpeechEngine, Spoken, check_audio_out
from macf.voice.speech.text import clean, respell, sentences


class FakeEngine(SpeechEngine):
    def __init__(self):
        self.said = []

    def say(self, sentence, voice, speed, lang):
        self.said.append((sentence, voice, speed))
        return Spoken(np.zeros(160, np.float32), 16000)

    def voices(self):
        return ["am_michael"]


class FakeOut(AudioOut):
    """Plays for ``seconds`` unless stopped, keeping what it played and whether it was cut."""

    def __init__(self, seconds=0.0, during=None):
        self.seconds, self.during = seconds, during
        self.played, self.stopped = [], threading.Event()

    def play(self, spoken):
        self.stopped.clear()
        self.played.append(spoken)
        if self.during:
            self.during()
        self.stopped.wait(self.seconds)

    def stop(self):
        self.stopped.set()


def make_worker(home, out=None, recording=lambda: False, locked=lambda: False, **settings):
    engine = FakeEngine()
    w = speech.SpeechWorker(home, engine, out or FakeOut(), settings=lambda: SpeechSettings(**settings),
                            recording=recording, screen_locked=locked, sleep=lambda s: time.sleep(0.001))
    return w, engine


def test_one_worker_serializes_agents(tmp_path):
    """R28: one worker holds the lock; a second can't start playing beside it, and runs once it's free."""
    first = speech.WorkerLock(tmp_path / "speech.lock")
    second = speech.WorkerLock(tmp_path / "speech.lock")
    assert first.acquire() and not second.acquire()
    w, _ = make_worker(tmp_path)
    assert speech.run(w, second, stopping=lambda: True, beat=lambda: None) == 75
    first.release()
    assert second.acquire()
    second.release()


def test_messages_play_in_order_sentence_by_sentence(tmp_path):
    w, engine = make_worker(tmp_path)
    speech.enqueue(tmp_path, "First thing. Second thing!")
    speech.enqueue(tmp_path, "Third.")
    while w.take():
        pass
    assert [call[0] for call in engine.said] == ["First thing.", "Second thing!", "Third."]


def test_no_playback_while_microphone_open(tmp_path, monkeypatch):
    """R29: a sentence waits while the capture unit records, and plays once it stops; one already
    playing when a recording opens is stopped, and the rest of its message dropped."""
    monkeypatch.setattr(speech, "RECORDING_WAIT_S", 1.0)   # a defect fails in a second, not in 330
    open_for = [5]

    def recording():
        open_for[0] -= 1
        return open_for[0] > 0

    out = FakeOut()
    w, _ = make_worker(tmp_path, out=out, recording=recording)
    speech.enqueue(tmp_path, "Wait for me.")
    w.take()
    assert len(out.played) == 1 and open_for[0] <= 0, "it played before the recording ended"

    rec = [False]
    out = FakeOut(seconds=5.0, during=lambda: threading.Timer(0.05, lambda: rec.__setitem__(0, True)).start())
    w, engine = make_worker(tmp_path, out=out, recording=lambda: rec[0])
    speech.enqueue(tmp_path, "A long first sentence. A second one never heard.")
    started = time.monotonic()
    w.take()
    assert time.monotonic() - started < 2.0, "the playing sentence wasn't stopped when a recording opened"
    assert len(out.played) == 1 and [call[0] for call in engine.said] == ["A long first sentence."]


def test_the_agent_is_marked_speaking_from_queue_to_last_sentence(tmp_path):
    """R27's input: queued speech marks the agent speaking at once, before the engine has loaded."""
    speech.enqueue(tmp_path, "Hello.")
    assert state.speaking(tmp_path)


def test_a_locked_screen_with_silent_declared_speaks_nothing(tmp_path):
    """R33: while locked, a voice section that says silent drops the message unspoken."""
    out = FakeOut()
    w, engine = make_worker(tmp_path, out=out, locked=lambda: True, while_locked="silent")
    speech.enqueue(tmp_path, "Nobody should hear this.")
    assert w.take() and out.played == [] and engine.said == []
    w, _ = make_worker(tmp_path, out=out, locked=lambda: True)
    speech.enqueue(tmp_path, "The default speaks.")
    w.take()
    assert len(out.played) == 1


def test_stop_drops_the_queue(tmp_path):
    speech.enqueue(tmp_path, "One.")
    speech.enqueue(tmp_path, "Two.")
    assert speech.stop(tmp_path) == 2 and not any(speech.queue_dir(tmp_path).glob("*.json"))


def test_text_is_made_fit_to_hear():
    said = clean("See `cfg` in **bold**: ```rm -rf /``` and [the PR](https://x.y/1) or https://a.b/c", {})
    assert "rm -rf" not in said and "code block omitted" in said and "the PR" in said and "a link" in said
    assert "`" not in said and "*" not in said
    assert sentences("One. Two!\nThree") == ["One.", "Two!", "Three"]


def test_a_word_is_respelled_only_standing_alone():
    table = {"Ira": "Eyera"}
    assert respell("Ask Ira. Ira's review, MacEff-Ira and Irate.", table) == \
        "Ask Eyera. Eyera's review, MacEff-Ira and Irate."


def test_the_fake_audio_out_keeps_the_contract():
    check_audio_out(lambda: FakeOut(seconds=5.0))
