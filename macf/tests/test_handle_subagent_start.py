"""Tests for the SubagentStart hook (DELEG_DRV tool_use_id <-> agent_id bridge).

Coverage target: macf/src/macf/hooks/handle_subagent_start.py

This hook bridges the parent session's tool_use_id (known at PreToolUse:Agent)
to the subagent's agent_id (known only once CC's AgentTool spawns the
subagent) so SubagentStop can later correlate the two namespaces. It was
entirely untested (0% coverage) even though a broken bridge silently loses
DELEG_DRV correlation — the forensic trail connecting a delegation's start
to its completion. The hook is deliberately non-blocking (always returns
{"continue": True}, catches everything), so these tests check that the
Telegram/bridge side effects happen with the right arguments rather than
exercising any real network or bridge storage.
"""

import json

import pytest

from macf.hooks import handle_subagent_start as hsa


def test_format_deleg_drv_tag_with_full_info():
    """All three segments present render as type@tool_use_id|agent_id."""
    assert hsa._format_deleg_drv_tag("Explore", "01SoJX", "ad38b33c") == "[Explore@01SoJX|ad38b33c]"


def test_format_deleg_drv_tag_omits_empty_segments():
    """Empty tool_use_id/agent_id segments are dropped, not shown blank."""
    assert hsa._format_deleg_drv_tag("Explore", "", "") == "[Explore]"


def test_format_deleg_drv_tag_defaults_type_to_unknown_when_empty():
    """An empty subagent_type falls back to the literal 'unknown'."""
    assert hsa._format_deleg_drv_tag("", "", "") == "[unknown]"


@pytest.fixture
def stub_bridge(monkeypatch):
    """Stub the bridge call and its lookup so run() never touches real storage."""
    calls = []

    def _bridge(session_id, agent_id, agent_type):
        calls.append({"session_id": session_id, "agent_id": agent_id, "agent_type": agent_type})
        return True

    monkeypatch.setattr(hsa, "bridge_deleg_drv_to_agent", _bridge)
    monkeypatch.setattr(hsa, "get_deleg_drv_bridge_by_agent_id", lambda session_id, agent_id: {"tool_use_id_short": "01SoJX"})
    monkeypatch.setattr("macf.channels.telegram.send_telegram_notification", lambda *a, **k: None)
    return calls


def test_run_bridges_parsed_fields_and_returns_continue_true(stub_bridge):
    """run() parses session_id/agent_id/agent_type from stdin and bridges them."""
    stdin = json.dumps({"session_id": "sess1", "agent_id": "agentid1234", "agent_type": "Explore"})

    result = hsa.run(stdin)

    assert result == {"continue": True}
    assert stub_bridge == [{"session_id": "sess1", "agent_id": "agentid1234", "agent_type": "Explore"}]


def test_run_defaults_agent_id_to_empty_string_on_empty_stdin(stub_bridge, monkeypatch):
    """Empty stdin still bridges, with agent_id defaulting to ''."""
    monkeypatch.setattr(hsa, "get_current_session_id", lambda: "auto-detected-session")

    result = hsa.run("")

    assert result == {"continue": True}
    assert stub_bridge == [{"session_id": "auto-detected-session", "agent_id": "", "agent_type": "unknown"}]


def test_run_never_raises_when_bridge_function_throws(monkeypatch):
    """A blown-up bridge call is swallowed; the hook must never block the subagent."""
    def _boom(session_id, agent_id, agent_type):
        raise RuntimeError("bridge storage unavailable (simulated)")

    monkeypatch.setattr(hsa, "bridge_deleg_drv_to_agent", _boom)

    result = hsa.run(json.dumps({"session_id": "sess1", "agent_id": "a1", "agent_type": "Explore"}))

    assert result == {"continue": True}
