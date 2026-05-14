"""Tests for DELEG_DRV Start/Complete correlation + subagent_type propagation.

Verifies that:
- start_deleg_drv emits the tool_use_id_short and subagent_type in the
  deleg_drv_started event.
- complete_deleg_drv reads the tool_use_id_short from the active start
  event and emits it (matching) in the deleg_drv_ended event, returning
  it as the third tuple element.
- get_active_deleg_drv_start returns the (started_at, tool_use_id_short)
  tuple.
- Subagent_type isn't lost between caller and event (the bug user
  surfaced: it was being fetched in hooks but never passed to the
  drives layer).
"""
from __future__ import annotations

import time

from macf.utils.drives import (
    start_deleg_drv,
    complete_deleg_drv,
    bridge_deleg_drv_to_agent,
    complete_deleg_drv_by_agent,
)
from macf.event_queries import (
    get_active_deleg_drv_start,
    get_oldest_unbridged_deleg_drv_started,
    get_deleg_drv_bridge_by_agent_id,
)
from macf.agent_events_log import read_events


SESSION = "test-correlation-roundtrip"


def _events_of_type(event_name: str):
    """Yield events from the isolated log matching ``event_name`` for our session."""
    for ev in read_events(reverse=False):
        if ev.get("event") == event_name and ev.get("data", {}).get("session_id") == SESSION:
            yield ev


def test_start_emits_tool_use_id_short():
    """tool_use_id_short passed to start_deleg_drv appears in the started event."""
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", tool_use_id="toolu_abc123dummyXXXX")

    events = list(_events_of_type("deleg_drv_started"))
    assert len(events) == 1
    data = events[0]["data"]
    assert data["tool_use_id_short"] == "abc123"
    assert data["subagent_type"] == "DevOpsEng"


def test_active_start_query_returns_started_at_tool_use_id_short_and_subagent_type():
    """get_active_deleg_drv_start returns (started_at, tool_use_id_short, subagent_type) tuple."""
    start_deleg_drv(SESSION, subagent_type="TestEng", tool_use_id="toolu_xyz789dummyXXXX")

    started_at, tool_use_id_short, subagent_type = get_active_deleg_drv_start(SESSION)
    assert started_at > 0.0
    assert tool_use_id_short == "xyz789"
    assert subagent_type == "TestEng"


def test_complete_propagates_tool_use_id_short_into_ended_event():
    """The tool_use_id_short from the active start flows through to the ended event."""
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", tool_use_id="toolu_def456dummyXXXX")
    time.sleep(0.01)  # ensure measurable duration

    success, duration, tool_use_id_short, _ = complete_deleg_drv(SESSION, subagent_type="DevOpsEng")

    assert success is True
    assert duration > 0.0
    assert tool_use_id_short == "def456"

    # ended event also carries it
    ended_events = list(_events_of_type("deleg_drv_ended"))
    assert ended_events[-1]["data"]["tool_use_id_short"] == "def456"


def test_complete_returns_empty_correlation_when_start_had_none():
    """Legacy start (no tool_use_id_short) still works; complete returns ''."""
    start_deleg_drv(SESSION, subagent_type="TestEng")  # no tool_use_id_short arg
    time.sleep(0.01)

    success, _duration, tool_use_id_short, _ = complete_deleg_drv(SESSION)

    assert success is True
    assert tool_use_id_short == ""


def test_complete_returns_false_when_no_active_drive():
    """No active start → complete returns (False, 0.0, '', '')."""
    success, duration, tool_use_id_short, subagent_type = complete_deleg_drv(SESSION)

    assert success is False
    assert duration == 0.0
    assert tool_use_id_short == ""
    assert subagent_type == ""


def test_complete_resolves_subagent_type_from_started_event():
    """When caller passes no subagent_type, complete returns the value from
    the started event (covers the SubagentStop case where hook_input
    doesn't carry subagent_type)."""
    start_deleg_drv(SESSION, subagent_type="Explore", tool_use_id="toolu_zzz999dummyXXXX")
    time.sleep(0.01)

    success, _duration, tool_use_id_short, sa_type = complete_deleg_drv(SESSION)

    assert success is True
    assert tool_use_id_short == "zzz999"
    assert sa_type == "Explore"


def test_complete_resolves_subagent_type_when_caller_passed_unknown():
    """Caller passing the literal 'unknown' is treated as no info — the
    started event's subagent_type wins."""
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", tool_use_id="toolu_abc000dummyXXXX")
    time.sleep(0.01)

    _, _, _, sa_type = complete_deleg_drv(SESSION, subagent_type="unknown")

    assert sa_type == "DevOpsEng"


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
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", tool_use_id="toolu_ghi000dummyXXXX")
    time.sleep(0.01)
    complete_deleg_drv(SESSION, subagent_type="DevOpsEng")

    data = list(_events_of_type("deleg_drv_ended"))[-1]["data"]
    assert data["subagent_type"] == "DevOpsEng"


# --- SubagentStart bridge mechanism --------------------------------------

def test_start_event_carries_full_tool_use_id():
    """``start_deleg_drv(tool_use_id=...)`` emits both the full id and the
    derived short slice."""
    tuid = "toolu_01ABCDEFghijklmnopqrstu"
    start_deleg_drv(SESSION, subagent_type="Explore", tool_use_id=tuid)

    data = next(_events_of_type("deleg_drv_started"))["data"]
    assert data["tool_use_id"] == tuid
    assert data["tool_use_id_short"] == "01ABCD"


