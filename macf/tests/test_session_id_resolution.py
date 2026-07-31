"""Session-id resolution priority (cversek/MacEff#158).

`get_current_session_id()` resolved from the most recent `session_started`
event — a global last-writer-wins singleton. When a second CC session started
under the same agent home, every hook in every session (including the original,
still-live one) began stamping the newcomer's id, and since ordinary hooks
never write `session_started`, the original could never reclaim its identity.

The hook process already holds the authoritative answer, so prefer it.
"""
import pytest

from macf.utils.session import get_current_session_id


def test_hook_input_session_id_wins(monkeypatch):
    """Tier 1: CC tells each hook its own session id — nothing beats that."""
    monkeypatch.setenv("MACF_SESSION_ID", "from-env")
    assert get_current_session_id({"session_id": "from-hook"}) == "from-hook"


def test_env_used_when_no_hook_input(monkeypatch):
    """Tier 2: CLI invoked from inside a session."""
    monkeypatch.setenv("MACF_SESSION_ID", "from-env")
    assert get_current_session_id() == "from-env"


def test_claude_code_session_id_env_honored(monkeypatch):
    monkeypatch.delenv("MACF_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "from-cc-env")
    assert get_current_session_id() == "from-cc-env"


def test_empty_hook_input_falls_through(monkeypatch):
    """A payload without session_id must not shadow the env tier."""
    monkeypatch.setenv("MACF_SESSION_ID", "from-env")
    assert get_current_session_id({}) == "from-env"
    assert get_current_session_id({"session_id": ""}) == "from-env"


def test_concurrent_session_cannot_hijack_a_live_hook(monkeypatch):
    """The reported failure: a newcomer's session_started must not rename us.

    With the hook's own payload in hand, the shared event log is irrelevant —
    whatever it says, this hook reports the session CC handed it.
    """
    monkeypatch.setenv("MACF_SESSION_ID", "throwaway-newcomer")
    live = get_current_session_id({"session_id": "original-live-session"})
    assert live == "original-live-session"
