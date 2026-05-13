"""Unit tests for macf.observability.messages.

Covers HookMessage dataclass shape, attribution rendering, and the
emit_message dual-channel contract (systemMessage + Telegram).
"""
from __future__ import annotations

import pytest

from macf.observability import HookMessage, emit_message


def _make_msg(**overrides) -> HookMessage:
    defaults = dict(
        hook_name="stop",
        event="dev_drv_complete",
        payload="DEV_DRV #5 complete (45s)\nDuration: 45s\nTokens: 12k",
    )
    defaults.update(overrides)
    return HookMessage(**defaults)


def _stub_send(monkeypatch: pytest.MonkeyPatch) -> list:
    """Replace send_telegram_notification with a recorder; returns the
    list of (text, prefix) tuples it captured.

    We monkeypatch on the channels.telegram module rather than on the
    observability.messages namespace because messages.py does a local
    `from ..channels.telegram import send_telegram_notification` inside
    emit_message — the source-of-truth binding is on the channels side.
    """
    captured = []

    def _recorder(text: str, prefix: str = "", **kw):
        captured.append((text, prefix))
        # Return a value that looks NotifyResult-ish for callers that
        # might check it. emit_message ignores the return today.
        return type("R", (), {"success": True, "warning": None, "__bool__": lambda self: True})()

    monkeypatch.setattr(
        "macf.channels.telegram.send_telegram_notification",
        _recorder,
    )
    return captured


# --- Dataclass shape ------------------------------------------------------

def test_hookmessage_construction_with_defaults():
    """Required fields populate; optionals use documented defaults."""
    m = HookMessage(hook_name="stop", event="dev_drv_complete", payload="x")

    assert m.hook_name == "stop"
    assert m.event == "dev_drv_complete"
    assert m.payload == "x"
    assert m.originating_agent is None
    assert m.severity == "info"


def test_hookmessage_is_frozen():
    """frozen=True: mutation attempts raise."""
    m = _make_msg()
    with pytest.raises(Exception):
        m.hook_name = "other"  # type: ignore[misc]


def test_hookmessage_carries_originating_agent():
    """SubAgent attribution field round-trips."""
    m = _make_msg(originating_agent="DevOpsEng@abc123")
    assert m.originating_agent == "DevOpsEng@abc123"


# --- emit_message dual-channel contract -----------------------------------

def test_emit_returns_system_message_with_payload(monkeypatch: pytest.MonkeyPatch):
    """Return dict carries the payload as systemMessage."""
    _stub_send(monkeypatch)
    m = _make_msg()

    result = emit_message(m)

    assert "systemMessage" in result
    assert "DEV_DRV #5 complete" in result["systemMessage"]


def test_emit_sends_to_telegram_with_prefix(monkeypatch: pytest.MonkeyPatch):
    """Telegram channel receives the payload with the supplied prefix."""
    captured = _stub_send(monkeypatch)
    m = _make_msg()

    emit_message(m, telegram_prefix="📊 DEV_DRV Complete")

    assert len(captured) == 1
    text, prefix = captured[0]
    assert prefix == "📊 DEV_DRV Complete"
    assert "DEV_DRV #5 complete" in text


def test_emit_skips_telegram_when_disabled(monkeypatch: pytest.MonkeyPatch):
    """send_to_telegram=False yields systemMessage but no Telegram call."""
    captured = _stub_send(monkeypatch)
    m = _make_msg()

    result = emit_message(m, send_to_telegram=False)

    assert "systemMessage" in result
    assert captured == []


def test_emit_prepends_attribution_when_originating_agent_set(
    monkeypatch: pytest.MonkeyPatch,
):
    """SubAgent attribution renders as a prefix tag on both channels."""
    captured = _stub_send(monkeypatch)
    m = _make_msg(originating_agent="DevOpsEng@abc123")

    result = emit_message(m, telegram_prefix="🎯 Tool Use")

    # systemMessage starts with the attribution
    assert result["systemMessage"].startswith("[from DevOpsEng@abc123]")
    # Telegram payload starts with the same attribution
    text, _ = captured[0]
    assert text.startswith("[from DevOpsEng@abc123]")


def test_emit_omits_attribution_when_originating_agent_is_none(
    monkeypatch: pytest.MonkeyPatch,
):
    """No attribution → no '[from ...]' prefix anywhere."""
    captured = _stub_send(monkeypatch)
    m = _make_msg()  # default: originating_agent=None

    result = emit_message(m, telegram_prefix="x")

    assert "[from" not in result["systemMessage"]
    text, _ = captured[0]
    assert "[from" not in text


def test_emit_telegram_prefix_defaults_to_empty(monkeypatch: pytest.MonkeyPatch):
    """No prefix supplied → send_telegram_notification gets prefix=''."""
    captured = _stub_send(monkeypatch)
    m = _make_msg()

    emit_message(m)

    text, prefix = captured[0]
    assert prefix == ""
