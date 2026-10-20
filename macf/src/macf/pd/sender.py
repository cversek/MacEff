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

**The brief** (5.5) is the operator's, declared once in the sender's config with its times, such as
morning and evening. Its text is the agent's by design: the agent writes it to its brief spool,
``.maceff/brief/`` in its home, and at each brief time the sender sends the newest brief written
since the previous one, under a fixed header naming the agent. The agent needn't know the times. If
none has arrived ``brief_grace_min`` after its time, the sender sends a plain agenda instead, built
from the entries alone, with no text the operator hasn't accepted. Brief and agenda share one id per
brief time, so the operator gets one or the other, late once if need be, never both.

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
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Literal, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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


DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


class QuietWindow(BaseModel):
    """The operator's quiet hours, ``HH:MM`` to ``HH:MM`` in the sender's timezone, on the days
    named, each the day the window starts. One whose end comes before its start runs past
    midnight."""

    model_config = ConfigDict(extra="forbid")
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days: List[Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]] = Field(default_factory=lambda: list(DAYS))


class SenderConfig(BaseModel):
    """The homes whose entries the sender reads, the command that reaches the operator, where
    its ledger lives, and the operator's quiet hours: windows by weekday, and whole days by date.
    Rendered at install, never kept by hand."""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    homes: List[str]
    alert_command: List[str] = Field(min_length=1)
    state_dir: str = Field(min_length=1)
    daily_bound: int = Field(default=DAILY_BOUND, ge=1)
    timezone: str = "UTC"
    quiet: List[QuietWindow] = Field(default_factory=list)
    quiet_dates: List[str] = Field(default_factory=list)   # YYYY-MM-DD, quiet all day
    briefs: List[str] = Field(default_factory=list)       # HH:MM, each a brief time
    brief_grace_min: int = Field(default=30, ge=0)

    @model_validator(mode="after")
    def _brief_times(self) -> "SenderConfig":
        bad = [t for t in self.briefs if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t)]
        if bad:
            raise ValueError(f"brief times are HH:MM: {', '.join(bad)}")
        return self


def brief_dir(home: Path) -> Path:
    return home / ".maceff" / "brief"


def brief_name(written: datetime) -> str:
    """A spool file's name: the instant it was written, in UTC, so names sort as times do."""
    return written.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".md"


def _written(path: Path) -> Optional[datetime]:
    try:
        return datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None  # noqa: MACEFF003 - a spool file not named by its write time is no brief: it's skipped


def plain_agenda(card: str, entries: Iterable[dict], now: datetime) -> str:
    """The day's agenda from the entries alone: what fires in the next day, and what waits. An
    entry's purpose is shown only once accepted, or when the operator owns it."""
    lines, waiting = [], []
    for entry in entries:
        if entry.get("state") == "waiting":
            waiting.append(entry["id"])
            continue
        if entry.get("state") not in (None, "active"):
            continue
        when, _ = _when(entry)
        nxt = when.next_after(now)
        if nxt is None or nxt > now + timedelta(days=1):
            continue
        shown = entry.get("purpose", "") if entry.get("accepted_at") or entry.get("agent") == "operator" else ""
        lines.append((nxt, f"{nxt.isoformat()}  {entry.get('action', 'wake')}  {entry['id']}  {shown}".rstrip()))
    out = [text for _, text in sorted(lines)] or ["nothing scheduled in the next day"]
    if waiting:
        out.append(f"waiting for your acceptance: {', '.join(waiting)}")
    return "\n".join(out)


def _slots(config: "SenderConfig", now: datetime) -> Tuple[Optional[datetime], Optional[datetime]]:
    """The newest brief time at or before ``now``, and the one before it, in the sender's zone."""
    tz = ZoneInfo(config.timezone)
    local = now.astimezone(tz)
    times = sorted(config.briefs)
    every = [datetime.combine(local.date() + timedelta(days=d), datetime.min.time(), tz).replace(
        hour=int(t[:2]), minute=int(t[3:])) for d in (-1, 0) for t in times]
    past = [t for t in every if t <= local]
    return (past[-1], past[-2]) if len(past) >= 2 else (past[-1] if past else None, None)


