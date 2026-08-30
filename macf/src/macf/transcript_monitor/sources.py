"""Event sources that are not transcript lines.

The monitor's detectors take a parsed transcript entry and return a Detection.
That shape assumes the world arrives as a stream of lines. A mail store does
not: it is a directory whose contents change, with no stream and no cursor.

A Source is polled instead of fed. It is asked "what is new?" and answers with
Detections, so everything downstream — the event log, the delivery adapter —
stays unchanged.

`macf_tools policy navigate notification_delivery`
"""
import hashlib
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional, Set

from .daemon import Detection

#: Suffixes that count as a message in a pickup box.
STORE_SUFFIXES = (".eml", ".amsg")


class StoreSource:
    """Notice that a broker-owned store has gained entries.

    Reads NAMES ONLY, never contents. That is the zero-bandwidth property made
    structural rather than maintained: a source that never opens a message
    cannot leak a byte of one, so no rendering discipline has to be remembered
    and no future edit can quietly relax it.

    Edge-triggered on arrival identity. A store that still holds yesterday's
    unread mail is not a new event, and re-reporting it every poll would turn
    one arrival into an unbounded stream of notices.

    Authority stays with the store. This source reports only that the store
    CHANGED; what changed is answered by reading the store, which is the single
    action a resulting notice licenses.
    """

    def __init__(
        self,
        store_dir: Path,
        name: str = "amail",
        suffixes: tuple = STORE_SUFFIXES,
        seen: Optional[Set[str]] = None,
    ):
        self.store_dir = Path(store_dir)
        self.name = name
        self.suffixes = suffixes
        self._seen: Set[str] = set(seen or ())
        self._primed = False
        self.poll_failures = 0

    def _entry_ids(self) -> Optional[Set[str]]:
        """Current arrival identities, or None when the store cannot be read.

        None is distinct from the empty set: "no mail" and "cannot tell" are
        different facts, and treating the second as the first would report an
        unreadable store as a quiet one.
        """
        try:
            names = os.listdir(self.store_dir)
        except FileNotFoundError:
            # A store that does not exist yet is empty, not broken. Provisioning
            # creates it; polling ahead of that is ordinary.
            return set()
        except (PermissionError, OSError) as e:
            self.poll_failures += 1
            if self.poll_failures in (1, 10, 100, 1000):
                print(
                    f"⚠️ MACF: store unreadable ({self.poll_failures} consecutive), "
                    f"arrivals cannot be noticed: {e}",
                    file=sys.stderr,
                )
            return None
        self.poll_failures = 0
        return {n for n in names if n.endswith(self.suffixes)}

    def prime(self) -> "StoreSource":
        """Adopt the current contents as already-seen.

        Called once at startup so a daemon restart does not announce every
        message already sitting in the store. What was missed while the daemon
        was down is recovered from its gap record, not by replaying arrivals —
        replay would deliver a burst of stale wakes and re-notify mail the agent
        may already have read.
        """
        current = self._entry_ids()
        if current is not None:
            self._seen = current
        self._primed = True
        return self

    def poll(self) -> List[Detection]:
        """Return at most one Detection describing what is NEW since last poll.

        One Detection per poll, never one per message: a burst of ten arrivals
        is one thing the agent needs to know and one store to consult.
        """
        if not self._primed:
            self.prime()
            return []

        current = self._entry_ids()
        if current is None:
            return []

        fresh = current - self._seen
        # Departed entries are dropped from the ledger so a redelivered name is
        # a new arrival rather than a permanent silence.
        self._seen = current
        if not fresh:
            return []

        # An arrival id derived from the SET of new names: stable for the same
        # burst, different for any other, and carrying none of the names
        # themselves into anything downstream.
        digest = hashlib.sha256("\0".join(sorted(fresh)).encode()).hexdigest()[:16]
        return [Detection(
            event_name="store_arrival_detected",
            data={
                "source": self.name,
                "arrival_id": f"{self.name}-{digest}",
                "count": len(fresh),
                "store": str(self.store_dir),
            },
        )]


def agent_store_source(agent_home: Path, name: str = "amail") -> StoreSource:
    """A StoreSource over an agent's own pickup box."""
    return StoreSource(Path(agent_home) / "amail" / "pickup", name=name)


def notify_sink(deliver: Callable, session_id_of: Callable) -> Callable:
    """Turn a store Detection into a delivered notice.

    Kept separate from the source so the source stays testable without a live
    session, and so a second sink can be added without touching detection.
    """
    from ..notify.notice import amail_notice

    def sink(detection: Detection) -> Optional[object]:
        if detection.event_name != "store_arrival_detected":
            return None
        session_id = session_id_of()
        if not session_id:
            print(
                "⚠️ MACF: store arrival detected but this process cannot name its "
                "own conversation; no notice delivered",
                file=sys.stderr,
            )
            return None
        notice = amail_notice(
            arrival_id=detection.data["arrival_id"],
            count=detection.data.get("count"),
        )
        return deliver(session_id, notice)

    return sink
