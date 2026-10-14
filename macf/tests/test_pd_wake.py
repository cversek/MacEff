"""The keystroke wake, the notifier's fallback for a session with no MacEff channel
(MIS-0002-R45, R77, R105, R43, R106), kept to the rules of the mail clock it replaces."""
import socket
from datetime import date
from types import SimpleNamespace

from macf.pd import notifier as nt
from macf.pd import wake as wk
from macf.utils.input_origin import WAKE_OPENING, opens_with_wake

RULE = "─" * 60
FAINT, RESET = "\x1b[2m", "\x1b[0m"
ID1, ID2, ID3 = "msg-1791900000-aaaaaaaaaaaa", "msg-1791900100-bbbbbbbbbbbb", "msg-1791900200-cccccccccccc"


def screen(box="", above=(), below=("  ? for shortcuts",)):
    return "\n".join([*above, RULE, f"❯ {box}", RULE, *below])


# --- reading the screen (R45), failing closed -------------------------------------

def test_an_idle_empty_box_is_the_only_state_that_may_be_typed_into():
    assert wk.classify(screen()) == wk.IDLE_EMPTY
    assert wk.classify(screen(f"{FAINT}try: summarize the diff{RESET}")) == wk.IDLE_EMPTY, \
        "the client's faint suggestion is an empty box"
    assert wk.classify(screen("half a thought")) == wk.DRAFT


def test_a_dialog_menu_or_question_is_never_typed_into():
    assert wk.classify("plain output, no input box") == wk.DIALOG
    assert wk.classify(screen(below=("Do you want to proceed?", "❯ 1. Yes", "  2. No"))) == wk.DIALOG
    assert wk.classify(screen(below=["line"] * 9)) == wk.DIALOG
    assert wk.classify(screen(below=("Enter to select · Esc to cancel",))) == wk.DIALOG


def test_a_running_turn_is_seen_by_its_phrase_or_by_the_spinner_alone():
    assert wk.classify(screen(above=("✻ Working… (esc to interrupt)",))) == wk.RUNNING
    # Since 2.1.288 the client prints only the spinner.
    assert wk.classify(screen(above=("✻ Pondering… (1m 12s · ↓ 2.1k tokens)",))) == wk.RUNNING


def test_only_the_box_counts_as_a_wake_in_the_prompt_never_its_echo():
    echo = f"> {WAKE_OPENING} mail waiting: {ID1}. Read it with macf_tools amail read."
    assert wk.classify(screen(above=(echo, "⏺ Read 1 message."))) == wk.IDLE_EMPTY
    assert wk.classify(screen(f"{WAKE_OPENING} mail waiting: {ID1}")) == wk.WAKE_IN_BOX


# --- what may be typed (R77) ------------------------------------------------------

def test_a_wake_carries_fixed_words_and_message_ids_oldest_first():
    text = wk.wake_text([ID3, ID1, "msg-evil; rm -rf ~", ID2])
    assert opens_with_wake(text)
    assert text.index(ID1) < text.index(ID2) < text.index(ID3)
    assert "evil" not in text and "rm" not in text
    assert wk.wake_text(["Subject: anything a sender chose"]) is None


def test_past_eight_ids_the_rest_are_counted_not_named():
    ids = [f"msg-17919{i:05d}-{i:012x}" for i in range(11)]
    text = wk.wake_text(ids)
    assert ids[7] in text and ids[8] not in text and "+3 more" in text


# --- typing and submitting -------------------------------------------------------

class FakePane:
    """A pane whose screen a test scripts, recording what was typed and pressed."""

    def __init__(self, screens):
        self.screens, self.typed, self.enters, self.log = list(screens), [], 0, []

    def capture(self):
        return self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]

    def type(self, text):
        self.typed.append(text)
        self.log.append("type")
        return True

    def enter(self):
        self.enters += 1
        self.log.append("enter")
        return True


def _waker(pane, events, clock=None, **kw):
    t = clock or [0.0]
    recorded = []

    def record(text, kind):
        recorded.append(text)
        pane.log.append("record")
    w = wk.Waker(pane, record_keys=record, append=lambda e, d: events.append((e, d)) or True,
                 clock=lambda: t[0], today=lambda: date(2026, 10, 14), **kw)
    return SimpleNamespace(waker=w, clock=t, recorded=recorded)


def test_the_wake_is_recorded_before_it_is_typed_and_reads_as_the_framework():
    pane, events = FakePane([screen()]), []
    h = _waker(pane, events)
    w, recorded = h.waker, h.recorded
    assert w.tick([ID1]) == "sent"
    assert pane.log[:2] == ["record", "type"], "the keys were typed before they were recorded"
    assert recorded == pane.typed and opens_with_wake(recorded[0])


def test_enter_only_while_the_wake_is_still_in_the_box_and_at_most_three_times():
    in_box = screen(f"{WAKE_OPENING} mail waiting: {ID1}")
    pane, events = FakePane([screen()] + [in_box] * 10), []
    h = _waker(pane, events)
    w, t = h.waker, h.clock
    w.tick([ID1])
    for _ in range(10):
        t[0] += 1.0
        w.tick([ID1])
    assert pane.enters == 3, "Enter pressed past three, or on something other than the wake"
    assert ("pd_wake_turn", {"started": False, "screen": wk.WAKE_IN_BOX, "enters": 3}) in events


