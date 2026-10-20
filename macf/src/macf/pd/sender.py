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

**The runner** (``python -m macf.pd.sender --config <path>``) is one pass, run by its own timer
outside every session, as the outside watch is, with the watch's kind of ``alert_command``: it
receives the message on stdin and holds its own credential (MIS-0002-R75). Its ledger is its own
file. Each send is written there as ``sending`` before the command runs and with its outcome
after. A send the command refused is tried again on the next pass. One whose outcome was never
written, because the sender died while sending, counts as sent: a duplicate on the operator's
phone is worse than one reminder lost, and the lost one is in the ledger to be found.
"""
import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Literal, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from macf.pd import interface
from macf.pd.entries import ENTRY_EVENTS, OneShot, fold, parse_when
from macf.utils.streaming import iter_lines_forward

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


def due_sends(entries: Iterable[dict], sent: Iterable[str], now: datetime,
              quiet_until: Callable[[datetime], Optional[datetime]] = lambda _now: None,
              sent_today: Optional[Dict[str, int]] = None, bound: int = DAILY_BOUND) -> List[Send]:
    """The sends due at ``now``, in the entries' order, none whose id is in ``sent``.

    ``quiet_until(now)`` is the end of the quiet window ``now`` falls in, or None; ``sent_today``
    counts each owner's sends today. Only the newest instant due is offered, so the ledger's ids
    alone say what was sent."""
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
        since = datetime.fromisoformat(entry.get("accepted_at") or entry["start"]) - timedelta(seconds=1)
        due = _newest_due(entry, since, now)
        if due is None:
            continue
        late = (now - due).total_seconds() > LATE_S
        text = (f"Late, due {due.isoformat()}: " if late else "") + entry.get("purpose", "")
        offer(entry, Send(f"{entry['id']}@{int(due.timestamp())}", owner, text))
    return out


# ---------------------------------------------------------------------- the runner

SEND_TIMEOUT_S = 30
LEDGER = "sent.jsonl"


class SenderConfig(BaseModel):
    """The homes whose entries the sender reads, the command that reaches the operator, and
    where its ledger lives. Rendered at install, never kept by hand."""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    homes: List[str]
    alert_command: List[str] = Field(min_length=1)
    state_dir: str = Field(min_length=1)
    daily_bound: int = Field(default=DAILY_BOUND, ge=1)


def read_entries(home: Path) -> List[dict]:
    """The entries an agent home holds, folded from its own event log."""
    card = interface.agent_card(home)
    names = tuple(f'"{name}"' for name in ENTRY_EVENTS)
    events = []
    try:
        for line in iter_lines_forward(home / ".maceff" / "agent_events_log.jsonl"):
            if any(name in line for name in names):
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue  # noqa: MACEFF003 - a torn line is no event: the fold skips it
    except FileNotFoundError:
        return []
    return list(fold(events, card).values())


def read_ledger(path: Path, today: str) -> Tuple[Set[str], Dict[str, int]]:
    """What was sent: the ids not to send again, and each owner's sends today. An id's newest
    record decides it, and only a refusal frees it."""
    state: Dict[str, dict] = {}
    try:
        for line in iter_lines_forward(path):
            try:
                record = json.loads(line)
            except ValueError:
                continue  # noqa: MACEFF003 - a torn last line: the record before it stands
            state[record["id"]] = record
    except FileNotFoundError:
        pass
    sent, today_counts = set(), {}
    for send_id, record in state.items():
        if record.get("state") == "failed":
            continue
        sent.add(send_id)
        if record.get("day") == today:
            today_counts[record["owner"]] = today_counts.get(record["owner"], 0) + 1
    return sent, today_counts


def _write(path: Path, record: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
        fh.flush()


def deliver(alert_command: List[str], send: Send, ledger: Path, day: str) -> bool:
    """Send one message, recorded as sending before the command runs and with its outcome after.
    The command's own output is never echoed, since a transport error can carry its URL."""
    base = {"id": send.id, "owner": send.owner, "day": day}
    _write(ledger, {**base, "state": "sending", "ts": time.time()})
    header = "MacEff: an entry waits for you" if send.id.endswith("@accept") else f"MacEff reminder from {send.owner}"
    try:
        result = subprocess.run(list(alert_command), input=f"{header}\n{send.text}\n", text=True,
                                capture_output=True, timeout=SEND_TIMEOUT_S)
        ok, outcome = result.returncode == 0, f"exit {result.returncode}"
    except (OSError, subprocess.TimeoutExpired) as e:
        ok, outcome = False, type(e).__name__
    _write(ledger, {**base, "state": "sent" if ok else "failed", "outcome": outcome, "ts": time.time()})
    if not ok:
        print(f"MacEff sender: {send.id} was not sent ({outcome}); it is tried again next pass", file=sys.stderr)
    return ok


def run_pass(config: SenderConfig, now: Optional[datetime] = None) -> int:
    """One pass: send what is due across every home, and say how many went."""
    now = now or datetime.now(timezone.utc)
    state = Path(config.state_dir)
    state.mkdir(parents=True, exist_ok=True)
    ledger, day = state / LEDGER, now.date().isoformat()
    sent, today = read_ledger(ledger, day)
    entries = [e for home in config.homes for e in read_entries(Path(home))]
    sends = due_sends(entries, sent, now, sent_today=today, bound=config.daily_bound)
    return sum(deliver(config.alert_command, s, ledger, day) for s in sends)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m macf.pd.sender",
                                     description="One pass of the sender: what is due goes to the operator.")
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        config = SenderConfig.model_validate_json(args.config.read_text())
    except (OSError, ValidationError, ValueError) as e:
        print(f"MacEff sender: the config {args.config} cannot be used: {type(e).__name__}", file=sys.stderr)
        return 2
    run_pass(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
