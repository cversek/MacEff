"""An injected /compact must be able to end the turn that queued it.

The Stop gates refuse the stop that submits a queued slash command, so an agent
that winds down a sprint and injects /compact is held open by the gate whose
carry-through design needs that compaction. One passage, for compaction only.
"""

import json
import time
from unittest.mock import patch

import pytest

from macf import stop_bypass
from macf.agent_events_log import append_event


@pytest.fixture(autouse=True)
def _fresh_failsafe():
    """The idle-stop counter is a global sidecar; start and leave it full."""
    from macf.task.scope_gate_failsafe import reset
    reset()
    yield
    reset()


def _stop():
    from macf.hooks.handle_stop import run
    with patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(True, "test")):
        return run(json.dumps({"stop_reason": "end_turn", "session_id": "test-sess"}))


def test_only_compaction_arms_a_passage(isolated_events_log):
    """A passage for any slash command would let `inject help` walk out of the gate."""
    assert stop_bypass.arm("help") is False
    assert stop_bypass.consume() is None
    assert stop_bypass.arm("/compact") is True


def test_one_passage_then_the_gate_holds(isolated_events_log):
    stop_bypass.arm("compact")
    assert stop_bypass.consume()["command"] == "compact"
    assert stop_bypass.consume() is None


def test_an_expired_passage_is_not_taken(isolated_events_log):
    append_event(stop_bypass.BYPASS_ARMED_EVENT,
                 {"command": "compact", "expires_epoch": time.time() - 1})
    assert stop_bypass.consume() is None


@pytest.mark.parametrize("rc, armed", [(0, True), (1, False)])
def test_inject_arms_only_after_delivery(isolated_events_log, rc, armed):
    """A failed send has queued nothing, so it must leave no passage behind."""
    from macf import supervisor
    with patch.object(supervisor, "_find_own_supervisor", return_value={"name": "me"}), \
         patch.object(supervisor, "send_keys", return_value=rc):
        assert supervisor.send_slash_to_self("compact") == rc
    assert (stop_bypass.consume() is not None) is armed


def test_an_injected_compaction_ends_a_gated_sprint_turn(isolated_events_log):
    """End to end, the observed defect: scope holding, /compact injected, the
    Stop refused anyway. Now the first Stop passes and the next is gated."""
    from macf.task.scope import set_scope
    set_scope(["4242"])
    assert _stop().get("decision") == "block", "precondition: the scope gate holds"

    stop_bypass.arm("compact")
    first = _stop()
    assert first.get("decision") != "block"
    assert "injected /compact" in first.get("systemMessage", "")

    assert _stop().get("decision") == "block", "the passage was not one-shot"
