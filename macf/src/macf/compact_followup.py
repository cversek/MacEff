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
  ``SETTLE_SECONDS`` have passed since it, so the SessionStart hook has finished, and only
  into an idle, empty input box. Text typed after a draft is sent with it as one prompt:
  a follower's unsent text once sat in a box for 29 hours, and the next ``inject compact``
  typed ``/compact`` onto its end, so no compaction ran;
- **skip** if a new prompt started after the compaction (a mail clock, a cron or the
  operator got there first): the agent is already awake, and a second prompt would collide;
- **give up** after ``TIMEOUT_SECONDS`` with no compaction (the ``/compact`` never ran).

It exits after one decision. It types only text written by the framework, never text from
a message or a file, so it cannot carry anyone else's words into the session.

**Sent means a turn started.** The text is typed, then Enter is pressed only while that
text is still in the input box, at most ``MAX_ENTERS`` times, ``ENTER_SPACING_S`` apart,
until the prompt event shows a turn began. Typed and Enter pressed in one burst, the Enter
was once taken into the text: a seat's box held the prompt, unsent, for fourteen hours,
the log said "sent", and every wake meanwhile was held, since a wake types only into an
empty box.
"""
import argparse
import sys
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

DEFAULT_TEXT = ("🏗️ MACF | The compaction you queued with inject compact has finished. "
                "Run your recovery now: follow the recovery instructions above.")
#: The SessionStart hook's prompt after any compaction while AUTO_MODE is on.
RESUME_TEXT = ("🏗️ MACF | Your session compacted while in AUTO_MODE, and nothing has started "
               "a turn since. Run your recovery now: follow the recovery instructions above, "
               "then resume your work.")
#: Held by the follower that is waiting, so a second one for the same compaction steps aside.
LOCK_NAME = "compact_followup.lock"
SETTLE_SECONDS = 5.0
MAX_ENTERS = 3
ENTER_SPACING_S = 2.0
TURN_WAIT_S = 8.0
TIMEOUT_SECONDS = 1800.0
POLL_SECONDS = 2.0
PROMPT_EVENT = "dev_drv_started"
COMPACTION_EVENT = "compaction_detected"
#: The turn that queued a command ended: a queued /model has then run, since the client takes
#: a queued command as the turn yields. ``inject model`` waits for this, not for a compaction.
TURN_END_EVENT = "dev_drv_ended"
MODEL_TEXT = ("🏗️ MACF | Your model is now {model}, switched with inject model ({reason}). "
              "Carry on with the work you were doing.")
#: Model families as the client's "Switch model?" dialog names them ("Fable 5.2"), by the aliases inject types.
MODEL_FAMILIES = ("opus", "sonnet", "haiku", "fable")


def same_model(asked: str, shown: str) -> bool:
    """Whether the model a "Switch model?" dialog names is the one inject model was asked for. Only a family
    alias or a ``claude-<family>-...`` id can be matched; ``default`` names no family, so it never matches."""
    asked = asked.lower().replace("[1m]", "").strip()
    family = asked.split("-")[1] if asked.startswith("claude-") and asked.count("-") >= 2 else asked
    words = shown.lower().split()
    return family in MODEL_FAMILIES and bool(words) and words[0] == family


def decide(events: Iterable[dict], since: float, now: float,
           settle: float = SETTLE_SECONDS, after: str = COMPACTION_EVENT) -> str:
    """'wait', 'send' or 'skip', from the events at or after *since* (any order). *after* is the
    event that must come first: a compaction for ``inject compact``, a turn's end for a model switch."""
    rows = sorted((e for e in events if (e.get("timestamp") or 0) >= since),
                  key=lambda e: e.get("timestamp") or 0)
    compaction = next((e for e in rows if e.get("event") == after), None)
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


def submit(text: str, typed_at: float, *, capture: Callable[[], Optional[str]],
           enter: Callable[[], int], read: Callable[[float], list],
           clock: Callable[[], float] = time.time,
           sleep: Callable[[float], None] = time.sleep,
           max_enters: int = MAX_ENTERS, spacing: float = ENTER_SPACING_S,
           turn_wait: float = TURN_WAIT_S) -> str:
    """Press Enter on *text*, typed at *typed_at*, until a turn starts. Returns the outcome."""
    from .pd.wake import box_text

    def started() -> bool:
        return any(e.get("event") == PROMPT_EVENT and (e.get("timestamp") or 0) > typed_at
                   for e in read(typed_at))

    enters = 0
    deadline = clock() + max_enters * spacing + turn_wait
    while clock() < deadline:
        sleep(spacing)
        if started():
            return "sent"
        screen = capture()
        in_box = box_text(screen) if screen is not None else None
        if in_box and in_box.startswith(text[:40]) and enters < max_enters:
            enter()                                        # only our own text is submitted
            enters += 1
    if started():
        return "sent"
    return f"typed, but no turn started after {enters} Enter(s)"


