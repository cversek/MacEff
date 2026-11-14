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


def test_a_stop_cuts_the_sentence_playing(tmp_path):
    """voice speak --stop is immediate: the sentence playing stops, not only the ones after it."""
    out = FakeOut(seconds=5.0, during=lambda: threading.Timer(0.05, speech.stop, args=(tmp_path,)).start())
    w, engine = make_worker(tmp_path, out=out)
    speech.enqueue(tmp_path, "A long sentence. Never heard.")
    started = time.monotonic()
    w.take()
    assert time.monotonic() - started < 2.0 and [c[0] for c in engine.said] == ["A long sentence."]


# ---------------------------------------------------------------- R55: what the operator heard when a key cut the speech

from macf.voice.speech import cut as speech_cut  # noqa: E402


def test_the_words_heard_come_from_word_times_when_the_engine_has_them():
    heard, unheard, how = speech_cut.heard_in_sentence("one two three four", 0.9, 2.0, word_ends=(0.4, 0.8, 1.2, 1.6))
    assert (heard, unheard, how) == ("one two", "three four", "measured")


def test_without_word_times_the_words_heard_are_estimated_and_a_partial_word_is_not_heard():
    # 1.0 s of speech after the 0.12 s lead-in, four equal words: half played is two words heard.
    duration = speech_cut.LEAD_IN_S + 1.0 + speech_cut.LEAD_OUT_S
    heard, unheard, how = speech_cut.heard_in_sentence("aaa bbb ccc ddd", speech_cut.LEAD_IN_S + 0.5, duration)
    assert (heard, unheard, how) == ("aaa bbb", "ccc ddd", "estimated")
    heard = speech_cut.heard_in_sentence("aaa bbb ccc ddd", speech_cut.LEAD_IN_S + 0.45, duration).heard
    assert heard == "aaa", "a word still playing at the cut was counted as heard"
    assert speech_cut.heard_in_sentence("aaa bbb", 0.05, duration).heard == ""


def test_cut_speech_tells_agent_what_was_heard(tmp_path):
    """R55: a recording that cuts the agent's speech leaves a record of the sentences heard whole, the
    words heard of the one cut, and everything the operator didn't hear."""
    rec = [False]
    plays = [0]

    def during():
        plays[0] += 1
        if plays[0] == 2:                       # the second sentence: a key opens a recording
            threading.Timer(0.05, lambda: rec.__setitem__(0, True)).start()

    out = FakeOut(seconds=0.0, during=during)
    w, engine = make_worker(tmp_path, out=out, recording=lambda: rec[0])
    # Each sentence lasts two seconds, as real speech would. With the fake engine's hundredth of a
    # second, any cut past the lead-in counted the whole sentence heard: a slower macOS runner cut
    # later than that, and failed, which a cut delayed to 0.2 s reproduced here.
    engine.say = lambda sentence, voice, speed, lang: Spoken(np.zeros(32000, np.float32), 16000)
    out.seconds = 0.0

    def play(spoken, _orig=out.play):
        out.seconds = 5.0 if plays[0] >= 1 else 0.0
        _orig(spoken)
    out.play = play
    speech.enqueue(tmp_path, "Here is the plan. Then we deploy the fix tonight. Last words.")
    w.take()
    entry = speech_cut.take_untold(tmp_path)
    assert entry is not None and entry["why"] == "recording" and entry["how"] == "estimated"
    assert entry["heard"].startswith("Here is the plan.")
    assert entry["unheard"].endswith("Last words.") and "tonight" in entry["unheard"]
    assert speech_cut.take_untold(tmp_path) is None, "a cut was told twice"


def test_a_stop_is_not_a_cut_the_agent_is_told_about(tmp_path):
    """--stop is the agent's or operator's own silence, not a key cutting the agent off."""
    out = FakeOut(seconds=5.0, during=lambda: threading.Timer(0.05, lambda: speech.stop(tmp_path)).start())
    w, _ = make_worker(tmp_path, out=out)
    speech.enqueue(tmp_path, "A sentence that is stopped.")
    w.take()
    assert speech_cut.take_untold(tmp_path) is None


def test_a_stale_cut_is_not_told(tmp_path):
    speech_cut.record(tmp_path, [], "one two", 0.0, 1.0, [], now=1000.0)
    assert speech_cut.take_untold(tmp_path, now=1000.0 + speech_cut.TELL_WITHIN_S + 1) is None


def test_the_prompt_tells_a_cut_once(tmp_path):
    speech_cut.record(tmp_path, ["Heard whole."], "cut here now", 10.0, 1.0, ["Never said."])
    line = speech_cut.prompt_line(tmp_path)
    assert "Heard whole." in line and "Never said." in line and "measured" not in line
    assert speech_cut.prompt_line(tmp_path) == ""
