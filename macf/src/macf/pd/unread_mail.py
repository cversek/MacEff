"""Mail left unread past the agent's declared threshold, derived each pass (MIS-0002-R55).

Mail is unread while it sits in the agent's pickup box: ingesting a message takes it out.
An unread spell starts when the oldest message in the box has waited longer than
``unread_mail_threshold_s``, and ends when the box is empty. More mail during a spell adds
nothing, so each declared route hears one notice per spell, not one per message.

**The wait is counted in the recipient's own active time.** A message's wait starts at its
arrival or at the start of the session now running, whichever is later, and no spell starts
while the agent's declared session isn't running. Wall-clock age alone pages for an agent
that wasn't there to read, which is the alert storm ``amail.alerting`` records. An agent
that declares no session unit is counted on the wall clock.

Nothing is stored but what is written to the event log (MIS-0002-R16): a spell opens with
one ``pd_unread_mail`` and closes with one ``pd_unread_mail_cleared``. A restarted daemon
reads back whether a spell is open, so it never notices one twice. The notice goes to the
agent through the notifier where it is routed there; the outside watch reads the same
events and tells the operator where it is routed to them.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from macf.agent_events_log import append_event, read_events
from macf.pd.interface import EVENT_UNREAD_MAIL, EVENT_UNREAD_MAIL_CLEARED, UNREAD_MAIL_SOURCE
from macf.transcript_monitor.sources import STORE_SUFFIXES

#: ``active_since`` when the agent declares no session: every wait counts from arrival.
ALWAYS_ACTIVE = float("-inf")


def pickup_box(agent_home: Path) -> Path:
    return Path(agent_home) / "amail" / "pickup"


def unread_arrivals(box: Path) -> Optional[List[float]]:
    """The arrival times (mtimes) of the messages in *box*, or None when it can't be read.
    A box that doesn't exist yet is empty. Names and times only, never contents."""
    try:
        entries = list(os.scandir(box))
    except FileNotFoundError:
        return []
    except OSError as e:
        print(f"⚠️ MACF: pd: the pickup box can't be read, so unread mail can't be judged: {e}",
              file=sys.stderr)
        return None
    times = []
    for entry in entries:
        if not entry.name.endswith(STORE_SUFFIXES):
            continue
        try:
            times.append(entry.stat().st_mtime)
        except FileNotFoundError:
            continue        # ingested between the listing and the stat
    return times


def _spell_open(events: Iterable[dict], card: str) -> bool:
    """Whether the newest unread-mail event of *card* opened a spell (read newest first)."""
    for event in events:
        data = event.get("data") or {}
        if isinstance(data, dict) and data.get("agent") == card:
            return event.get("event") == EVENT_UNREAD_MAIL
    return False


@dataclass
class UnreadMail:
    """One pass at a time: ``tick(active_since)``, after ``boot``."""

    card: str
    threshold_s: float
    box: Path
    notice: Callable[[str, str], object]
    append: Callable[[str, dict], bool] = append_event
    wall: Callable[[], float] = time.time
    events: Callable[[], Iterable[dict]] = field(default=lambda: read_events(
        reverse=True, scope="all", only=(EVENT_UNREAD_MAIL, EVENT_UNREAD_MAIL_CLEARED)))
    in_spell: bool = False

    def boot(self) -> None:
        """Pick up a spell a previous daemon opened, so it isn't noticed a second time."""
        self.in_spell = _spell_open(self.events(), self.card)

    def tick(self, active_since: Optional[float]) -> None:
        """*active_since*: when the agent's running session started, ALWAYS_ACTIVE where it
        declares none, or None while its declared session isn't running."""
        arrivals = unread_arrivals(self.box)
        if arrivals is None:
            return                              # can't tell; the box said so
        if not arrivals:
            if self.in_spell:
                self.in_spell = False
                self._say(EVENT_UNREAD_MAIL_CLEARED, 0, 0.0, "the pickup box is empty")
            return
        if self.in_spell or active_since is None:
            return
        now = self.wall()
        waited = now - max(min(arrivals), active_since)
        if waited < self.threshold_s:
            return
        self.in_spell = True
        reason = (f"{len(arrivals)} message(s) unread; the oldest has waited {waited:.0f} s "
                  f"while the agent ran, past its threshold of {self.threshold_s:g} s")
        self._say(EVENT_UNREAD_MAIL, len(arrivals), waited, reason)
        self.notice(UNREAD_MAIL_SOURCE, f"unread-mail-{int(now)}")

    def _say(self, event: str, count: int, waited: float, reason: str) -> None:
        data = {"agent": self.card, "count": count, "waited_s": round(waited, 1), "reason": reason}
        if not self.append(event, data):
            print(f"⚠️ MACF: pd: the {event} event was not recorded: {reason}", file=sys.stderr)