def brief_send(config: "SenderConfig", card: str, home: Path, entries: List[dict], sent: Set[str],
               now: datetime) -> Optional[Send]:
    """The brief due at the latest brief time or, past its grace, the plain agenda; None when
    neither is due. The brief is the newest the agent wrote since the brief time before."""
    due, before = _slots(config, now)
    if due is None:
        return None
    send_id = f"brief:{card}:{due.strftime('%Y-%m-%dT%H:%M')}"
    if send_id in sent:
        return None
    since = before or due - timedelta(days=1)
    written = sorted((w, p) for p in brief_dir(home).glob("*.md") if (w := _written(p)) and since < w <= now)
    if written:
        return Send(send_id, card, written[-1][1].read_text())
    if now < due + timedelta(minutes=config.brief_grace_min):
        return None
    return Send(send_id, card, "No brief arrived; the plain agenda follows.\n" + plain_agenda(card, entries, now))


def quiet_until(config: SenderConfig, now: datetime) -> Optional[datetime]:
    """The end of the quiet window or day ``now`` falls in, or None when it falls in none."""
    tz = ZoneInfo(config.timezone)
    local = now.astimezone(tz)
    today, hhmm = local.date(), local.strftime("%H:%M")
    if today.isoformat() in config.quiet_dates:
        return datetime.combine(today + timedelta(days=1), datetime.min.time(), tz)

    def at(day, text):
        hour, minute = map(int, text.split(":"))
        return datetime.combine(day, datetime.min.time(), tz).replace(hour=hour, minute=minute)
    yesterday = today - timedelta(days=1)
    for w in config.quiet:
        on = DAYS[today.weekday()] in w.days
        if w.start <= w.end:
            if on and w.start <= hhmm < w.end:
                return at(today, w.end)
        elif on and hhmm >= w.start:
            return at(today + timedelta(days=1), w.end)
        elif DAYS[yesterday.weekday()] in w.days and hhmm < w.end:
            return at(today, w.end)
    return None


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
    header = ("MacEff: an entry waits for you" if send.id.endswith("@accept")
              else f"MacEff daily brief from {send.owner}" if send.id.startswith("brief:")
              else f"MacEff reminder from {send.owner}")
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
    held = quiet_until(config, now)
    sends, entries = [], []
    for home in map(Path, config.homes):
        mine = read_entries(home)
        entries += mine
        brief = brief_send(config, interface.agent_card(home), home, mine, sent, now) if held is None else None
        if brief is not None:
            sends.append(brief)
    sends += due_sends(entries, sent, now, quiet_until=lambda t: quiet_until(config, t),
                       sent_today=today, bound=config.daily_bound)
    return sum(deliver(config.alert_command, s, ledger, day) for s in sends)


def render_systemd(config_path: Path, every_s: int = 60, python: str = sys.executable) -> Dict[str, str]:
    """The Linux user units: a oneshot service and its timer. The sender is its own process on its
    own timer, outside every session and every daemon, so a reminder goes while both are down.
    Installing them is the operator's act, with an alert command the operator chooses."""
    service = (
        "[Unit]\n"
        "Description=MacEff sender: reminders and the brief to the operator\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={python} -m macf.pd.sender --config {config_path}\n"
    )
    timer = (
        "[Unit]\n"
        "Description=Run the MacEff sender\n\n"
        "[Timer]\n"
        f"OnBootSec={every_s}\n"
        f"OnUnitActiveSec={every_s}\n"
        "AccuracySec=5\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    return {f"{interface.PD_IDENTIFIER}_sender.service": service,
            f"{interface.PD_IDENTIFIER}_sender.timer": timer}


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
