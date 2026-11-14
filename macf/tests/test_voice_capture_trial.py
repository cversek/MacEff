"""``voice capture trial``: a live try of a wake model that prints what it heard and delivers nothing."""
import numpy as np
import pytest

from macf.voice import state
from macf.voice.capture import trial
from macf.voice.capture.backends import WakeDetector
from macf.voice.capture.unit import Utterance


class Scripted(WakeDetector):
    def __init__(self, *scores):
        self.scores = list(scores)
        self.resets = 0

    def score(self, frame):
        return self.scores.pop(0)

    def reset(self):
        self.resets += 1


def scored(detector, n):
    frame = np.zeros(1280, np.int16)
    return [detector.score(frame) for _ in range(n)]


def test_a_near_fire_prints_its_peak_and_whether_it_crossed_the_bar():
    """A miss shows how close it came; a fire says so; noise below the near mark prints nothing."""
    said = []
    d = trial.PeakReporting(Scripted(0.1, 0.5, 0.88, 0.4, 0.0, 0.2, 0.97, 0.99, 0.1, 0.25), "yo tom", 0.95, said.append)
    assert scored(d, 10) == [0.1, 0.5, 0.88, 0.4, 0.0, 0.2, 0.97, 0.99, 0.1, 0.25]
    assert said == ["yo tom peaked 0.880 (bar 0.95): under the bar", "yo tom peaked 0.990 (bar 0.95): fired"]


def test_a_reset_mid_peak_reports_it_and_resets_the_model():
    """A wake resets the detectors while the score is still high; that peak is still printed."""
    said, inner = [], Scripted(0.6, 0.99)
    d = trial.PeakReporting(inner, "hey ada", 0.95, said.append)
    scored(d, 2)
    d.reset()
    assert said == ["hey ada peaked 0.990 (bar 0.95): fired"] and inner.resets == 1


class StopsAfter:
    """A unit that runs ``n`` ticks, then raises ``error`` or asks to stop."""

    def __init__(self, home, n, stopping, error=None):
        self.home, self.n, self.stopping, self.error = home, n, stopping, error
        self.seen_listening, self.shut = [], False

    def tick(self):
        self.seen_listening.append(state.listening_on(self.home))
        self.n -= 1
        if self.n <= 0:
            if self.error:
                raise self.error
            self.stopping.append(True)

    def shutdown(self):
        self.shut = True


@pytest.mark.parametrize("was_on", [True, False])
def test_listening_is_off_during_the_trial_and_restored_after(tmp_path, was_on):
    """The agent's own capture unit mustn't take the trial's words; afterwards listening is as it was."""
    state.set_listening(tmp_path, was_on)
    stopping = []
    unit = StopsAfter(tmp_path, 3, stopping)
    trial.run(unit, tmp_path, out=lambda s: None, stopping=stopping)
    assert unit.seen_listening == [False, False, False]
    assert state.listening_on(tmp_path) is was_on and unit.shut


def test_listening_is_restored_when_the_trial_fails(tmp_path):
    state.set_listening(tmp_path, True)
    stopping = []
    unit = StopsAfter(tmp_path, 2, stopping, error=RuntimeError("the microphone stream ended"))
    with pytest.raises(RuntimeError):
        trial.run(unit, tmp_path, out=lambda s: None, stopping=stopping)
    assert state.listening_on(tmp_path) and unit.shut


def test_each_utterance_is_printed_with_why_it_ended_and_counted():
    said, tally = [], trial.Tally()
    deliver = trial.printer(tally, said.append)
    deliver(Utterance(trigger="wake_phrase", spoken_at=1794600000.0, screen="unlocked", text="check the queue",
                      agent="Tester_abc123", ended="send"))
    log = trial.logger(tally, said.append)
    log("wake for Tester_abc123")
    assert (tally.utterances, tally.wakes) == (1, 1)
    assert "ended: send" in said[0] and "check the queue" in said[0] and "Tester_abc123" in said[0]


def test_a_trial_needs_a_model_for_each_phrase(tmp_path, monkeypatch):
    import macf.pd.interface as interface
    import macf.pd.core as core
    monkeypatch.setattr(interface, "agent_card", lambda home: "Tester_abc123")
    monkeypatch.setattr(core, "load_declaration", lambda home, card: type("D", (), {"voice": None})())
    with pytest.raises(ValueError, match="no wake phrase"):
        trial.build(tmp_path, [], [], None, out=lambda s: None)
    with pytest.raises(ValueError, match="one --model for each --phrase"):
        trial.build(tmp_path, ["yo tom", "hey ada"], ["a.npz"], None, out=lambda s: None)
