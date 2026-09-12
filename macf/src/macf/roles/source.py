"""A polled Source over roles x duties: the out-of-session half of the duty nag.

The in-session half (``roles.hooks.conscientiousness_nag``) reads the tiers
on every tool call. This reads the same tiers from outside the session --
polled by whatever long-lived process hosts it (today the transcript
monitor's ``add_source``; tomorrow the hypervisor's notifier) -- and reports
a crossing into DUE_SOON or OVERDUE as one Detection, edge-triggered on
(duty id, tier, entry time), so a duty that stays overdue is one event, not
one per poll. Names only: a Detection carries the duty's id and tier, never
its body, so the notice it becomes stays content-free and the agent consults
the roles store, which is the single action a notice licenses.

Where this runs is a deployment decision, not this module's: it has no
process, no timer and no transport. ``macf_tools policy navigate
notification_delivery`` for what may be delivered; the roles policy for the
tiers.
"""
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from .priority import DUE_SOON, OVERDUE, now, rank
from .store import RoleStore


class Detection:
    """Mirror of the monitor's Detection so this module imports nothing from it."""
    __slots__ = ("event_name", "data")

    def __init__(self, event_name: str, data: dict):
        self.event_name = event_name
        self.data = data


EVENT = "duty_tier_crossed"


class DutyTierSource:
    """Report each duty's entry into DUE_SOON or OVERDUE, once."""

    def __init__(self, store: Optional[RoleStore] = None, name: str = "roles",
                 seen: Optional[Set[Tuple[str, int, str]]] = None, prime: bool = True):
        self.store = store
        self.name = name
        self._seen: Set[Tuple[str, int, str]] = set(seen or ())
        self._primed = not prime      # prime=True: the first poll records, never reports
        self.poll_failures = 0

    def _store(self) -> RoleStore:
        return self.store or RoleStore()

    def _current(self, at: datetime) -> Dict[Tuple[str, int, str], dict]:
        """Every (duty, tier, entered) currently in a due-now tier, with its facts."""
        out: Dict[Tuple[str, int, str], dict] = {}
        store = self._store()
        focused = None
        try:
            from .focus import current_focus
            focused = current_focus()
        except OSError:
            pass    # no events log: nothing is focused
        for role, folder in store.roles():
            if role.state != "active":
                continue
            duties = [d for d, _ in store.duties(folder)]
            for p in rank(duties, at, role.expires):
                if p.tier not in (OVERDUE, DUE_SOON) or p.entered is None:
                    continue
                key = (p.duty.id, p.tier, p.entered.isoformat())
                out[key] = {"source": self.name, "duty_id": p.duty.id, "role_id": role.id,
                            "tier": p.tier_name, "entered": p.entered.isoformat(),
                            "occurrence": p.occurrence.isoformat() if p.occurrence else None,
                            "role_focused": role.id == focused,
                            "arrival_id": f"{self.name}-{p.duty.id}-{p.tier_name}-{p.entered:%Y%m%dT%H%M}"}
        return out

    def poll(self, at: Optional[datetime] = None) -> List[Detection]:
        at = at or now()
        current = self._current(at)
        if not self._primed:
            # First poll after start: everything already in a tier is old news
            # the agent has seen in its tree; report only what crosses from here.
            self._seen = set(current)
            self._primed = True
            return []
        fresh = [k for k in current if k not in self._seen]
        # Forget keys that left their tier (serviced, done, deferred, or the
        # occurrence moved on), so a later re-entry is a new crossing.
        self._seen = set(current)
        return [Detection(EVENT, current[k]) for k in sorted(fresh)]
