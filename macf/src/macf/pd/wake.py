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
- **A refractory window and a daily cap**, each said once rather than on every poll. A
  wake the window holds is said as a hold like any other, with the seconds left, so a
  late wake always has a reason in the log.
- **A dialog or draft hold keeps the screen it read**, private to the agent, so what the
  fallback took for a dialog can be checked afterwards against the classifier.

The screen is read and typed into through a ``Pane``; ``TmuxPane`` reaches a session
unit's pane through its own tmux server.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Protocol, Tuple

from macf.agent_events_log import append_event
from macf.utils.input_origin import WAKE_OPENING

#: The broker's message id; any other shape is never typed (R77).
MESSAGE_ID = re.compile(r"^msg-\d{10}-[0-9a-f]{12}$")
#: How many ids a wake names before "+N more".
MAX_NAMED = 8
#: Seconds after a wake before another may be typed; arrivals meanwhile wait for the next. The
#: declaration's ``wake_refractory_s`` defaults to the same value (pinned equal by a test), and
#: the agent may pace it (``pace_refusal``, ``window_at_boot``).
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
#: The agent, or the operator, paced the wake over the control socket (persistent_layer 1.9):
#: the window asked for, the one it replaced, and who asked, why and from which process. The
#: next daemon reads the newest back at its start.
EVENT_PACED = "pd_wake_paced"

# The screen states, from the most to the least cautious.
DIALOG, RUNNING, DRAFT, WAKE_IN_BOX, IDLE_EMPTY = "dialog", "running", "draft", "wake_in_box", "idle_empty"
#: The hold reason while the refractory window runs: the agent's pace, not its screen.
REFRACTORY = "refractory"

#: The holds whose screen is kept: the two a person may be behind, and the two the
#: Oct 17 demo could not explain afterwards.
SCREEN_KEPT_FOR = (DIALOG, DRAFT)
#: Saved screens kept per agent, the newest; older ones are removed as new ones are written.
SCREENS_KEPT = 20

#: A border of the input box: a run of rule characters, which since client 2.1.300 may be
#: broken once by a label (the session's name, near the right end of the top border).
_RULE = re.compile(r"^\s*─+(?: \S(?:.*\S)? ─+)?\s*$")
#: Rule characters a border has at least, so a short rule in the conversation is not one.
_RULE_MIN = 20
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
#: The running turn's spinner line, "Verbing… (1m 5s · …". While a hook runs, 2.1.300 puts what
#: it is doing first, "Verbing… (running PreToolUse hook · 26m 20s · …", about a second at every
#: tool call; read without that phrase, those seconds looked idle and a wake was typed mid-turn.
_SPINNER = re.compile(r"…\s*\((?:[^()]*?·\s*)?(\d+h )?(\d+m )?\d+s")
_DIALOG_MARKERS = ("esc to cancel", "enter to select", "do you want to")
_RUNNING_MARKER = "esc to interrupt"


def pace_refusal(wanted_s: Optional[float], floor_s: Optional[float],
                 ceiling_s: Optional[float] = None) -> Optional[str]:
    """Why a pace is refused, or None. Only the declaration sets the floor and the ceiling: a pace
    may lengthen the window up to the ceiling, or shorten it down to the floor, and never past
    either. None asks for the declared window, which the declaration holds between the two."""
    if wanted_s is None:
        return None
    if not math.isfinite(wanted_s):
        return f"{wanted_s!r} is not a window: a pace is a finite number of seconds"
    if floor_s is not None and wanted_s < floor_s:
        return (f"{wanted_s:g} s is under the declared floor of {floor_s:g} s, and only the "
                f"declaration sets the floor")
    if ceiling_s is not None and wanted_s > ceiling_s:
        return (f"{wanted_s:g} s is over the declared ceiling of {ceiling_s:g} s, and only the "
                f"declaration sets the ceiling: past it, the agent would go unwoken longer than a "
                f"held wake may before the operator is told")
    return None


