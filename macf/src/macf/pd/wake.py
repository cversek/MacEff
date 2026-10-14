"""The keystroke wake: the notifier's fallback for a session with no MacEff channel.

MIS-0002-R105 (keystroke_wake_MUST_be_fallback_only): the daemon types a wake only when
no channel has taken the notices it owes. What it may type, when, and how it submits
follow the rules of the mail clock that typed wakes before the daemon did, each kept
because something went wrong without it:

- **Only fixed words and message ids** [MIS-0002-R77 (wake_MUST_carry_fixed_words_only)],
  ids only in the broker's exact shape, every waiting one named oldest first up to eight.
  An agent consumes by position, and agents told only of the newest lost the older ones.
- **Only into an empty input box of an idle session** [MIS-0002-R45
  (keystroke_wake_MUST_need_empty_idle_box)], read from the screen, failing closed:
  anything not recognized as idle and empty is busy. A dialog, a menu or a question on
  screen is never typed into, because the wake carries digits and a digit or an Enter
  selects an option.
- **Recorded before it is typed**, through the framework's keystroke record, and opened
  with the wake words, so neither producer of the operator's activity counts it
  [MIS-0002-R106 (wake_MUST-NOT_count_as_operator_activity)].
- **Enter only while the wake is still in the box**, at most three times: the client's
  paste detection can hold the first, and an Enter that lands on a dialog the new turn
  raised would approve it.
- **Sent is recorded at the send**, before the turn is verified, so a misread status can't
  send it again; then the turn's start is looked for, and the log says whether it came.
- **A refractory window and a daily cap**, each said once rather than on every poll.

The screen is read and typed into through a ``Pane``; ``TmuxPane`` reaches a session
unit's pane through its own tmux server.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterable, List, Optional, Protocol

from macf.agent_events_log import append_event
from macf.utils.input_origin import WAKE_OPENING

#: The broker's message id; any other shape is never typed (R77).
MESSAGE_ID = re.compile(r"^msg-\d{10}-[0-9a-f]{12}$")
#: How many ids a wake names before "+N more".
MAX_NAMED = 8
#: Seconds after a wake before another may be typed; arrivals meanwhile wait for the next.
REFRACTORY_S = 600.0
#: Wakes per day at most; reaching it is recorded once.
DAILY_CAP = 48
#: Enter presses at most, and the spacing between them.
MAX_ENTERS, ENTER_SPACING_S = 3, 0.7
#: How long the turn has to be seen starting after the first Enter.
VERIFY_S = 6.0

#: How many lines above the box a running turn's phrase or spinner is looked for.
RUNNING_LOOKBACK = 15

EVENT_SENT = "pd_wake_sent"
EVENT_HELD = "pd_wake_held"
#: A held stretch that ended with nothing left waiting: the agent read its mail on its own.
EVENT_RELEASED = "pd_wake_released"
EVENT_TURN = "pd_wake_turn"
EVENT_CAP = "pd_wake_cap_reached"

# The screen states, from the most to the least cautious.
DIALOG, RUNNING, DRAFT, WAKE_IN_BOX, IDLE_EMPTY = "dialog", "running", "draft", "wake_in_box", "idle_empty"

_RULE = re.compile(r"^\s*─{20,}\s*$")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_SPINNER = re.compile(r"…\s*\((\d+h )?(\d+m )?\d+s")
_DIALOG_MARKERS = ("esc to cancel", "enter to select", "do you want to")
_RUNNING_MARKER = "esc to interrupt"


def wake_text(ids: Iterable[str]) -> Optional[str]:
    """The wake for these message ids, or None when none is in the broker's shape. Fixed
    words and ids only; every id named, oldest first, up to eight, then "+N more"."""
    valid = sorted({i for i in ids if MESSAGE_ID.match(i)}, key=lambda i: (i.split("-")[1], i))
    if not valid:
        return None
    named = " ".join(valid[:MAX_NAMED])
    more = f" +{len(valid) - MAX_NAMED} more" if len(valid) > MAX_NAMED else ""
    return f"{WAKE_OPENING} mail waiting: {named}{more}. Read it with macf_tools amail read."


def _visible(line: str) -> str:
    """A line's text without escape codes and without faint runs, the client's suggestion."""
    out, faint, pos = [], False, 0
    for m in _ANSI.finditer(line):
        if not faint:
            out.append(line[pos:m.start()])
        params = m.group(0)[2:-1]
        if m.group(0).endswith("m"):
            codes = params.split(";") if params else ["0"]
            if "2" in codes:
                faint = True
            elif "0" in codes or "22" in codes or params == "":
                faint = False
        pos = m.end()
    if not faint:
        out.append(line[pos:])
    return "".join(out)


def classify(screen: str) -> str:
    """What a captured screen shows, failing closed: anything not recognized as an idle
    session with an empty input box is one of the busy states."""
    raw = screen.splitlines()
    plain = [_ANSI.sub("", line) for line in raw]
    rules = [i for i, line in enumerate(plain) if _RULE.match(line)]
    if len(rules) < 2:
        return DIALOG                                      # no input box on screen
    top, bottom = rules[-2], rules[-1]
    box = [i for i in range(top + 1, bottom) if plain[i].strip()]
    if not box or not plain[box[0]].lstrip().startswith(("❯", ">")):
        return DIALOG
    below = [line for line in plain[bottom + 1:] if line.strip()]
    if len(below) > 8 or any(m in line.lower() for line in below for m in _DIALOG_MARKERS):
        return DIALOG
    # The spinner can sit well above the box, with the turn's output between them; the
    # clock looks fifteen lines up, and 2.1.288 prints only the spinner.
    near = plain[max(0, top - RUNNING_LOOKBACK):]
    if any(_RUNNING_MARKER in line.lower() or _SPINNER.search(line) for line in near):
        return RUNNING
    first = _visible(raw[box[0]]).lstrip()[1:]            # past the prompt mark
    text = " ".join([first] + [_visible(raw[i]) for i in box[1:]]).strip()
    if not text:
        return IDLE_EMPTY
    if text.startswith(WAKE_OPENING):
        return WAKE_IN_BOX                                 # only the box counts, never an echo
    return DRAFT


class Pane(Protocol):
    def capture(self) -> Optional[str]: ...
    def type(self, text: str) -> bool: ...
    def enter(self) -> bool: ...


@dataclass
class Waker:
    """Type wakes into a pane, one step per ``tick``, so the daemon's loop never waits."""

    pane: Pane
    record_keys: Callable[[str, str], None]
    append: Callable[[str, dict], bool] = append_event
    clock: Callable[[], float] = time.monotonic
    today: Callable[[], date] = date.today
    refractory_s: float = REFRACTORY_S
    daily_cap: int = DAILY_CAP
    woken: set = field(default_factory=set)
    last_sent: float = float("-inf")
    day: Optional[date] = None
    sent_today: int = 0
    cap_said: Optional[date] = None
    held: Optional[str] = None
    enters: int = 0
    next_enter: float = 0.0
    verify_by: Optional[float] = None
    #: The agent's calling card, named in every event so the outside watch can tell whose a
    #: held wake is in a log several agents share (rule 14 of the clock's list, on #552).
    card: str = ""

    def tick(self, waiting_ids: List[str]) -> Optional[str]:
        """One step. Returns "sent" on the step a wake is typed, else None."""
        now = self.clock()
        if self.verify_by is not None:
            self._submit(now)
            return None
        fresh = [i for i in waiting_ids if i not in self.woken and MESSAGE_ID.match(i)]
        if not fresh:
            # The held stretch ends without a wake: whatever waited has been read meanwhile.
            self.release("nothing waits any more")
        if not fresh or now - self.last_sent < self.refractory_s:
            return None
        if self.day != self.today():
            self.day, self.sent_today = self.today(), 0
        if self.sent_today >= self.daily_cap:
            if self.cap_said != self.day:
                self.cap_said = self.day
                self._say(EVENT_CAP, {"cap": self.daily_cap, "day": self.day.isoformat()})
            return None
        screen = self.pane.capture()
        state = classify(screen) if screen is not None else DIALOG
        if state != IDLE_EMPTY:
            if self.held != state:                         # once per busy stretch
                self.held = state
                self._say(EVENT_HELD, {"reason": state, "waiting": len(fresh)})
            return None
        self.held = None
        text = wake_text(waiting_ids)
        if text is None:
            return None
        self.record_keys(text, "pd-wake")                  # before the keys, so they read as the framework's
        if not self.pane.type(text):
            self._say(EVENT_HELD, {"reason": "the pane could not be typed into", "waiting": len(fresh)})
            return None
        # Sent, from here: recorded at the send, so a misread status can't send it again.
        self.woken.update(i for i in waiting_ids if MESSAGE_ID.match(i))
        self.last_sent, self.sent_today = now, self.sent_today + 1
        self._say(EVENT_SENT, {"ids": sorted(self.woken & set(waiting_ids)), "chars": len(text)})
        self.enters, self.next_enter, self.verify_by = 0, now, now + VERIFY_S
        return "sent"

    def release(self, reason: str) -> None:
        """End a held stretch without a wake, saying why; nothing if none is held."""
        if self.held is not None:
            self.held = None
            self._say(EVENT_RELEASED, {"reason": reason})

    def _say(self, event: str, data: dict) -> None:
        self.append(event, {"agent": self.card, **data} if self.card else data)

    def _submit(self, now: float) -> None:
        """Press Enter only while the wake is still in the box, at most three times; then
        look for the turn's start until the deadline, and say whether it came."""
        screen = self.pane.capture()
        state = classify(screen) if screen is not None else DIALOG
        if state == RUNNING:
            self.verify_by = None
            self._say(EVENT_TURN, {"started": True})
            return
        if state == WAKE_IN_BOX and self.enters < MAX_ENTERS and now >= self.next_enter:
            self.pane.enter()
            self.enters, self.next_enter = self.enters + 1, now + ENTER_SPACING_S
            return
        if now >= self.verify_by:
            self.verify_by = None
            self._say(EVENT_TURN, {"started": False, "screen": state, "enters": self.enters})


class TmuxPane:
    """A session unit's pane, through its own tmux server (``pd.session_unit``)."""

    def __init__(self, agent: str, base=None):
        self.agent, self.base = agent, base

    def _run(self, *args: str) -> Optional[subprocess.CompletedProcess]:
        from macf.pd.session_unit import client_environment
        env = client_environment(self.agent, self.base)
        if env is None:
            return None                                    # no session unit runs here
        try:
            return subprocess.run(["tmux", *args], env=env, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"⚠️ MACF: pd: the session's pane could not be reached: {e}", file=sys.stderr)
            return None

    def capture(self) -> Optional[str]:
        out = self._run("capture-pane", "-p", "-e", "-t", f"={self.agent}:")
        return out.stdout if out is not None and out.returncode == 0 else None

    def type(self, text: str) -> bool:
        out = self._run("send-keys", "-t", f"={self.agent}:", "-l", text)
        return out is not None and out.returncode == 0

    def enter(self) -> bool:
        out = self._run("send-keys", "-t", f"={self.agent}:", "Enter")
        return out is not None and out.returncode == 0
