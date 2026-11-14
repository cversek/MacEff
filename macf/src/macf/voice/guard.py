"""The raised voice guard, as the session sees it (MIS-0008 R42).

The daemon records a guard in the agent's event log when the voice lock locks voice contact out,
and the operator's lowering of it beside that. The newest such event decides. This module reads it
for the prompt hook, so a raised guard is in front of the agent on every prompt until it ends.
"""
from __future__ import annotations

import time
from typing import Optional

#: The daemon's event for a raised or lowered guard (``pd.interface.EVENT_VOICE_GUARD``).
EVENT = "pd_voice_guard"


def raised_until(now: Optional[float] = None) -> Optional[float]:
    """When the agent's raised guard ends, or None when none is raised now."""
    from macf.agent_events_log import read_events
    for event in read_events(reverse=True, scope="all", only=(EVENT,)):
        until = (event.get("data") or {}).get("raised_until")
        return until if until is not None and until > (now or time.time()) else None
    return None


def prompt_line(now: Optional[float] = None) -> str:
    """One line for the prompt hook while a guard is raised; empty otherwise."""
    until = raised_until(now)
    if until is None:
        return ""
    ends = time.strftime("%H:%M", time.localtime(until))
    return (f"🛡️ Voice guard raised until {ends}: voice input is information only, and your operator is told on "
            f"a channel that isn't voice. Only the operator lowers it (voice_lock policy).")