def window_at_boot(declared_s: float, floor_s: Optional[float],
                   paced: Optional[dict], ceiling_s: Optional[float] = None) -> Tuple[float, str]:
    """The window a starting daemon puts in force, and where it came from, from the newest
    ``pd_wake_paced`` event of this agent, or None. The newest pace holds until another replaces
    it; a floor declared above it, or a ceiling below it, since then wins, and the answer says
    so. A saved pace that is not a finite number (written before paces were bounded) is held to
    the ceiling."""
    if paced is None:
        return declared_s, "the declaration"
    data = paced.get("data") or {}
    when = paced.get("timestamp") or 0
    wanted = data.get("refractory_s")
    if wanted is None:
        return declared_s, f"the declaration, which the pace of {_minute(when)} went back to"
    if ceiling_s is not None and not (isinstance(wanted, (int, float)) and wanted <= ceiling_s):
        return ceiling_s, f"the declared ceiling, under the pace of {_minute(when)}, which asked for {wanted!r} s"
    if floor_s is not None and wanted < floor_s:
        return floor_s, f"the declared floor, raised since the pace of {_minute(when)} asked for {wanted:g} s"
    return wanted, pace_source(when, (data.get("asked_by") or {}).get("kind", "agent"), data.get("reason", ""))


def pace_source(when: float, asker_kind: str, reason: str) -> str:
    """Where a paced window came from, said the same way live and after a restart."""
    return f"the pace of {_minute(when)} by the {asker_kind}: {reason}"


def _minute(epoch: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch))


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


def _box(screen: str):
    """``(state, text)``: None and the box's text (empty for an empty box) for an idle
    session; RUNNING and the box's text while a turn runs; DIALOG and None with no box."""
    raw = screen.splitlines()
    plain = [_ANSI.sub("", line) for line in raw]
    rules = [i for i, line in enumerate(plain)
             if _RULE.match(line) and line.count("─") >= _RULE_MIN]
    if len(rules) < 2:
        return DIALOG, None                                # no input box on screen
    top, bottom = rules[-2], rules[-1]
    box = [i for i in range(top + 1, bottom) if plain[i].strip()]
    if not box or not plain[box[0]].lstrip().startswith(("❯", ">")):
        return DIALOG, None
    below = [line for line in plain[bottom + 1:] if line.strip()]
    if len(below) > 8 or any(m in line.lower() for line in below for m in _DIALOG_MARKERS):
        return DIALOG, None
    # The spinner can sit well above the box, with the turn's output between them; the
    # clock looks fifteen lines up, and 2.1.288 prints only the spinner.
    near = plain[max(0, top - RUNNING_LOOKBACK):]
    first = _visible(raw[box[0]]).lstrip()[1:]            # past the prompt mark
    text = " ".join([first] + [_visible(raw[i]) for i in box[1:]]).strip()
    if any(_RUNNING_MARKER in line.lower() or _SPINNER.search(line) for line in near):
        return RUNNING, text
    return None, text


def classify(screen: str) -> str:
    """What a captured screen shows, failing closed: anything not recognized as an idle
    session with an empty input box is one of the busy states."""
    state, text = _box(screen)
    if state is not None:
        return state
    if not text:
        return IDLE_EMPTY
    if text.startswith(WAKE_OPENING):
        return WAKE_IN_BOX                                 # only the box counts, never an echo
    return DRAFT


def saved_screens_dir(agent_home: Path) -> Path:
    """Where an agent's held wakes keep their screens: beside its event log, which the
    daemon writes wherever it runs."""
    return Path(agent_home) / ".maceff" / "wake_screens"


def save_screen(directory: Path, screen: str, reason: str, when: float,
                keep: int = SCREENS_KEPT) -> Path:
    """Write a held wake's screen, escape codes and all, to *directory*, private to this
    user, keeping the newest *keep*; the path written. It never leaves this host: a screen
    can show anything the session showed. Raises OSError when it cannot be written."""
    from macf.pd.session_unit import _private_dir
    _private_dir(directory)
    # UTC, so the names sort by time through a change of the clocks, and the oldest go first.
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(when)) + f".{int(when * 1000) % 1000:03d}Z"
    path = directory / f"wake-{stamp}-{reason}.txt"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # never another file's
    with os.fdopen(fd, "w") as f:
        f.write(screen)
    for old in sorted(directory.glob("wake-*.txt"))[:-keep]:
        old.unlink(missing_ok=True)
    return path


def box_text(screen: str) -> Optional[str]:
    """The text in an idle session's input box, empty when the box is empty; None while the
    screen shows a running turn, a dialog, or no box. Only the box counts, never an echo."""
    state, text = _box(screen)
    return text if state is None else None


def draft_text(screen: str) -> Optional[str]:
    """The text in the input box whether or not a turn is running, empty when the box is
    empty; None for a dialog or no box. Anything typed now lands after this text."""
    return _box(screen)[1]


