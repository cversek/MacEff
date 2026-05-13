"""Tests for DELEG_DRV Start/Complete correlation + subagent_type propagation.

Verifies that:
- start_deleg_drv emits the correlation_id and subagent_type in the
  deleg_drv_started event.
- complete_deleg_drv reads the correlation_id from the active start
  event and emits it (matching) in the deleg_drv_ended event, returning
  it as the third tuple element.
- get_active_deleg_drv_start returns the (started_at, correlation_id)
  tuple.
- Subagent_type isn't lost between caller and event (the bug user
  surfaced: it was being fetched in hooks but never passed to the
  drives layer).
"""
from __future__ import annotations

import time

from macf.utils.drives import start_deleg_drv, complete_deleg_drv
from macf.event_queries import get_active_deleg_drv_start
from macf.agent_events_log import read_events


SESSION = "test-correlation-roundtrip"


def _events_of_type(event_name: str):
    """Yield events from the isolated log matching ``event_name`` for our session."""
    for ev in read_events(reverse=False):
        if ev.get("event") == event_name and ev.get("data", {}).get("session_id") == SESSION:
            yield ev


def test_start_emits_correlation_id():
    """correlation_id passed to start_deleg_drv appears in the started event."""
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", correlation_id="abc123")

    events = list(_events_of_type("deleg_drv_started"))
    assert len(events) == 1
    data = events[0]["data"]
    assert data["correlation_id"] == "abc123"
    assert data["subagent_type"] == "DevOpsEng"


def test_active_start_query_returns_started_at_and_correlation_id():
    """get_active_deleg_drv_start returns (started_at, correlation_id) tuple."""
    start_deleg_drv(SESSION, subagent_type="TestEng", correlation_id="xyz789")

    started_at, correlation_id = get_active_deleg_drv_start(SESSION)
    assert started_at > 0.0
    assert correlation_id == "xyz789"


def test_complete_propagates_correlation_id_into_ended_event():
    """The correlation_id from the active start flows through to the ended event."""
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", correlation_id="def456")
    time.sleep(0.01)  # ensure measurable duration

    success, duration, correlation_id = complete_deleg_drv(SESSION, subagent_type="DevOpsEng")

    assert success is True
    assert duration > 0.0
    assert correlation_id == "def456"

    # ended event also carries it
    ended_events = list(_events_of_type("deleg_drv_ended"))
    assert ended_events[-1]["data"]["correlation_id"] == "def456"


def test_complete_returns_empty_correlation_when_start_had_none():
    """Legacy start (no correlation_id) still works; complete returns ''."""
    start_deleg_drv(SESSION, subagent_type="TestEng")  # no correlation_id arg
    time.sleep(0.01)

    success, _duration, correlation_id = complete_deleg_drv(SESSION)

    assert success is True
    assert correlation_id == ""


def test_complete_returns_false_when_no_active_drive():
    """No active start → complete returns (False, 0.0, '')."""
    success, duration, correlation_id = complete_deleg_drv(SESSION)

    assert success is False
    assert duration == 0.0
    assert correlation_id == ""


def test_subagent_type_propagates_through_started_event():
    """The subagent_type the caller passes appears in the started event,
    not the legacy 'unknown' default."""
    start_deleg_drv(SESSION, subagent_type="ClaudeReviewer")

    data = next(_events_of_type("deleg_drv_started"))["data"]
    assert data["subagent_type"] == "ClaudeReviewer"


def test_subagent_type_propagates_through_ended_event():
    """The subagent_type the caller passes to complete_deleg_drv appears
    in the ended event (the bug user surfaced was that this was being
    fetched in hooks but never propagated to the drives layer)."""
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", correlation_id="ghi")
    time.sleep(0.01)
    complete_deleg_drv(SESSION, subagent_type="DevOpsEng")

    data = list(_events_of_type("deleg_drv_ended"))[-1]["data"]
    assert data["subagent_type"] == "DevOpsEng"
