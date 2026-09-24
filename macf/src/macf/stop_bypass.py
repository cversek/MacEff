"""One passage through the Stop gates for an injected ``/compact``.

The gates hold an AUTO_MODE session open while scoped work, due duties or a burn
intent remain, and they do it by refusing the Stop that ends a turn. A slash
command typed into the pane by ``macf_tools inject`` is only submitted when the
turn ends, so an agent that winds down and injects ``/compact`` is held open by
the same gate whose carry-through design needs that compaction. The command sits
in the input queue and never runs.

``arm`` records that a compaction was injected; the next Stop consumes it and is
allowed, and every Stop after it is gated as before. The passage is narrow on
purpose:

- Only commands in ``BYPASS_COMMANDS`` arm it. A passage for any slash command
  would let ``inject help`` walk out of the gate. Compaction is the exit the
  sprint policy sanctions, and scope is carried across it.
- It is armed only after the injection was delivered to the pane.
- It lasts one Stop, and dies at the next cycle boundary (the read is cycle
  scoped) or after ``BYPASS_TTL_SEC``, so a token whose command the client
  dropped cannot become a standing escape.
"""

import time
from typing import Optional

from .agent_events_log import append_event, read_events

BYPASS_ARMED_EVENT = "stop_gate_suspend_once"
BYPASS_CONSUMED_EVENT = "stop_gate_bypassed_once"
BYPASS_COMMANDS = frozenset({"compact"})
BYPASS_TTL_SEC = 30 * 60


def arm(command: str) -> bool:
    """Record an injected command that needs the turn to end. False if not eligible."""
    command = command.lstrip("/").strip()
    if command not in BYPASS_COMMANDS:
        return False
    return append_event(BYPASS_ARMED_EVENT, {
        "command": command,
        "expires_epoch": time.time() + BYPASS_TTL_SEC,
    })


def consume() -> Optional[dict]:
    """Take the armed passage if one is live, recording that it was taken.

    Returns the armed event's data, or None when there is nothing to take: no
    token this cycle, the newest one already consumed, expired, or for a command
    that is not eligible.
    """
    for event in read_events(reverse=True):
        kind = event.get("event")
        if kind == BYPASS_CONSUMED_EVENT:
            return None
        if kind != BYPASS_ARMED_EVENT:
            continue
        data = event.get("data") or {}
        if data.get("command") not in BYPASS_COMMANDS:
            return None
        if (data.get("expires_epoch") or 0) <= time.time():
            return None
        # If this append fails the token stays live and a later Stop may pass
        # too, until the TTL. Refusing instead would reproduce the defect this
        # module exists for: the queued /compact would never run.
        append_event(BYPASS_CONSUMED_EVENT, {
            "command": data["command"],
            "armed_timestamp": event.get("timestamp"),
        })
        return data
    return None
