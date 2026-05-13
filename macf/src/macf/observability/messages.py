"""Hook messages with CLI ↔ Telegram parity.

Replaces patterns where a hook constructed one piece of content for the
agent's ``systemMessage`` and a separate, often-truncated string for
Telegram. With :class:`HookMessage` + :func:`emit_message` the same
payload reaches both channels — local user (via the CC terminal's
rendering of ``systemMessage``), agent (via ``systemMessage``), and
remote observer (via ``macf.channels.telegram.send_telegram_notification``).

Producers expected: hook handlers in ``macf.hooks.*``. Specifically
status-class events (DEV_DRV completion summaries, mode transitions,
session-start banners) — these are not warnings, so they don't belong
in the :func:`~macf.observability.emit_warning` path.

The :attr:`HookMessage.originating_agent` field is reserved for tool-
invocation observations and any other producer where attribution matters
— e.g. a PreToolUse hook firing under a SubAgent's session can tag the
message with the SA's identity so remote observers can follow individual
SA threads in the stream.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal, Optional


Severity = Literal["info", "warning"]


@dataclass(frozen=True)
class HookMessage:
    """Structured hook message suitable for dual-channel emission.

    Attributes:
        hook_name: Short identifier for the producing hook
            (e.g. ``"stop"``, ``"pre_tool_use"``, ``"session_start"``).
        event: Short identifier for the event category within the hook
            (e.g. ``"dev_drv_complete"``, ``"tool_invoked"``,
            ``"session_started"``). Together with ``hook_name`` this
            identifies the kind of message for downstream filtering /
            routing.
        payload: The full message body. Same content goes to both the
            agent (via ``systemMessage``) and the remote observer (via
            Telegram), so write it for both audiences.
        originating_agent: Optional attribution for messages produced
            while a SubAgent is active — e.g. ``"DevOpsEng@abc123"``
            (display name + 6-char UUID prefix). ``None`` for messages
            produced by the Primary Agent or by hook code that doesn't
            track agent identity. Rendered as a prefix-tag on both
            channels when present.
        severity: ``"info"`` (default) or ``"warning"``. ``"warning"``
            indicates the message is informational about a non-failure
            anomaly — for actual errors use
            :func:`~macf.observability.emit_warning` instead.
    """

    hook_name: str
    event: str
    payload: str
    originating_agent: Optional[str] = None
    severity: Severity = "info"


def _render_attribution(originating_agent: Optional[str]) -> str:
    """Return a single-line attribution tag for the channel, or empty
    string if no attribution is set."""
    if not originating_agent:
        return ""
    return f"[from {originating_agent}] "


def emit_message(
    m: HookMessage,
    *,
    telegram_prefix: str = "",
    send_to_telegram: bool = True,
) -> dict:
    """Emit ``m`` to BOTH the agent (systemMessage) and Telegram.

    The payload is sent verbatim — callers should write it for both
    audiences. The optional ``telegram_prefix`` becomes the prefix tag
    on the Telegram message; if empty, no prefix is used.

    Args:
        m: The HookMessage to emit.
        telegram_prefix: Prefix for the Telegram message (typically an
            emoji + short label, e.g. ``"📊 DEV_DRV Complete"``).
            Empty string sends the payload without a prefix.
        send_to_telegram: When False, only the systemMessage path runs.
            Useful for testing or for cases where Telegram routing is
            independently disabled.

    Returns:
        A dict slice intended to be merged into the hook's return dict::

            return {**emit_message(m, telegram_prefix="📊 Done"), "continue": True}

        The dict contains ``{"systemMessage": <attribution><payload>}``.
    """
    attribution = _render_attribution(m.originating_agent)
    framed_payload = f"{attribution}{m.payload}"

    if send_to_telegram:
        # Local import: keeps observability importable in contexts where
        # channels.telegram is unavailable (e.g. minimal test runs).
        try:
            from ..channels.telegram import send_telegram_notification
            send_telegram_notification(framed_payload, prefix=telegram_prefix)
        except ImportError as e:
            print(f"⚠️ MACF observability: telegram channel unavailable: {e}", file=sys.stderr)

    return {"systemMessage": framed_payload}
