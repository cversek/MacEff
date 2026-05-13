"""Generic hook-warning framework with dual-channel delivery.

Replaces ad-hoc ``except Exception as e: print(f'⚠️ MACF: ...',
file=sys.stderr)`` patterns scattered through hook handlers in
``macf.hooks.*`` and channel modules in ``macf.channels.*``.

Design intent:

1. Carry enough STRUCTURE (source, kind, detail, cause, remediation,
   full-trace pointer, severity) for any consumer to render the warning
   well — user-facing terminal, agent-facing systemMessage, and future
   remote-observer routing.
2. Deliver to BOTH channels by default with at-least-once semantics:
   stderr emits unconditionally as the failure-safe default, and the
   agent-channel contribution is returned for the caller to merge into
   the hook's return dict.
3. Deduplicate by ``source:kind`` fingerprint within a process so a
   chatty inner loop doesn't paper the terminal with identical lines.
   First occurrence is verbatim; subsequent occurrences get a ``(×N)``
   suffix.

Consumers call :func:`emit_warning` and merge its return dict into their
own hook return dict::

    return {**emit_warning(w), "continue": True, ...}
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Dict, Literal, Optional


Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class Warning:
    """Structured warning suitable for dual-channel emission.

    ``frozen=True`` makes instances hashable + immutable so they're safe
    to pass through callbacks and store in registries without aliasing
    hazards. New fields can be added as ``Optional`` without breaking
    callers — dataclass is additive-friendly.

    Attributes:
        source: Short identifier for the producing subsystem.
            Examples: ``"telegram"``, ``"config"``, ``"stop_hook"``.
        kind: Short identifier for the warning category within
            ``source``. Examples: ``"api_unreachable"``,
            ``"missing_required_field"``. ``source:kind`` is the dedup
            fingerprint — pick a kind narrow enough to NOT collapse
            genuinely-distinct issues but broad enough to deduplicate
            the chatty case.
        detail: One-line technical detail. NEVER a full stack trace —
            keep the trace at ``full_trace_path`` if useful. Goes
            verbatim into the stderr line and into the agent's
            systemMessage.
        likely_cause: Plain-language explanation of why this likely
            happened. Aimed at a human reader of the terminal, not the
            agent. Optional but recommended.
        user_remediation: Concrete action the user can take. Same
            audience and intent as ``likely_cause``. Optional.
        full_trace_path: Filesystem path where a longer trace, log, or
            dump was written if the warning needed one. ``None`` if
            ``detail`` is enough.
        severity: One of ``"info"``, ``"warning"``, ``"error"``. Used by
            future severity filters and by terminals that distinguish
            (colour, prefix).
    """

    source: str
    kind: str
    detail: str
    likely_cause: str = ""
    user_remediation: str = ""
    full_trace_path: Optional[str] = None
    severity: Severity = "warning"

    def fingerprint(self) -> str:
        """``source:kind`` — the dedup key. Stable across instances with
        the same source+kind, distinct otherwise."""
        return f"{self.source}:{self.kind}"


# Per-process dedup registry. Hook processes are short-lived so
# per-process is effectively per-invocation. Longer-lived processes
# (proxy, CLI repls) can pass an explicit registry via the ``_registry``
# arg to emit_warning if they want per-context dedup semantics.
_DEDUP_COUNTS: Dict[str, int] = {}


def reset_dedup_registry() -> None:
    """Empty the module-level dedup registry.

    Intended for tests and for long-lived processes that want a clean
    boundary at a specific point (e.g. a CLI repl between commands).
    Production hook code does not need to call this — the hook process
    exits, taking the registry with it.
    """
    _DEDUP_COUNTS.clear()


def emit_warning(
    w: Warning,
    *,
    dedupe: bool = True,
    _registry: Optional[Dict[str, int]] = None,
) -> dict:
    """Emit ``w`` to BOTH the user (stderr) and the agent (systemMessage).

    Stderr is written unconditionally as the failure-safe default — if
    the caller forgets to merge the returned dict, the agent loses the
    message but the user still sees it on the terminal.

    Args:
        w: The Warning to emit.
        dedupe: When True (default), increments a per-process counter
            keyed on ``w.fingerprint()`` and appends ``(×N)`` to both
            the stderr line and the systemMessage for ``N > 1``. Pass
            ``False`` for callers that want every occurrence emitted
            verbatim.
        _registry: Optional injected dedup registry (dict mapping
            fingerprint → count). Defaults to the module-level registry.
            Tests use this to isolate state; long-lived processes use
            it to scope dedup to a context. Underscore-prefixed because
            normal callers should never need to touch it.

    Returns:
        A dict slice intended to be merged into the hook's return dict::

            return {**emit_warning(w), "continue": True, ...}

        Currently the dict contains ``{"systemMessage": <str>}``. Future
        fields (e.g. ``hookSpecificOutput.additionalContext`` for hooks
        that support it) can be added without breaking existing callers.
    """
    registry = _registry if _registry is not None else _DEDUP_COUNTS

    suffix = ""
    if dedupe:
        fp = w.fingerprint()
        registry[fp] = registry.get(fp, 0) + 1
        count = registry[fp]
        if count > 1:
            suffix = f" (×{count})"

    # User channel: stderr (unconditional).
    cause_part = f" (cause: {w.likely_cause})" if w.likely_cause else ""
    stderr_line = f"⚠️ MACF {w.source}: {w.detail}{cause_part}{suffix}"
    print(stderr_line, file=sys.stderr)

    # Agent channel: systemMessage.
    parts = [
        f"⚠️ Warning from {w.source}: {w.kind}{suffix}",
        f"Details: {w.detail}",
    ]
    if w.likely_cause:
        parts.append(f"Cause: {w.likely_cause}")
    if w.user_remediation:
        parts.append(f"Recovery: {w.user_remediation}")
    if w.full_trace_path:
        parts.append(f"Full trace: {w.full_trace_path}")
    agent_msg = "\n".join(parts)

    return {"systemMessage": agent_msg}
