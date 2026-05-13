"""macf.observability — structured warnings, hook messages, tool metadata.

Cross-cutting visibility primitives for code paths that need to tell BOTH
the user and the agent about something — an error, a status change, a
warning. Replaces hand-rolled ``print(..., file=sys.stderr)`` plus an
ad-hoc ``systemMessage`` build with a single audit point that handles
formatting, deduplication, and (future) remote-observer routing.

Current contents:

- ``warnings`` — :class:`Warning` dataclass + :func:`emit_warning` for
  structured, dual-channel (user + agent) diagnostic emission with
  per-process deduplication.
- ``messages`` — :class:`HookMessage` dataclass + :func:`emit_message`
  for non-warning content (status, mode markers, completion summaries)
  with CLI-terminal ↔ Telegram parity for remote observers. Carries
  optional ``originating_agent`` attribution for messages produced
  under a SubAgent's session.

Planned siblings (separate modules within this namespace):

- ``tool_metadata`` — concise per-tool metadata formatters used by
  PreToolUse hook output (tool name + target/argument summary).

Producers expected: hook handlers in ``macf.hooks.*``, channel modules
in ``macf.channels.*``, and CLI commands in ``macf.cli``.
"""
from __future__ import annotations

from .messages import HookMessage, emit_message
from .warnings import Warning, emit_warning, reset_dedup_registry

__all__ = [
    "HookMessage",
    "Warning",
    "emit_message",
    "emit_warning",
    "reset_dedup_registry",
]
