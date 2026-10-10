"""After an injected /compact, type one recovery prompt once the compaction has finished.

A compaction opens no turn, and nothing a SessionStart hook returns can open one. An agent
that compacts itself with ``macf_tools inject compact`` as the last act of a wind-down
therefore sits at an empty input box after the compaction, its recovery unread, until
something else happens to wake it. Observed twice in one day on one host: the host agent
woke only because a scheduled check-in fired, a seat only because its herder mailed it.

``inject compact`` cannot wait for the compaction itself: the queued ``/compact`` runs only
after the turn that queued it ends. So it starts this follower, detached, which watches the
agent's own event log and types one prompt into the same pane when it is safe to:

- **send** once a ``compaction_detected`` newer than the injection is in the log and
  ``SETTLE_SECONDS`` have passed since it, so the SessionStart hook has finished;
- **skip** if a new prompt started after the compaction (a mail clock, a cron or the
  operator got there first): the agent is already awake, and a second prompt would collide;
- **give up** after ``TIMEOUT_SECONDS`` with no compaction (the ``/compact`` never ran).

It exits after one decision. It types only text written by the framework, never text from
a message or a file, so it cannot carry anyone else's words into the session.
"""
import argparse
import sys
import time
from typing import Callable, Iterable, Optional

DEFAULT_TEXT = ("🏗️ MACF | The compaction you queued with inject compact has finished. "
                "Run your recovery now: follow the recovery instructions above.")
SETTLE_SECONDS = 5.0
TIMEOUT_SECONDS = 1800.0
POLL_SECONDS = 2.0
PROMPT_EVENT = "dev_drv_started"
COMPACTION_EVENT = "compaction_detected"


def decide(events: Iterable[dict], since: float, now: float,
           settle: float = SETTLE_SECONDS) -> str:
    """'wait', 'send' or 'skip', from the events at or after *since* (any order)."""
    rows = sorted((e for e in events if (e.get("timestamp") or 0) >= since),
                  key=lambda e: e.get("timestamp") or 0)
    compaction = next((e for e in rows if e.get("event") == COMPACTION_EVENT), None)
    if compaction is None:
        return "wait"
    at = compaction["timestamp"]
    if any(e.get("event") == PROMPT_EVENT and e["timestamp"] > at for e in rows):
        return "skip"
    return "send" if now - at >= settle else "wait"


def _events_since(since: float) -> list:
    from .agent_events_log import read_events
    out = []
    for e in read_events(reverse=True):          # cycle scope: ends at the newest compaction
        if (e.get("timestamp") or 0) < since:
            break
        out.append(e)
    return out


def follow(target: str, since: float, text: str = DEFAULT_TEXT, *,
           timeout: float = TIMEOUT_SECONDS, poll: float = POLL_SECONDS,
           read: Callable[[float], list] = _events_since,
           send: Optional[Callable[[str, list], int]] = None,
           clock: Callable[[], float] = time.time,
           sleep: Callable[[float], None] = time.sleep) -> str:
    """Wait for the compaction, then send, skip, or give up. Returns which, for the log."""
    if send is None:
        from .supervisor import send_keys
        send = lambda t, keys: send_keys(t, keys, enter=True)   # noqa: E731
    deadline = clock() + timeout
    while clock() < deadline:
        verdict = decide(read(since), since, clock())
        if verdict == "send":
            return "sent" if send(target, [text]) == 0 else "send failed"
        if verdict == "skip":
            return "skipped: a prompt started after the compaction"
        sleep(poll)
    return "gave up: no compaction within the timeout"


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("target", help="supervisor name or pid whose pane receives the prompt")
    p.add_argument("since", type=float, help="epoch seconds of the injection")
    p.add_argument("--text", default=DEFAULT_TEXT)
    a = p.parse_args(argv)
    outcome = follow(a.target, a.since, a.text)
    try:
        from .agent_events_log import append_event
        append_event("compact_followup", {"target": a.target, "outcome": outcome})
    except Exception:  # the outcome is a record, never a reason to fail
        pass
    print(f"[inject] compact follow-up: {outcome}")
    return 0 if outcome in ("sent",) or outcome.startswith("skipped") else 1


if __name__ == "__main__":
    sys.exit(main())