#: Transcript records that are not a turn of the conversation: an interrupt, and a local command
#: with its output. The macOS prototype found both holding the gate shut after a turn had ended
#: (MIS-0004 R29); they failed safe, but a notice then waited for a person to type.
_SKIPPED_TEXT = ("[Request interrupted by user", "<command-name>", "<local-command-stdout>",
                 "<local-command-stderr>", "<command-message>", "<local-command-caveat>",
                 "<bash-input>", "<bash-stdout>", "<bash-stderr>")


def _record_text(rec: dict) -> str:
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def turn_ended(lines: Iterable[str]) -> Optional[bool]:
    """Whether the transcript's last turn has ended (MIS-0004 R29), read from its JSONL lines.

    True when the last meaningful record is the assistant's, finished (``stop_reason`` end_turn);
    False when it is the user's, or the assistant's mid-turn (a tool call); None when nothing in
    it can be read, which is never evidence of an idle prompt. Interrupt and local-command
    records, and system records, are skipped."""
    last = None
    for raw in lines:
        try:
            rec = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict) or rec.get("type") not in ("user", "assistant"):
            continue
        # Skipped by prefix only, never by isMeta: a channel message (Telegram, a MacEff notice)
        # is an isMeta user record that starts a turn (CTB on #925).
        if rec["type"] == "user" and _record_text(rec).lstrip().startswith(_SKIPPED_TEXT):
            continue
        last = rec
    if last is None:
        return None
    if last["type"] == "user":
        return False
    return (last.get("message") or {}).get("stop_reason") == "end_turn"


def transcript_turn_ended(path: Optional[Path], tail_bytes: int = 262144) -> Optional[bool]:
    """:func:`turn_ended` over the tail of the transcript at *path*; None when it can't be read."""
    if path is None:
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return None  # noqa: MACEFF003 - None is "can't be read", which the R29 gate holds as busy
    lines = data.splitlines()
    return turn_ended(lines[1:] if size > tail_bytes else lines)