def test_oldest_unbridged_query_returns_first_unmatched():
    """``get_oldest_unbridged_deleg_drv_started`` returns the FIFO-oldest
    started without a matching booted event."""
    start_deleg_drv(SESSION, subagent_type="Explore", tool_use_id="toolu_A1A1A1A1A1A1xxxxxxxx")
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", tool_use_id="toolu_B2B2B2B2B2B2xxxxxxxx")

    started_at, tool_use_id, _short, subagent_type = (
        get_oldest_unbridged_deleg_drv_started(SESSION)
    )

    assert started_at > 0.0
    assert tool_use_id == "toolu_A1A1A1A1A1A1xxxxxxxx"
    assert subagent_type == "Explore"


def test_bridge_consumes_oldest_unbridged_started():
    """Calling ``bridge_deleg_drv_to_agent`` consumes the oldest unbridged
    started; the next bridge call moves to the next-oldest. This is the
    FIFO matching that keeps parallel delegations correctly paired."""
    start_deleg_drv(SESSION, subagent_type="Explore", tool_use_id="toolu_A1A1A1A1A1A1xxxxxxxx")
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", tool_use_id="toolu_B2B2B2B2B2B2xxxxxxxx")

    bridge_deleg_drv_to_agent(SESSION, agent_id="aFIRST123", agent_type="Explore")
    bridge_deleg_drv_to_agent(SESSION, agent_id="aSECOND456", agent_type="DevOpsEng")

    bridges = list(_events_of_type("deleg_drv_subagent_booted"))
    assert len(bridges) == 2
    # First bridge claims the FIRST started
    assert bridges[0]["data"]["agent_id"] == "aFIRST123"
    assert bridges[0]["data"]["tool_use_id"] == "toolu_A1A1A1A1A1A1xxxxxxxx"
    # Second bridge claims the SECOND started
    assert bridges[1]["data"]["agent_id"] == "aSECOND456"
    assert bridges[1]["data"]["tool_use_id"] == "toolu_B2B2B2B2B2B2xxxxxxxx"


def test_complete_by_agent_uses_bridge_for_resolution():
    """``complete_deleg_drv_by_agent`` looks up the bridge by agent_id and
    emits the ended event with full pair-key + agent_transcript_path +
    last_assistant_message_preview."""
    start_deleg_drv(SESSION, subagent_type="Explore", tool_use_id="toolu_XYZ123XYZ456abcdef")
    bridge_deleg_drv_to_agent(SESSION, agent_id="aTARGET789", agent_type="Explore")
    time.sleep(0.01)

    success, duration, tuid, short, sa_type = complete_deleg_drv_by_agent(
        SESSION,
        agent_id="aTARGET789",
        agent_transcript_path="/tmp/subagents/agent-aTARGET789.jsonl",
        last_assistant_message="ok " * 200,  # long message; preview should truncate
    )

    assert success is True
    assert duration > 0.0
    assert tuid == "toolu_XYZ123XYZ456abcdef"
    assert short == "XYZ123"
    assert sa_type == "Explore"

    ended = list(_events_of_type("deleg_drv_ended"))[-1]["data"]
    assert ended["bridged"] is True
    assert ended["agent_id"] == "aTARGET789"
    assert ended["agent_transcript_path"] == "/tmp/subagents/agent-aTARGET789.jsonl"
    assert len(ended["last_assistant_message_preview"]) <= 200


def test_complete_by_agent_returns_unbridged_when_no_bridge_exists():
    """No bridge for this agent_id (e.g. SA started before instrumentation)
    → ended event still emits with bridged=False so the observation isn't
    silently dropped."""
    success, duration, tuid, short, sa_type = complete_deleg_drv_by_agent(
        SESSION, agent_id="aORPHAN", agent_transcript_path="/tmp/x", last_assistant_message="",
    )

    assert success is False
    assert tuid == ""

    ended = list(_events_of_type("deleg_drv_ended"))[-1]["data"]
    assert ended["bridged"] is False
    assert ended["agent_id"] == "aORPHAN"


def test_parallel_delegations_paired_correctly_via_bridge():
    """End-to-end parallel-delegation test: two starteds, two bridges
    (in interleaved order), two completes by agent_id. Each Complete
    pairs with its OWN Started — not "most recent unended"."""
    # Two starteds back-to-back (PreToolUse fires synchronously per Task)
    start_deleg_drv(SESSION, subagent_type="Explore", tool_use_id="toolu_A1A1A1A1A1A1xxxxxxxx")
    start_deleg_drv(SESSION, subagent_type="DevOpsEng", tool_use_id="toolu_B2B2B2B2B2B2xxxxxxxx")

    # Two SubagentStarts in order
    bridge_deleg_drv_to_agent(SESSION, agent_id="aONE111", agent_type="Explore")
    bridge_deleg_drv_to_agent(SESSION, agent_id="aTWO222", agent_type="DevOpsEng")

    # Subagent TWO finishes FIRST (out of original dispatch order)
    _, _, tuid_two, _, sa_two = complete_deleg_drv_by_agent(
        SESSION, agent_id="aTWO222", agent_transcript_path="/x", last_assistant_message=""
    )
    assert tuid_two == "toolu_B2B2B2B2B2B2xxxxxxxx"
    assert sa_two == "DevOpsEng"

    # Subagent ONE finishes second
    _, _, tuid_one, _, sa_one = complete_deleg_drv_by_agent(
        SESSION, agent_id="aONE111", agent_transcript_path="/y", last_assistant_message=""
    )
    assert tuid_one == "toolu_A1A1A1A1A1A1xxxxxxxx"
    assert sa_one == "Explore"

    # Each subagent's Complete event references its OWN tool_use_id —
    # the "most-recent-unended" heuristic would have broken this.
