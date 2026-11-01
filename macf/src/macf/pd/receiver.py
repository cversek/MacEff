"""The receiver: the primal daemon ingests its agent's mail, as its agent (MIS-0004 R04).

Before this, mail moved from the broker's pickup box into the agent's store only when the
agent ran ``amail list``. A notice named mail ``amail read`` couldn't find yet (R25), and an
agent waiting behind a prompt held its mail in the box, where nothing counted it as unread.
Here the daemon ingests each pass, through the same ``client.ingest`` the listing uses, so
the duplicate drop (R16) and the owner and link check (R37) stay in one code path, and the
store's lock keeps the two from ingesting at once.

Which box and whose contacts come from the agent's own ``.maceff/amail.json``, never the
environment: on a shared login every agent's daemon can reach every box, and a variable
naming another agent has already become a client's identity once (MIS-0002-R02's incident).
Without settings that name the agent, there is no receiver, and the daemon says so.

The first pass checks that the box can be listed and the store written. A refusal is a
notice (MIS-0002-R65 (denied_grant_MUST_raise_notice)), never an empty box that reads as
no mail: on macOS the daemon is a LaunchAgent whose privacy grants differ from the terminal
where ``amail list`` works, and in a container a daemon whose supplementary groups were
cleared loses a box it could reach only through one.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Dict, Optional, Set

#: How often the box is ingested. The notice follows the store, so this bounds how long an
#: arrival takes to become a notice; it doesn't affect correctness.
INGEST_S = 2.0
#: Contacts the receiver verifies signatures with when the settings name none: the broker's,
#: as `amail list` defaults them, but without its environment override.
DEFAULT_CONTACTS = "/var/lib/amail_broker/contacts.json"
#: The event one pass that moved anything writes.
EVENT_INGESTED = "pd_mail_ingested"
#: The notice a box or store the receiver can't use raises.
GRANT_SOURCE = "pd_grant_denied"


def receiver_settings(agent_home: Path) -> Optional[Dict[str, object]]:
    """``{"box", "agent", "contacts"}`` from the home's own amail settings, or None when they
    don't name the agent. The environment is never read."""
    from macf.amail.pickup import _settings, resolve_pickup_box
    cfg = _settings(Path(agent_home))
    if not cfg.get("agent"):
        return None
    # With no environment, the handoff is the settings' or the fixed default, never a variable.
    box, _how = resolve_pickup_box(Path(agent_home), env={})
    return {"box": box, "agent": str(cfg["agent"]),
            "contacts": Path(str(cfg.get("contacts") or DEFAULT_CONTACTS))}


class Receiver:
    """One pass at a time: ``tick(now)``."""

    def __init__(self, card: str, agent_home: Path, box: Path, agent: str, contacts: Path,
                 append: Callable[[str, dict], object], notice: Callable[[str, str], object]):
        self.card = card
        self.home = Path(agent_home)
        self.box = Path(box)
        self.agent = agent
        self.contacts = contacts
        self._append = append
        self._notice = notice
        self._next = float("-inf")
        self._checked = False
        self.refused: Optional[str] = None
        self._said: Set[str] = set()

    def tick(self, now: float) -> None:
        if now < self._next:
            return
        self._next = now + INGEST_S
        if not self._checked:
            self._checked = True
            self.refused = self._access()
            if self.refused:
                print(f"⚠️ MACF: pd: the receiver can't ingest {self.agent}'s mail, so none is "
                      f"ingested by this daemon: {self.refused}", file=sys.stderr)
                self._notice(GRANT_SOURCE, f"pd_grant_denied:amail-receiver:{int(now)}")
        if self.refused:
            return
        self.ingest()

    def ingest(self) -> None:
        from macf.amail.client import IngestBusy, ingest
        try:
            results = ingest(self.home, self.box, contacts_path=self.contacts,
                             agent=self.agent, wait=False)
        except IngestBusy:
            return  # noqa: MACEFF003 - `amail list` holds the lock and takes what is waiting; this pass tries again
        except OSError as e:
            if "ingest" not in self._said:
                self._said.add("ingest")
                print(f"⚠️ MACF: pd: ingesting {self.box} failed (tried again each pass): {e}",
                      file=sys.stderr)
            return
        self._said.discard("ingest")
        ingested = [r for r in results if r.get("ingested")]
        refused = [r for r in results if r.get("refused")]
        duplicates = [r for r in results if r.get("duplicate")]
        stuck = [r for r in results
                 if not r.get("ingested") and not (r.get("refused") or r.get("duplicate") or r.get("taken"))]
        for r in stuck:
            # An entry ingest can't take stays in the box and is met every pass; say it once.
            if r["name"] not in self._said:
                self._said.add(r["name"])
                print(f"⚠️ MACF: pd: pickup entry {r['name']} not ingested: {r['reason']}",
                      file=sys.stderr)
        if ingested or refused or duplicates:
            self._append(EVENT_INGESTED, {"agent": self.card, "box": str(self.box),
                                          "ingested": len(ingested), "refused": len(refused),
                                          "duplicates": len(duplicates),
                                          "stuck": sorted(r["name"] for r in stuck)})

    def _access(self) -> Optional[str]:
        """Why the box can't be listed or the store written, or None when both can."""
        try:
            os.listdir(self.box)
        except FileNotFoundError:
            return None  # noqa: MACEFF003 - not made yet, which refuses nothing: the broker creates it with the first mail
        except OSError as e:
            return f"the pickup box {self.box} can't be listed ({e.strerror}){self._group_hint()}"
        try:
            from macf.amail.store import ensure_maildir
            new = ensure_maildir(self.home) / "new"
        except OSError as e:
            return f"the store under {self.home} can't be made ({e})"
        if not os.access(new, os.W_OK):
            return f"the store's {new} isn't writable by this daemon"
        return None

    def _group_hint(self) -> str:
        """Name the case a container meets: the box's group reachable only as a supplementary
        group, which a daemon started with its groups cleared doesn't have."""
        try:
            gid = os.stat(self.box).st_gid
        except OSError:
            return ""
        if gid != os.getgid() and gid not in os.getgroups():
            return (f"; the box's group {gid} is neither this daemon's primary group nor one of its "
                    f"groups, so it should be the agent's primary group")
        return ""
