"""What the sender sends the operator, and when (the scheduler design, 4.3 and 5.5).

The sender is the only path to the operator. This module is its decision, pure over what it's
given: the entries it can read, what its ledger says it already sent, the time, and the quiet
hours. The runner around it reads the stores, sends, and keeps the ledger.

**Exactly once.** Each send has an idempotent id: an entry's id and the instant it's for, or the
entry's id and ``accept`` for the push asking the operator to accept it. An id in the ledger is
never sent again. A reminder missed while nothing ran is sent once, late, saying so, for its
newest instant only.

**What may be sent.**
- An entry the operator owns, or one the operator accepted: its purpose, the agent's text.
- An entry that waits for acceptance: a fixed template naming its id, its owner, when it was made
  and why it waits. Never its text, so an agent can't put words on the operator's phone before
  the operator has read them where they're stored.

**Quiet hours.** A send due inside a quiet window is held to the window's end, unless its entry
is urgent.

**Rate.** Each owner may cause a bounded number of sends a day. Past the bound, the sender sends
one fixed line saying so, once that day, and holds the rest.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from macf.pd.entries import OneShot, parse_when

#: A reminder sent more than this late says so.
LATE_S = 60
#: Sends an owner may cause in a day, by default.
DAILY_BOUND = 24


@dataclass(frozen=True)
class Send:
    id: str        # the idempotent id the ledger keeps
    owner: str
    text: str


def _when(entry: dict):
    tz = timezone.utc if entry.get("zone") in (None, "UTC") else ZoneInfo(entry["zone"])
    start = datetime.fromisoformat(entry["start"])
    try:
        return OneShot(datetime.fromisoformat(entry["when"])), start
    except ValueError:
        return parse_when(entry["when"], tz, start, start=start), start


def _newest_due(entry: dict, after: datetime, now: datetime) -> Optional[datetime]:
    """The newest instant of ``entry`` in (after, now], or None."""
    when, _ = _when(entry)
    due = when.next_after(after)
    if due is None or due > now:
        return None
    for _ in range(10000):
        later = when.next_after(due)
        if later is None or later > now:
            break
        due = later
    return due


def _accept_text(entry: dict) -> str:
    why = "; ".join(entry.get("marked") or []) or "it's a reminder"
    return (f"{entry.get('agent')} made entry {entry['id']} at {entry.get('start')}. It waits for your "
            f"acceptance ({why}). Read it with: macf_tools pd entry show {entry['id']}")


def due_sends(entries: Iterable[dict], sent: Iterable[str], last_sent: Dict[str, datetime], now: datetime,
              quiet_until: Callable[[datetime], Optional[datetime]] = lambda _now: None,
              sent_today: Optional[Dict[str, int]] = None, bound: int = DAILY_BOUND) -> List[Send]:
    """The sends due at ``now``, in the entries' order, none whose id is in ``sent``.

    ``last_sent`` is each entry's newest instant already sent; ``quiet_until(now)`` is the end of
    the quiet window ``now`` falls in, or None; ``sent_today`` counts each owner's sends today."""
    sent, counts = set(sent), dict(sent_today or {})
    held = quiet_until(now)
    out: List[Send] = []

    def offer(entry: dict, send: Send) -> None:
        if send.id in sent:
            return
        if held is not None and entry.get("quiet") != "urgent":
            return
        owner = send.owner
        if counts.get(owner, 0) >= bound:
            line = f"rate:{owner}:{now.date().isoformat()}"
            if line not in sent:
                sent.add(line)
                out.append(Send(line, owner, f"{owner} has reached its {bound} messages for today; "
                                             f"the rest wait until tomorrow."))
            return
        counts[owner] = counts.get(owner, 0) + 1
        sent.add(send.id)
        out.append(send)

    for entry in entries:
        owner = entry.get("agent") or "operator"
        if entry.get("state") == "waiting":
            offer(entry, Send(f"{entry['id']}@accept", owner, _accept_text(entry)))
            continue
        if entry.get("action") != "remind" or entry.get("state") not in (None, "active"):
            continue
        if owner != "operator" and not entry.get("accepted_at"):
            continue                                         # never the agent's text unaccepted
        since = last_sent.get(entry["id"]) or datetime.fromisoformat(
            entry.get("accepted_at") or entry["start"]) - timedelta(seconds=1)
        due = _newest_due(entry, since, now)
        if due is None:
            continue
        late = (now - due).total_seconds() > LATE_S
        text = (f"Late, due {due.isoformat()}: " if late else "") + entry.get("purpose", "")
        offer(entry, Send(f"{entry['id']}@{int(due.timestamp())}", owner, text))
    return out
