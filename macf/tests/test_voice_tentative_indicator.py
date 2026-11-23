"""The indicator shows at the wake model's fire, before the words check, and is withdrawn on a reject."""
from types import SimpleNamespace

from macf.voice.capture.unit import CaptureUnit


class Indicator:
    def __init__(self):
        self.calls = []

    def show(self, agent, mode):
        self.calls.append(("show", agent, mode))

    def hide(self):
        self.calls.append(("hide",))


def bare_unit():
    unit = CaptureUnit.__new__(CaptureUnit)  #only what the tentative indicator touches
    unit.indicator, unit._tentative, unit.log = Indicator(), False, lambda line: None
    return unit


def test_a_fire_shows_at_once_and_a_reject_withdraws_it():
    unit = bare_unit()
    agent = SimpleNamespace(b=SimpleNamespace(agent="Bez_bc8705"))
    unit._show_tentative(agent)
    unit._show_tentative(agent)  #a fire held over several frames shows once
    assert unit.indicator.calls == [("show", "Bez_bc8705", "wake_phrase")]
    unit._reject("hey jarvis 1.00 → no speech in the window: rejected", now=0.0)
    assert unit.indicator.calls[-1] == ("hide",) and not unit._tentative
    unit._reject("another reject", now=1.0)  #nothing shown: nothing hidden
    assert unit.indicator.calls.count(("hide",)) == 1