def follow(target: str, since: float, text: str = DEFAULT_TEXT, *,
           timeout: float = TIMEOUT_SECONDS, poll: float = POLL_SECONDS,
           read: Callable[[float], list] = _events_since,
           send: Optional[Callable[[str, list], int]] = None,
           capture: Optional[Callable[[], Optional[str]]] = None,
           enter: Optional[Callable[[], int]] = None,
           width: Optional[Callable[[], Optional[int]]] = None,
           clock: Callable[[], float] = time.time,
           sleep: Callable[[float], None] = time.sleep,
           after: str = COMPACTION_EVENT, confirm_model: Optional[str] = None) -> str:
    """Wait for the compaction (or *after*), then send, skip, or give up. Returns which, for the log.

    After a model switch the client may ask "Switch model?" in a dialog above the input box. With
    *confirm_model*, the model inject was asked for, the follower answers it once, and only when the dialog
    offers that same model; any other dialog is left for a person, and the outcome says so."""
    if send is None or capture is None or enter is None or width is None:
        from .supervisor import capture_pane, pane_width, press_enter, send_keys
        send = send or (lambda t, keys: send_keys(t, keys, enter=False, kind="compact-followup"))  # noqa: E731
        capture = capture or (lambda: capture_pane(target))  # noqa: E731
        enter = enter or (lambda: press_enter(target))  # noqa: E731
        width = width or (lambda: pane_width(target))  # noqa: E731
    from .pd.wake import IDLE_EMPTY, TOO_NARROW, classify, switch_dialog_model
    deadline = clock() + timeout
    box_seen, columns, answered = None, None, False
    while clock() < deadline:
        verdict = decide(read(since), since, clock(), after=after)
        if verdict == "send":
            screen, columns = capture(), width()
            offered = switch_dialog_model(screen) if screen is not None and after == TURN_END_EVENT else None
            if offered is not None:
                if confirm_model is None:
                    return f"gave up: a 'Switch model?' dialog for {offered} waits for a person (switched with --no-confirm)"
                if not same_model(confirm_model, offered) or answered:
                    return (f"gave up: a 'Switch model?' dialog offers {offered}, and {confirm_model} was asked"
                            f"{' and already confirmed once' if answered else ''}; left for a person")
                enter()                        # option 1, highlighted: "Yes, switch to" the model asked
                answered = True
                sleep(poll)
                continue
            box_seen = classify(screen, columns) if screen is not None else "unreadable"
            if box_seen != IDLE_EMPTY:
                sleep(poll)                    # typed after a draft, both would go as one
                continue
            typed_at = clock()
            if send(target, [text]) != 0:
                return "send failed"
            return submit(text, typed_at, capture=capture, enter=enter, read=read,
                          clock=clock, sleep=sleep)
        if verdict == "skip":
            return f"skipped: a prompt started after the {'compaction' if after == COMPACTION_EVENT else 'turn ended'}"
        sleep(poll)
    if box_seen == TOO_NARROW:
        return (f"gave up: the session's pane is {columns} columns wide, too narrow to read "
                f"its input box; widen it")
    if box_seen is not None:
        return f"gave up: the input box was never idle and empty (last seen: {box_seen})"
    return f"gave up: no {'compaction' if after == COMPACTION_EVENT else 'turn end'} within the timeout"


def _take_lock(path: Optional[Path] = None):
    """The open lock file, held until this process exits, or None when another follower
    holds it. ``inject compact`` and the SessionStart hook each start one for the same
    compaction, and two would type the prompt twice. Can't take it at all: proceed."""
    import fcntl
    if path is None:
        from .utils.paths import find_agent_home
        path = find_agent_home() / ".maceff" / LOCK_NAME
    try:
        fh = open(path, "a")
    except OSError as e:
        print(f"[inject] compact follow-up: no lock ({e}); proceeding without one",
              file=sys.stderr)
        return sys.stderr                              # any non-None: nothing to hold
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    return fh


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("target", help="supervisor name or pid whose pane receives the prompt")
    p.add_argument("since", type=float, help="epoch seconds of the injection")
    p.add_argument("--text", default=DEFAULT_TEXT)
    p.add_argument("--after", default=COMPACTION_EVENT, choices=(COMPACTION_EVENT, TURN_END_EVENT),
                   help="the event to wait for before typing (default: a compaction)")
    p.add_argument("--confirm-switch", metavar="MODEL", default=None,
                   help="after a model switch, answer the client's 'Switch model?' dialog if it offers MODEL")
    a = p.parse_args(argv)
    lock = _take_lock()
    outcome = follow(a.target, a.since, a.text, after=a.after, confirm_model=a.confirm_switch) \
        if lock is not None else "skipped: another follower is already waiting"
    from .agent_events_log import append_event
    # append_event catches its own I/O errors and returns False; a wrapper here could only
    # hide a defect, so a failed record is said, not swallowed.
    record = {"target": a.target, "outcome": outcome}
    if a.after != COMPACTION_EVENT:
        record["after"] = a.after                      # a compaction's record keeps its shape
    if not append_event("compact_followup", record):
        print("[inject] compact follow-up: the outcome could not be recorded in the event log",
              file=sys.stderr)
    print(f"[inject] compact follow-up: {outcome}")
    return 0 if outcome in ("sent",) or outcome.startswith("skipped") else 1


if __name__ == "__main__":
    sys.exit(main())
