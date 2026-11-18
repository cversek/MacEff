"""Scope gate idle-stop counter — failsafe escape from deadlocked Stop hook.

Background (BUG #1022): the Stop hook's scope gate blocks completion when
active scoped tasks remain. Each block forces a response from the agent;
if the agent has no useful work to do (just "Standing by" or similar), the
loop is closed — agent stops, gate blocks, agent responds, gate fires
again — and incoming channel messages get queued behind the loop, leaving
the agent unreachable through its primary channel until the user manually
intervenes from the terminal.

Design: simple decrementing counter, persisted as a small JSON sidecar in
this user's private runtime directory.

- Counter starts at COUNT_INIT (default 5).
- handle_pre_tool_use resets to COUNT_INIT on every fire (any useful work
  by the agent counts as activity that should re-engage the gate).
- handle_stop decrements when the scope gate would block AND there has
  been no PreToolUse activity since the last Stop. When counter reaches
  0, the gate is bypassed (return continue=True without 'block') so the
  agent escapes the loop.

Stuck agents escape after at most COUNT_INIT consecutive idle stops.
Working agents keep the gate active because every tool call resets the
counter.
"""

import json
import os
from pathlib import Path

from macf.observability import Warning, emit_warning

COUNT_INIT = 5


def _counter_path() -> Path:
    """Path to this user's sidecar JSON tracking the idle-stop count.

    It lives in this user's private runtime directory (``utils.paths.user_runtime_dir``),
    never a bare ``/tmp/macf``. Several agents share one container, each under its own
    account, and the first to create ``/tmp/macf`` owned it: every other agent's write
    failed, its counter read COUNT_INIT on every Stop, and the failsafe could never reach
    zero, so the scope gate re-prompted without limit.
    """
    from macf.utils.paths import user_runtime_dir
    return user_runtime_dir() / "scope_gate_idle_counter.json"


def _read() -> int:
    """Read current counter value; default to COUNT_INIT if missing/corrupt."""
    p = _counter_path()
    try:
        if not p.exists():
            return COUNT_INIT
        data = json.loads(p.read_text())
        v = int(data.get("remaining", COUNT_INIT))
        return max(0, min(COUNT_INIT, v))
    except (OSError, ValueError, json.JSONDecodeError):
        return COUNT_INIT


def _write(v: int) -> None:
    """Persist counter value. A failure is non-fatal but never silent: a counter that
    cannot be saved reads COUNT_INIT on every Stop, and the failsafe it exists for
    never fires."""
    try:
        p = _counter_path()
        p.write_text(json.dumps({"remaining": int(v)}))
    except OSError as e:
        emit_warning(Warning(source="scope_gate_failsafe", kind="counter_unwritable",
                             detail=f"the idle-stop counter could not be saved ({e}); "
                                    f"the failsafe cannot count down until it can"))


def reset() -> None:
    """Reset the counter to COUNT_INIT (called from PreToolUse — agent did useful work)."""
    _write(COUNT_INIT)


def decrement_and_check() -> tuple[int, bool]:
    """Decrement the counter and report whether the gate should fail open.

    Returns:
        (remaining, fail_open) — remaining is the new counter value;
        fail_open is True when the counter has reached 0 and the gate
        should bypass blocking to let the agent escape.
    """
    current = _read()
    new_value = max(0, current - 1)
    _write(new_value)
    return new_value, new_value <= 0


def current() -> int:
    """Read current counter without modification (for logging / display)."""
    return _read()
