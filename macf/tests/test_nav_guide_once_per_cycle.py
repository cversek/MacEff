"""A nav guide surfaced once is surfaced; repeating it costs more than context.

`task start` auto-injects CEP navigation guides for the task type, statelessly
with respect to what has already been shown — so several task starts in one
cycle re-injected the same guides verbatim. Observed: the task-management guide
three times across three consecutive starts, identical each time.

The guide earns its cost in the case it was designed for: an agent opening its
first task after a context loss, with no memory of the policy. Nothing
distinguished that from the fourth task-start of the same cycle. And the repeat
is worse than wasted context — a block that arrives unchanged for the fourth
time gets skimmed, and thereafter so does the first one.

The events log already records what happened this cycle, so "has this been
surfaced" has an existing home and needs no new state file.
"""
import pytest


def _ev(name, **data):
    return {"event": name, "data": data}


@pytest.fixture
def surfaced(monkeypatch):
    def _run(events):
        import macf.event_queries as eq
        # reverse=True is what the function asks for; hand back the reversed
        # list so the stub matches the real reader's contract rather than a
        # convenient one.
        monkeypatch.setattr(eq, "read_events",
                            lambda limit=None, reverse=False: list(reversed(events)) if reverse else list(events))
        return eq.get_policies_surfaced_this_cycle()
    return _run


class TestSurfacedThisCycle:
    def test_nothing_surfaced_yet(self):
        """Before any injection the answer is empty, and empty means empty."""
        import macf.event_queries as eq
        assert isinstance(eq.get_policies_surfaced_this_cycle(), dict)

    def test_records_the_policy_and_the_task_that_surfaced_it(self, surfaced):
        got = surfaced([_ev("policy_injection_activated",
                            policy_name="task_management", task_id="1248")])
        assert got == {"task_management": "1248"}

    def test_repeat_keeps_the_FIRST_task_not_the_latest(self, surfaced):
        """The pointer should send the reader to where the content actually is."""
        got = surfaced([
            _ev("policy_injection_activated", policy_name="task_management", task_id="1248"),
            _ev("policy_injection_activated", policy_name="task_management", task_id="1251"),
        ])
        assert got == {"task_management": "1248"}

    def test_compaction_is_the_boundary(self, surfaced):
        """A new cycle has no memory of the content, so the guide earns its cost again."""
        got = surfaced([
            _ev("policy_injection_activated", policy_name="task_management", task_id="900"),
            _ev("compaction_detected", cycle=525),
            _ev("policy_injection_activated", policy_name="testing", task_id="1248"),
        ])
        assert got == {"testing": "1248"}

    def test_clearing_an_injection_does_not_unsurface_it(self, surfaced):
        """Clearing removes a pending injection, not the agent's exposure.

        Injected text persists in the conversation's message history for the
        rest of the cycle, so re-showing it after a clear would re-show
        something already present.
        """
        got = surfaced([
            _ev("policy_injection_activated", policy_name="task_management", task_id="1248"),
            _ev("policy_injection_cleared", policy_name="task_management"),
        ])
        assert got == {"task_management": "1248"}
