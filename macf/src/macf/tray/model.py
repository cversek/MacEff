"""What the tray shows and what it asks for, without drawing anything.

One icon for every agent installed on the host, with one menu entry per agent keyed
by its calling card. The icon shows the most urgent status across the entries, and the
menu names the agents that caused it. This is the form the operator chose on
2026-10-09 ("one tray icon with a pulldown menu showing calling cards and status per
agent ... alert by unioning statuses"); it is written against the amendment of
MIS-0002-R69 (tray_MUST_show_icon_per_agent) and R72 (tray_MUST_flag_waiting_on_person)
that the Secretary carries, and follows whatever wording that amendment lands with.

The tray only observes and asks. Every start, stop or restart becomes a request to that
agent's primal daemon naming the operator as the asker (MIS-0002-R70
(tray_MUST_act_through_pd)); nothing here can type into a session (R71).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

#: The order of urgency for the union, most urgent first. ``unreachable`` is the tray's
#: own: the agent's primal daemon did not answer, so its units' states are unknown, and
#: that outranks every state a daemon can report except a failure.
URGENCY = ("failed", "unreachable", "waiting_on_a_person", "starting", "running", "stopped", "declared")
_RANK = {s: i for i, s in enumerate(URGENCY)}

#: The states that make the icon alert, as opposed to merely showing a state.
ALERTING = ("failed", "unreachable", "waiting_on_a_person")

#: The acts an entry offers (MIS-0002-R70). Compaction is not one: only the operator's
#: own command or the agent's wind-down asks for it (MIS-0002-R108).
ACTS = ("start", "stop", "restart")


def most_urgent(states: Iterable[str]) -> Optional[str]:
    """The most urgent of ``states``, or None for none. An unknown state counts as unreachable."""
    ranked = [s if s in _RANK else "unreachable" for s in states]
    if not ranked:
        return None
    return min(ranked, key=_RANK.__getitem__)


@dataclass(frozen=True)
class Entry:
    """One agent's line in the menu."""

    card: str
    status: Optional[str]
    units: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def label(self) -> str:
        if self.status is None:
            return f"{self.card}: no units"
        return f"{self.card}: {self.status.replace('_', ' ')}"


def entry(card: str, response: Optional[dict]) -> Entry:
    """An agent's entry from its primal daemon's status response.

    ``response`` is the daemon's ``Response`` as a dict (``ok``, ``error``, ``units``), or
    None when the socket could not be reached. Either failure is ``unreachable``, with
    the reason kept for the menu; a daemon that answers with no units has no status.
    """
    if response is None:
        return Entry(card, "unreachable", error="the primal daemon did not answer")
    if not response.get("ok"):
        return Entry(card, "unreachable", error=response.get("error") or "the primal daemon refused the status request")
    units = {u["unit"]: u["state"] for u in response.get("units") or []}
    return Entry(card, most_urgent(units.values()), units=units)


@dataclass(frozen=True)
class TrayState:
    """The icon's state, the agents that caused it, and the menu entries."""

    icon: Optional[str]
    alerting: bool
    caused_by: List[str]
    entries: List[Entry]


def union(entries: Iterable[Entry]) -> TrayState:
    """One icon over all agents: the most urgent entry status, and who has it.

    Entries are keyed by card and sorted by it, so the menu reads the same from one
    poll to the next. Two entries for one card is a broken install, not a union, and
    is refused.
    """
    by_card: Dict[str, Entry] = {}
    for e in entries:
        if e.card in by_card:
            raise ValueError(f"two agents claim the calling card {e.card!r}")
        by_card[e.card] = e
    ordered = [by_card[c] for c in sorted(by_card)]
    icon = most_urgent(e.status for e in ordered if e.status is not None)
    caused_by = [e.card for e in ordered if icon is not None and e.status == icon]
    return TrayState(icon=icon, alerting=icon in ALERTING, caused_by=caused_by, entries=ordered)


def act_request(act: str, unit: str, reason: str = "asked from the tray") -> str:
    """The control-socket line for an act an entry offers, asked by the operator.

    One JSON object per line, in the primal daemon's request shape. The tray sends it to
    that agent's control socket and nowhere else.
    """
    if act not in ACTS:
        raise ValueError(f"the tray offers {', '.join(ACTS)}, not {act!r}")
    if not unit:
        raise ValueError("an act names its unit")
    return json.dumps({"op": act, "unit": unit, "asked_by": {"kind": "operator"}, "reason": reason})