def test_no_enter_lands_on_a_dialog_the_new_turn_raised():
    dialog = screen(below=("Do you want to proceed?", "❯ 1. Yes", "  2. No"))
    pane, events = FakePane([screen(), dialog]), []
    h = _waker(pane, events)
    w, t = h.waker, h.clock
    w.tick([ID1])
    for _ in range(8):
        t[0] += 1.0
        w.tick([ID1])
    assert pane.enters == 0


def test_sent_is_recorded_at_the_send_so_a_misread_status_never_sends_twice():
    pane, events = FakePane([screen()]), []                  # the turn is never seen
    h = _waker(pane, events, refractory_s=0.0)
    w, t = h.waker, h.clock
    w.tick([ID1])
    for _ in range(20):
        t[0] += 1.0
        w.tick([ID1])
    assert len(pane.typed) == 1, "the same mail was woken for twice"
    assert ("pd_wake_turn", {"started": False, "screen": wk.IDLE_EMPTY, "enters": 0}) in events


def test_a_busy_stretch_is_said_once_and_nothing_is_typed():
    pane, events = FakePane([screen("half a thought")]), []
    h = _waker(pane, events)
    w, t = h.waker, h.clock
    for _ in range(5):
        t[0] += 1.0
        w.tick([ID1])
    assert pane.typed == []
    assert [e for e, _ in events] == ["pd_wake_held"]


def test_arrivals_inside_the_refractory_window_wait_for_the_next_wake():
    running = screen(above=("✻ Working… (esc to interrupt)",))
    pane, events = FakePane([screen(), running, screen()]), []
    h = _waker(pane, events, refractory_s=600.0)
    w, t = h.waker, h.clock
    w.tick([ID1])
    t[0] += 1.0
    w.tick([ID1])                                             # the turn is seen; done
    t[0] += 60.0
    assert w.tick([ID1, ID2]) is None                         # inside the window
    t[0] += 600.0
    assert w.tick([ID1, ID2]) == "sent"
    assert ID1 in pane.typed[1] and ID2 in pane.typed[1], "the next wake names everything waiting"


def test_the_daily_cap_is_recorded_once():
    pane, events = FakePane([screen()]), []
    h = _waker(pane, events, refractory_s=0.0, daily_cap=1)
    w, t = h.waker, h.clock
    w.tick([ID1])
    for i in range(10):
        t[0] += 10.0
        w.tick([ID1, f"msg-17919{i:05d}-{i:012x}"])
    assert len(pane.typed) == 1
    assert [e for e, _ in events].count("pd_wake_cap_reached") == 1


# --- the notifier: channel first (R104, R105, R43) --------------------------------

def _home_with_mail(tmp_path, *ids):
    box = tmp_path / "agent" / "amail" / "pickup"
    box.mkdir(parents=True)
    for i in ids:
        (box / f"1791990000-{i}.amsg").write_text("never read by the notifier")
    return tmp_path / "agent"


def test_wake_through_notifier(tmp_path, isolated_events_log):
    """Every wake goes through the notifier (R43), and only as its fallback (R105): never
    while a channel is attached, never before a channel has had its grace, and a typed
    wake delivers the mail notices it covers, so no channel delivers them again."""
    clock = [1000.0]
    n = nt.Notifier(_home_with_mail(tmp_path, ID1, ID2), {"amail": "agent"}, clock=lambda: clock[0])
    n.boot()
    pane = FakePane([screen()])
    n.waker = _waker(pane, []).waker
    ours, theirs = socket.socketpair()
    n.attach(ours)
    clock[0] += 3600
    assert not n.wake() and pane.typed == [], "typed a wake while a channel was attached"
    n.detach(ours)
    theirs.close()

    clock[0] = n.owed[next(iter(n.owed))].read_at + nt.CHANNEL_GRACE_S - 1
    assert not n.wake(), "typed before a channel had its grace"
    clock[0] += 2
    assert n.wake() and len(pane.typed) == 1
    assert ID1 in pane.typed[0] and ID2 in pane.typed[0]
    assert not n.owed, "a typed wake left its notices owed, for a channel to deliver again"


# --- the real pane ---------------------------------------------------------------

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.skipif(shutil.which("tmux") is None, reason="needs tmux")
def test_the_wake_reaches_a_session_units_own_pane():
    """TmuxPane reaches the session unit's server through TMUX_TMPDIR and its pane by the
    exact session name, and the wake arrives as typed."""
    from macf.pd import session_unit as su
    base = Path(tempfile.mkdtemp(prefix="pw-", dir="/tmp"))
    agent = "Resident_1a2b3c"
    env = {k: v for k, v in os.environ.items() if k != "TMUX"}
    env["TMUX_TMPDIR"] = str(su._private_dir(su.tmux_dir(agent, base)))
    got = base / "got.txt"
    try:
        subprocess.run(["tmux", "-f", "/dev/null", "new-session", "-d", "-s", agent, f"cat > {got}"],
                       env=env, check=True)
        pane = wk.TmuxPane(agent, base)
        deadline = time.monotonic() + 5
        while pane.capture() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        text = wk.wake_text([ID1])
        assert pane.capture() is not None and pane.type(text) and pane.enter()
        deadline = time.monotonic() + 5
        while not (got.exists() and got.read_text().strip()) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert got.read_text().strip() == text
    finally:
        subprocess.run(["tmux", "kill-server"], env=env, capture_output=True)
        shutil.rmtree(base, ignore_errors=True)
