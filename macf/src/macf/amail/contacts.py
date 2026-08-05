"""Contact lists — who an agent is permitted to send to.

Two rules from the amail policy are enforced here rather than documented:

1. A contact entry names a correspondent and NEVER records how to reach one.
   Reachability is runtime state; encoding it in configuration means every
   topology change becomes an edit to every contact list, and guarantees drift.
   Any entry carrying a host/transport hint is rejected at load.

2. Changes take effect without a rebuild — the list is read from disk per
   decision, not cached at process start.

What this does NOT control is as important as what it does: it bounds the
RECIPIENT SET, not the content. An agent induced to disclose something can still
disclose it to a permitted correspondent.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


class ContactListError(ValueError):
    """Raised when a contact list is malformed. Never fall back to permissive."""


# Keys that would encode a route rather than an identity.
_ROUTE_KEYS = {"host", "hostname", "transport", "via", "route", "network", "tailnet", "relay"}


class ContactBook:
    """Per-agent contact lists, loaded fresh on every check."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> Dict[str, List[str]]:
        if not self.path.exists():
            # Fail closed. An absent contact list is not an empty restriction;
            # it means the deployment is not configured, and sending under that
            # condition is exactly what the allowlist exists to prevent.
            raise ContactListError(
                f"contact list not found at {self.path} — refusing to send with no policy"
            )
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError) as e:
            raise ContactListError(f"contact list at {self.path} is unreadable: {e}") from e

        if not isinstance(raw, dict):
            raise ContactListError("contact list must be an object of agent -> [addresses]")

        book: Dict[str, List[str]] = {}
        for agent, entries in raw.items():
            if not isinstance(entries, list):
                raise ContactListError(f"contacts for '{agent}' must be a list")
            addrs: List[str] = []
            for e in entries:
                if isinstance(e, dict):
                    offending = _ROUTE_KEYS & {k.lower() for k in e}
                    if offending:
                        raise ContactListError(
                            f"contact entry for '{agent}' records reachability "
                            f"({', '.join(sorted(offending))}). A contact names a "
                            "correspondent, never a route — the broker decides how "
                            "to deliver at send time."
                        )
                    if "address" not in e:
                        raise ContactListError(f"contact entry for '{agent}' has no address")
                    addrs.append(str(e["address"]).strip().lower())
                elif isinstance(e, str):
                    addrs.append(e.strip().lower())
                else:
                    raise ContactListError(f"contact entry for '{agent}' must be a string or object")
            book[agent] = addrs
        return book

    def contacts_for(self, agent: str) -> List[str]:
        return self._load().get(agent, [])

    def permits(self, agent: str, recipient: str) -> bool:
        """True when `agent` may send to `recipient`.

        Case-insensitive on the address, because mail addresses are, and a
        restriction that can be stepped around by capitalising a letter is not one.
        """
        return recipient.strip().lower() in self.contacts_for(agent)

    def refuse_reason(self, agent: str, recipient: str) -> Optional[str]:
        """None when permitted; otherwise a message the agent can act on.

        Refusals are returned rather than swallowed: an agent that cannot tell a
        message was refused learns to believe mail was delivered.
        """
        if self.permits(agent, recipient):
            return None
        known = self.contacts_for(agent)
        if not known:
            return f"'{agent}' has no contacts declared; every recipient is refused"
        return (
            f"'{recipient}' is not in the contact list for '{agent}' "
            f"({len(known)} permitted)"
        )
