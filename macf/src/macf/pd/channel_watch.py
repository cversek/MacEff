"""Whether the session's MacEff channel is dark, derived each pass (MIS-0002-R115).

A channel is dark when the session that should hold it is running and none is attached:
either one was attached during this incarnation of the session and has gone, or none
attached within the declaration's ``channel_connect_s`` of the incarnation being seen.
A restart is not a dark channel. While no session runs there is nothing to hold a channel,
and a new incarnation starts its own window.

Nothing is stored but what is written to the event log (MIS-0002-R16): a dark stretch opens
with one ``pd_channel_dark`` and closes with one ``pd_channel_back``. The outside watch reads
those and is what tells the operator, through its own alert path (R75), because a daemon
whose channel is dark has no other way to reach anyone.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from macf.agent_events_log import append_event
from macf.pd.interface import EVENT_CHANNEL_BACK, EVENT_CHANNEL_DARK

Incarnation = Tuple[int, str]          # the session unit's (pid, start), as the core reports it


@dataclass
class DarkChannel:
    """One pass at a time: ``tick(session, attached)``."""

    card: str
    connect_s: float
    append: Callable[[str, dict], bool] = append_event
    clock: Callable[[], float] = time.monotonic
    session: Optional[Incarnation] = None
    seen_at: float = 0.0
    was_attached: bool = False
    dark: bool = False

    def tick(self, session: Optional[Incarnation], attached: bool) -> None:
        now = self.clock()
        if session != self.session:
            # A new incarnation, or none: what the old one's channel did is not this one's.
            # A dark stretch that the restart ended is closed by the restart, not by a channel.
            if self.dark and self.session is not None:
                self._say(EVENT_CHANNEL_BACK, "the session restarted; its new incarnation starts its own window")
            self.session, self.seen_at, self.was_attached, self.dark = session, now, False, False
        if session is None:
            return
        if attached:
            if self.dark:
                self._say(EVENT_CHANNEL_BACK, "a channel attached")
            self.was_attached, self.dark = True, False
            return
        if self.dark:
            return
        if self.was_attached:
            self.dark = True
            self._say(EVENT_CHANNEL_DARK, "the session's channel dropped while the session ran")
        elif now - self.seen_at > self.connect_s:
            self.dark = True
            self._say(EVENT_CHANNEL_DARK, f"no channel attached within {self.connect_s:g} s of the session's start")

    def _say(self, event: str, reason: str) -> None:
        pid = self.session[0] if self.session else None
        if not self.append(event, {"agent": self.card, "session_pid": pid, "reason": reason}):
            print(f"⚠️ MACF: pd: the {event} event was not recorded: {reason}", file=sys.stderr)