def latest_transcript(project_dir: Optional[Path], claude_home: Optional[Path] = None) -> Optional[Path]:
    """The newest transcript of the sessions run in *project_dir*: Claude Code keeps them under
    ``~/.claude/projects/<the path with every non-alphanumeric character as ->/``."""
    if project_dir is None:
        return None
    key = re.sub(r"[^A-Za-z0-9]", "-", str(Path(project_dir)))
    folder = (claude_home or Path.home() / ".claude") / "projects" / key
    try:
        found = max(folder.glob("*.jsonl"), key=lambda q: q.stat().st_mtime)
    except (ValueError, OSError):
        return None  # noqa: MACEFF003 - None is "no transcript found", which the R29 gate holds as busy
    return found


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
    #: Where a dialog or draft hold keeps the screen it read; None keeps none.
    screens_dir: Optional[Path] = None
    #: The wall clock, for a saved screen's name; ``clock`` only measures intervals.
    wall: Callable[[], float] = time.time
    #: Who or what the session waits on (MIS-0002-R21), or None; with the next two, the positive
    #: evidence of an idle prompt MIS-0004 R29 asks for. None here means not wired: no gate.
    waiting_on: Optional[Callable[[], Optional[str]]] = None
    #: Whether the transcript's last turn has ended (True), not (False) or can't be read (None,
    #: which holds like False). None here means not wired: no gate.
    turn_ended: Optional[Callable[[], Optional[bool]]] = None

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
            return None
        left = self.refractory_s - (now - self.last_sent)
        if left > 0:
            if self.held != REFRACTORY:                    # once per stretch, like the screen's reasons
                self.held = REFRACTORY
                self._say(EVENT_HELD, {"reason": REFRACTORY, "left_s": math.ceil(left), "waiting": len(fresh)})
            return None
        if self.day != self.today():
            self.day, self.sent_today = self.today(), 0
        if self.sent_today >= self.daily_cap:
            if self.cap_said != self.day:
                self.cap_said = self.day
                self._say(EVENT_CAP, {"cap": self.daily_cap, "day": self.day.isoformat()})
            return None
        if self.waiting_on is not None:
            who = self.waiting_on()
            if who:
                return self._hold(f"a person is waited on: {who}", fresh)
        if self.turn_ended is not None:
            ended = self.turn_ended()
            if ended is not True:
                return self._hold("the transcript's last turn has not ended" if ended is False
                                  else "the transcript can't be read", fresh)
        screen = self.pane.capture()
        state = classify(screen) if screen is not None else DIALOG
        if state != IDLE_EMPTY:
            if self.held != state:                         # once per busy stretch
                self.held = state
                self._say(EVENT_HELD, {"reason": state, "waiting": len(fresh), **self._evidence(screen, state)})
            return None
        self.held = None
        text = wake_text(waiting_ids)
        if text is None:
            return None
        if not self.type_notice(text):                     # it has said why
            return None
        # Sent, from here: recorded at the send, so a misread status can't send it again.
        self.woken.update(i for i in waiting_ids if MESSAGE_ID.match(i))
        self.last_sent, self.sent_today = now, self.sent_today + 1
        self._say(EVENT_SENT, {"ids": sorted(self.woken & set(waiting_ids)), "chars": len(text)})
        self.enters, self.next_enter, self.verify_by = 0, now, now + VERIFY_S
        return "sent"

    def type_notice(self, text: str) -> bool:
        """Record, then type *text* without its return (MIS-0004 R39 sends the return apart). A
        notice that begins with a digit is refused (R40): a survey bar reads as an empty box, and
        a digit answers it."""
        if text[:1].isdigit():
            self._say(EVENT_HELD, {"reason": "the notice begins with a digit, which a survey bar would take as an answer"})
            return False
        self.record_keys(text, "pd-wake")                  # before the keys, so they read as the framework's
        if not self.pane.type(text):
            self._say(EVENT_HELD, {"reason": "the pane could not be typed into"})
            return False
        return True

    def _hold(self, reason: str, fresh: List[str]) -> None:
        if self.held != reason:                            # once per stretch, like the screen's reasons
            self.held = reason
            self._say(EVENT_HELD, {"reason": reason, "waiting": len(fresh)})
        return None

    def release(self, reason: str) -> None:
        """End a held stretch without a wake, saying why; nothing if none is held."""
        if self.held is not None:
            self.held = None
            self._say(EVENT_RELEASED, {"reason": reason})

    def _say(self, event: str, data: dict) -> None:
        self.append(event, {"agent": self.card, **data} if self.card else data)

    def _evidence(self, screen: Optional[str], state: str) -> dict:
        """What a hold can show for itself: the saved screen's path for a dialog or a draft,
        or that no screen could be read at all, which also reads as a dialog."""
        if screen is None:
            return {"captured": False}
        if state not in SCREEN_KEPT_FOR or self.screens_dir is None:
            return {}
        try:
            return {"screen": str(save_screen(self.screens_dir, screen, state, self.wall()))}
        except OSError as e:
            print(f"⚠️ MACF: pd: the held wake's screen was not saved (the hold is still said): {e}",
                  file=sys.stderr)
            return {"screen_error": str(e)}

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

    def _target(self) -> str:
        """The agent's own pane, else the session.

        ``={agent}:`` is the session's ACTIVE pane. Once someone splits the window and works
        in the new pane (a watch beside the agent), a wake typed there never reaches the
        client. The session unit names the pane it created in its pane record, by the
        pane's process group, which is the pane process's own pid (``session_unit``)."""
        from macf.pd.session_unit import PANE_RECORD, tmux_dir
        fallback = f"={self.agent}:"
        try:
            record = json.loads((tmux_dir(self.agent, self.base) / PANE_RECORD).read_text())
            groups = {int(entry[0]) for entry in record}
        except (OSError, ValueError, TypeError, IndexError):
            return fallback                       # no record yet: the session, as before
        out = self._run("list-panes", "-s", "-t", f"={self.agent}", "-F", "#{pane_id} #{pane_pid}")
        if out is None or out.returncode != 0:
            return fallback
        for line in out.stdout.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1].isdigit() and int(fields[1]) in groups:
                return fields[0]
        # A record that names no live pane is the case that types into the wrong one (#777).
        print(f"⚠️ MACF: pd: no pane of {self.agent} is the unit's own; the wake goes to the "
              f"session's active pane", file=sys.stderr)
        return fallback

    def capture(self) -> Optional[str]:
        out = self._run("capture-pane", "-p", "-e", "-t", self._target())
        return out.stdout if out is not None and out.returncode == 0 else None

    def type(self, text: str) -> bool:
        out = self._run("send-keys", "-t", self._target(), "-l", text)
        return out is not None and out.returncode == 0

    def enter(self) -> bool:
        out = self._run("send-keys", "-t", self._target(), "Enter")
        return out is not None and out.returncode == 0
