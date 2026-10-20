"""Duties on the primal daemon: a duty's crossing into DUE_SOON or OVERDUE wakes the agent
(the scheduler design, 4.4).

The roles' ``DutyTierSource`` reports each crossing once, but it kept nothing, and nothing hosted
it, so a duty that fell due while the session was idle was heard of only at the next tool call,
and one that crossed while no daemon ran was never reported. Here the daemon polls it, writes each
crossing to the event log before raising ``pd_duty_due``, and at a start reads back the crossings
it already announced, so one that happened while it was down is announced once, and none twice.
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional, Set, Tuple

from macf.roles.priority import TIER_NAMES
from macf.roles.source import EVENT, DutyTierSource
from macf.roles.store import RoleStore

#: The notice a duty's crossing raises.
NOTICE_DUTY_DUE = "pd_duty_due"
#: The name the daemon's crossings carry as their source, apart from any other poller's.
SOURCE = "pd"
#: How often the roles store is read.
POLL_S = 60.0


class HostedDuties:
    def __init__(self, card: str, roles: Path, append: Callable[[str, dict], object],
                 events: Callable[[], Iterable[dict]], on_notice: Optional[Callable[[str, str], object]],
                 clock: Callable[[], float]):
        self.card, self.roles, self.append, self.events = card, roles, append, events
        self.on_notice, self.clock = on_notice, clock
        self.source: Optional[DutyTierSource] = None
        self.last_poll: Optional[float] = None
        self.failed: Optional[str] = None

    def announced(self) -> Set[Tuple[str, int, str]]:
        """The crossings this agent's daemon already announced, as the source keys them."""
        seen = set()
        for event in self.events():
            data = event.get("data") or {}
            if event.get("event") == EVENT and data.get("source") == SOURCE and data.get("agent") == self.card \
                    and data.get("tier") in TIER_NAMES:
                seen.add((data.get("duty_id"), TIER_NAMES.index(data["tier"]), data.get("entered")))
        return seen

    def boot(self) -> None:
        # Not primed: what is in a tier now and was never announced crossed while no daemon ran.
        self.source = DutyTierSource(RoleStore(self.roles), name=SOURCE, seen=self.announced(), prime=False)

    def tick(self, at: Optional[datetime] = None) -> None:
        now = self.clock()
        if self.source is None or (self.last_poll is not None and now - self.last_poll < POLL_S):
            return
        self.last_poll = now
        try:
            detections = self.source.poll(at)
        except Exception as e:  # noqa: BLE001 - a roles store that won't read must not end the daemon
            said = f"{type(e).__name__}: {e}"
            if said != self.failed:
                self.failed = said
                print(f"⚠️ MACF: pd: the roles store couldn't be read for duties ({said})", file=sys.stderr)
            return
        self.failed = None
        for d in detections:
            self.append(EVENT, {**d.data, "agent": self.card})       # recorded before it is raised
            if self.on_notice is not None:
                self.on_notice(NOTICE_DUTY_DUE, d.data["arrival_id"])
