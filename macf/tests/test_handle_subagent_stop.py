"""Tests for handle_subagent_stop hook module."""
import json

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies for subagent_stop handler."""
    with patch('macf.hooks.handle_subagent_stop.get_current_session_id') as mock_session, \
         patch('macf.hooks.handle_subagent_stop.complete_deleg_drv') as mock_complete, \
         patch('macf.hooks.handle_subagent_stop.get_deleg_drv_stats') as mock_stats, \
         patch('macf.hooks.handle_subagent_stop.get_temporal_context') as mock_temporal:

        mock_session.return_value = "test-session-123"
        mock_complete.return_value = (True, 65, "abc123", "Explore")  # (success, duration, tool_use_id_short, subagent_type)
        mock_stats.return_value = {
            'count': 3,
            'total_duration': 180
        }
        mock_temporal.return_value = {
            "timestamp_formatted": "2025-10-08 01:15:30 AM EDT",
            "day_of_week": "Wednesday",
            "time_of_day": "01:15:30 AM"
        }

        yield {
            'session_id': mock_session,
            'complete': mock_complete,
            'stats': mock_stats,
            'temporal': mock_temporal
        }


def test_deleg_drv_completion_tracking(mock_dependencies):
    """Test DELEG_DRV completion tracking in production mode."""
    from macf.hooks.handle_subagent_stop import run

    mock_dependencies['complete'].return_value = (True, 65, "abc123", "Explore")

    result = run("")

    # In testing mode, complete_deleg_drv should NOT be called (safe-by-default)
    mock_dependencies['complete'].assert_called_once()
    assert result["continue"] is True


def test_delegation_stats_display(mock_dependencies):
    """Test delegation stats are displayed correctly."""
    from macf.hooks.handle_subagent_stop import run

    mock_dependencies['stats'].return_value = {
        'count': 3,
        'total_duration': 180
    }

    result = run("")

    assert "systemMessage" in result
    message = result["systemMessage"]

    # "Total Delegations: N" line was dropped (meaningless aggregate);
    # the per-call duration tag carries the meaningful signal.
    assert "Total Delegations:" not in message

    # Verify duration (180s = 3m)
    assert "3m" in message

    # Correlation tag should appear if mock provided one
    assert "abc123" in message


def test_temporal_context_included(mock_dependencies):
    """Test temporal context is included in output."""
    from macf.hooks.handle_subagent_stop import run

    result = run("")

    message = result["systemMessage"]

    # Verify timestamp present
    assert "01:15:30 AM EDT" in message or "Wednesday" in message


def test_duration_formatting(mock_dependencies):
    """Test duration is formatted correctly."""
    from macf.hooks.handle_subagent_stop import run

    mock_dependencies['complete'].return_value = (True, 65, "abc123", "Explore")
    mock_dependencies['stats'].return_value = {
        'count': 1,
        'total_duration': 65
    }

    result = run("")

    message = result["systemMessage"]

    # 65 seconds should display as 1m
    assert "1m" in message


def test_exception_handling(mock_dependencies):
    """Test hook handles exceptions gracefully."""
    from macf.hooks.handle_subagent_stop import run

    # Simulate exception in stats
    mock_dependencies['stats'].side_effect = Exception("Stats error")

    result = run("")

    # Should never crash - SubagentStop uses systemMessage only (no hookSpecificOutput)
    assert result["continue"] is True
    assert "systemMessage" in result
    assert "error" in result["systemMessage"].lower()


def _stop(agent_id, agent_type=""):
    """A SubagentStop payload as the client sends it."""
    return json.dumps({
        "session_id": "test-session-123",
        "hook_event_name": "SubagentStop",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "agent_transcript_path": "",
        "last_assistant_message": "Reading notes.md",
    })


def _events(name):
    from macf.agent_events_log import read_events
    return [e for e in read_events() if e.get("event") == name]


def test_an_agent_nobody_delegated_is_not_a_delegation(mock_dependencies):
    """A stop with no agent_type and no SubagentStart behind it is the client's own agent."""
    from macf.hooks.handle_subagent_stop import run

    result = run(_stop("a0123456789abcdef"))

    assert result == {"continue": True}
    assert [e["data"]["agent_id"] for e in _events("undelegated_agent_stopped")] == ["a0123456789abcdef"]
    assert _events("delegation_completed") == []
    assert _events("deleg_drv_ended") == []


def test_a_bridged_agent_still_counts(mock_dependencies):
    """A stop whose agent SubagentStart recorded is a delegation, with or without its type."""
    from macf.hooks.handle_subagent_stop import run
    from macf.utils.drives import start_deleg_drv, bridge_deleg_drv_to_agent

    start_deleg_drv("test-session-123", subagent_type="Explore",
                    tool_use_id="toolu_01abcdefghijklmnopqrstuv")
    bridge_deleg_drv_to_agent("test-session-123", "a0123456789abcdef", agent_type="Explore")

    result = run(_stop("a0123456789abcdef"))

    assert "systemMessage" in result
    assert len(_events("delegation_completed")) == 1
    assert [e["data"]["bridged"] for e in _events("deleg_drv_ended")] == [True]
    assert _events("undelegated_agent_stopped") == []


def test_a_typed_stop_counts_without_a_recorded_start(mock_dependencies):
    """A stop the client sends with a type is a delegation even when its start was missed."""
    from macf.hooks.handle_subagent_stop import run

    run(_stop("a0123456789abcdef", agent_type="Explore"))

    assert len(_events("delegation_completed")) == 1
    assert [e["data"]["bridged"] for e in _events("deleg_drv_ended")] == [False]
    assert _events("undelegated_agent_stopped") == []
