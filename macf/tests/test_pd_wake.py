"""The keystroke wake, the notifier's fallback for a session with no MacEff channel
(MIS-0002-R45, R77, R105, R43, R106), kept to the rules of the mail clock it replaces."""
import socket
import stat
from datetime import date
from types import SimpleNamespace

import pytest

from macf.channels.maceff_channel import TAKES
from macf.pd import notifier as nt
from macf.pd import wake as wk
from macf.utils.input_origin import WAKE_OPENING, opens_with_wake


@pytest.fixture(autouse=True)
def _mail_box_from_the_home(monkeypatch):
    """These tests put mail in <home>/amail/pickup, the box chosen when nothing names one.
    Inside a seat MACEFF_AGENT_NAME is set, which would point the daemon elsewhere."""
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    monkeypatch.delenv("MACF_AMAIL_HANDOFF", raising=False)


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


def test_a_spinner_well_above_the_box_is_still_a_running_turn():
    """The shape of a real 2.1.288 capture: the spinner seven lines above the box's top rule,
    with the turn's output between them. Read as idle, the wake would be typed into a turn
    that is running."""
    output = ["  ⎿  line of the turn's output"] * 7
    assert wk.classify(screen(above=("● Bloviating… (5m 5s · ↓ 25.3k tokens)", *output))) == wk.RUNNING


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
    n.attach(ours, takes=TAKES)
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


def test_a_source_no_attached_channel_declared_is_typed(tmp_path, isolated_events_log):
    """R105 counted per source (MIS-0002-R149): a channel is attached, but its hello left mail
    out, so for mail there is no channel. After the grace the wake is typed, never held forever,
    and the channel is sent no mail record."""
    clock = [1000.0]
    n = nt.Notifier(_home_with_mail(tmp_path, ID1), {"amail": "agent"}, clock=lambda: clock[0])
    n.boot()
    pane = FakePane([screen()])
    n.waker = _waker(pane, []).waker
    ours, theirs = socket.socketpair()
    theirs.settimeout(0.2)
    n.attach(ours, takes=[s for s in TAKES if s != "amail"])
    assert n.flush() == 0 and n.owed, "mail went to a channel that didn't declare it"
    clock[0] += nt.CHANNEL_GRACE_S + 1
    assert n.wake() and len(pane.typed) == 1 and ID1 in pane.typed[0]
    assert not n.owed
    with pytest.raises(socket.timeout):
        theirs.recv(1)
    n.detach(ours)
    theirs.close()


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


# --- rule 14: a wake held too long reaches the operator through the outside watch ----------

def test_a_held_stretch_names_the_agent_and_is_released_when_nothing_waits():
    """The held event names the agent, so the outside watch can attribute it in a shared log,
    and a stretch that ends because the agent read its mail meanwhile is released, not left
    open for the watch to alert on."""
    events = []
    dialog = screen(below=("Do you want to proceed?", "❯ 1. Yes", "  2. No"))
    rig = _waker(FakePane([dialog]), events, card="Tester@abc123")
    ids = ["msg-1790000001-aaaaaaaaaaaa"]
    rig.waker.tick(ids)
    rig.waker.tick(ids)
    rig.waker.tick([])                          # the agent read it on its own
    rig.waker.tick([])
    names = [e for e, _ in events]
    assert names == [wk.EVENT_HELD, wk.EVENT_RELEASED]
    assert all(d.get("agent") == "Tester@abc123" for _, d in events)


def test_the_outside_watch_alerts_only_on_a_hold_past_its_allowance():
    from macf.pd import watch
    card, now = "Tester@abc123", 10_000.0
    held = {"timestamp": now - 2000, "event": "pd_wake_held", "data": {"agent": card, "reason": "dialog"}}
    assert watch.check_wake(card, held, now).verdict == "HELD"
    young = dict(held, timestamp=now - 60)
    assert watch.check_wake(card, young, now).verdict == "ALIVE"
    for clearing in ("pd_wake_sent", "pd_wake_released"):
        assert watch.check_wake(card, dict(held, event=clearing), now).verdict == "ALIVE"
    assert watch.check_wake(card, None, now).verdict == "ALIVE"


def test_the_outside_watch_reads_this_agents_newest_wake_event(tmp_path):
    import json
    from macf.pd import watch
    card, now = "Tester@abc123", 10_000.0
    log = tmp_path / "log.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in [
        {"timestamp": now - 3000, "event": "pd_wake_held", "data": {"agent": card, "reason": "dialog"}},
        {"timestamp": now - 100, "event": "pd_wake_sent", "data": {"agent": "Other@000000"}},
    ]))
    assert watch.last_wake_event(log, card, now)["event"] == "pd_wake_held"


def test_a_hold_followed_by_a_sent_wake_is_not_alerted(tmp_path):
    import json
    from macf.pd import watch
    card, now = "Tester@abc123", 10_000.0
    log = tmp_path / "log.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in [
        {"timestamp": now - 3000, "event": "pd_wake_held", "data": {"agent": card, "reason": "dialog"}},
        {"timestamp": now - 2500, "event": "pd_wake_sent", "data": {"agent": card}},
    ]))
    assert watch.check_wake(card, watch.last_wake_event(log, card, now), now).verdict == "ALIVE"


def test_a_hold_whose_reason_changes_is_measured_from_its_first_hold(tmp_path):
    """CTB's note on #663: a dialog then a draft writes a second hold, and the allowance must
    not start again with it. A hold after a sent wake starts a new stretch."""
    import json
    from macf.pd import watch
    card, now = "Tester@abc123", 10_000.0
    log = tmp_path / "log.jsonl"
    rows = [
        {"timestamp": now - 5000, "event": "pd_wake_held", "data": {"agent": card, "reason": "dialog"}},
        {"timestamp": now - 4000, "event": "pd_wake_sent", "data": {"agent": card}},
        {"timestamp": now - 2000, "event": "pd_wake_held", "data": {"agent": card, "reason": "dialog"}},
        {"timestamp": now - 900, "event": "pd_wake_sent", "data": {"agent": "Other@000000"}},
        {"timestamp": now - 60, "event": "pd_wake_held", "data": {"agent": card, "reason": "draft"}},
    ]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    newest = watch.last_wake_event(log, card, now)
    assert newest["held_since"] == now - 2000
    finding = watch.check_wake(card, newest, now)
    assert finding.verdict == "HELD" and "draft" in finding.detail


def test_a_hold_that_a_channel_ends_is_released(tmp_path, isolated_events_log):
    """CTB's probe on #663: a wake held by a dialog, then a channel attaches and takes the
    mail. The hold is released, so the outside watch doesn't alert on mail already delivered."""
    from macf.pd import watch
    clock = [1000.0]
    n = nt.Notifier(_home_with_mail(tmp_path, ID1), {"amail": "agent"}, clock=lambda: clock[0])
    n.boot()
    events = []
    dialog = screen(below=("Do you want to proceed?", "❯ 1. Yes", "  2. No"))
    n.waker = _waker(FakePane([dialog]), events, card="Tester@abc123").waker
    clock[0] += nt.CHANNEL_GRACE_S + 1
    n.wake()
    assert [e for e, _ in events] == [wk.EVENT_HELD]
    ours, theirs = socket.socketpair()
    n.attach(ours, takes=TAKES)
    n.flush()
    n.wake()
    n.wake()
    assert [e for e, _ in events] == [wk.EVENT_HELD, wk.EVENT_RELEASED]
    newest = {"timestamp": 0.0, "event": events[-1][0], "data": events[-1][1]}
    assert watch.check_wake("Tester@abc123", newest, 3600.0).verdict == "ALIVE"
    n.detach(ours)
    theirs.close()


# --- a hold that explains itself: the window said, the screen kept --------------------

def _sent_then_seen(pane_screens, events, **kw):
    """A waker that has sent a wake for ID1 at t=0 and seen its turn start at t=1."""
    h = _waker(FakePane(pane_screens), events, refractory_s=600.0, **kw)
    h.waker.tick([ID1])
    h.clock[0] += 1.0
    h.waker.tick([ID1])
    return h


RUNNING = screen(above=("✻ Working… (esc to interrupt)",))
DIALOG_SCREEN = screen(below=("Do you want to proceed?", "❯ 1. Yes", "  2. No"))


def test_a_refractory_hold_is_said_once_with_the_time_left():
    """On Oct 17 a mail inside the window waited 13 minutes with nothing in the log. The
    window is now said like any other hold: once per stretch, with the seconds left."""
    events = []
    h = _sent_then_seen([screen(), RUNNING, screen()], events)
    h.clock[0] += 59.0                                        # t=60, inside the window
    for _ in range(3):
        assert h.waker.tick([ID1, ID2]) is None
        h.clock[0] += 100.0
    held = [d for e, d in events if e == wk.EVENT_HELD]
    assert held == [{"reason": wk.REFRACTORY, "left_s": 540, "waiting": 1}]
    h.clock[0] += 300.0                                       # t=660, the window over
    assert h.waker.tick([ID1, ID2]) == "sent"
    assert [e for e, _ in events][-2:] == [wk.EVENT_HELD, wk.EVENT_SENT]


def test_a_refractory_stretch_ends_like_any_other():
    """Mail read inside the window releases the stretch; a dialog after the window is said
    again, because the reason changed."""
    events = []
    h = _sent_then_seen([screen(), RUNNING, DIALOG_SCREEN], events)
    h.clock[0] += 59.0
    h.waker.tick([ID1, ID2])
    h.clock[0] += 600.0
    h.waker.tick([ID1, ID2])
    held = [d["reason"] for e, d in events if e == wk.EVENT_HELD]
    assert held == [wk.REFRACTORY, wk.DIALOG]

    events = []
    h = _sent_then_seen([screen(), RUNNING, screen()], events)
    h.clock[0] += 59.0
    h.waker.tick([ID1, ID2])
    h.waker.tick([ID1])                                       # ID2 read on its own
    assert [e for e, _ in events][-2:] == [wk.EVENT_HELD, wk.EVENT_RELEASED]


def test_a_dialog_or_draft_hold_keeps_the_screen_it_read(tmp_path):
    """The demo's dialog holds at 01:33, 07:41 and 08:06 left nothing to check. A dialog or
    draft hold now keeps its screen, private to the agent, which the classifier reads the
    same way again, escape codes and all. A running turn keeps none, and a pane that could
    not be read says so."""
    draft = screen(f"half a thought {FAINT}(a suggestion){RESET}")
    kept = tmp_path / "wake_screens"
    events = []
    h = _waker(FakePane([DIALOG_SCREEN, draft, RUNNING]), events, screens_dir=kept,
               wall=lambda: 1792292400.0)
    for _ in range(3):
        h.clock[0] += 1.0
        h.waker.tick([ID1])
    held = [d for e, d in events if e == wk.EVENT_HELD]
    assert [d["reason"] for d in held] == [wk.DIALOG, wk.DRAFT, wk.RUNNING]
    for d, shown in zip(held[:2], (DIALOG_SCREEN, draft), strict=True):
        path = Path(d["screen"])
        assert path.parent == kept and path.read_text() == shown
        assert wk.classify(path.read_text()) == d["reason"]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(kept.stat().st_mode) == 0o700
    assert "screen" not in held[2] and len(list(kept.iterdir())) == 2

    class Unreadable(FakePane):
        def capture(self):
            return None
    events = []
    _waker(Unreadable([screen()]), events, screens_dir=kept).waker.tick([ID1])
    assert events == [(wk.EVENT_HELD, {"reason": wk.DIALOG, "waiting": 1, "captured": False})]


def test_only_the_newest_twenty_screens_are_kept(tmp_path):
    (tmp_path / "notes.txt").write_text("not the waker's")
    for i in range(wk.SCREENS_KEPT + 5):
        wk.save_screen(tmp_path, f"screen {i}", wk.DIALOG, 1792292400.0 + i)
    kept = {p.read_text() for p in tmp_path.glob("wake-*.txt")}
    assert kept == {f"screen {i}" for i in range(5, wk.SCREENS_KEPT + 5)}
    assert (tmp_path / "notes.txt").exists(), "a file the waker did not write was removed"


def test_the_outside_watch_takes_a_refractory_hold_for_pacing(tmp_path):
    """The window is the agent's pace, not something a person must clear: a dialog after it
    is measured from the dialog, and a refractory hold that a reached daily cap leaves
    newest all day never alerts."""
    import json
    from macf.pd import watch
    card, now = "Tester@abc123", 10_000.0
    log = tmp_path / "log.jsonl"
    rows = [
        {"timestamp": now - 4000, "event": "pd_wake_sent", "data": {"agent": card}},
        {"timestamp": now - 3990, "event": "pd_wake_held",
         "data": {"agent": card, "reason": "refractory", "left_s": 590}},
        {"timestamp": now - 1000, "event": "pd_wake_held", "data": {"agent": card, "reason": "dialog"}},
    ]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    newest = watch.last_wake_event(log, card, now)
    assert newest["held_since"] == now - 1000
    assert watch.check_wake(card, newest, now).verdict == "ALIVE"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows[:2]))
    assert watch.check_wake(card, watch.last_wake_event(log, card, now), now).verdict == "ALIVE"


def test_the_daemon_keeps_held_screens_beside_the_event_log(tmp_path):
    """The daemon gives its waker the agent's own screens directory, so a hold on a real
    session keeps its screen and not only a test's waker."""
    import pwd
    from macf.pd.daemon import Daemon
    from macf.pd.interface import Unit
    from test_primal_daemon import make_home
    me = pwd.getpwuid(os.getuid()).pw_name
    home = make_home(tmp_path, [Unit(name="session", kind="session", command=["true"], account=me,
                                     restart="always", liveness_interval_s=120, memory_limit_mb=64)])
    runtime = Path(tempfile.mkdtemp(prefix="pd-", dir="/tmp"))
    try:
        daemon = Daemon(home, base=runtime)
        assert daemon.notifier.waker.screens_dir == home / ".maceff" / "wake_screens"
    finally:
        shutil.rmtree(runtime, ignore_errors=True)


# --- the agent paces its wake (persistent_layer 1.9) ---------------------------------------

def test_the_declared_window_and_the_wakes_default_are_one_value():
    from macf.pd.interface import DEFAULT_WAKE_REFRACTORY_S, Declaration
    assert wk.REFRACTORY_S == DEFAULT_WAKE_REFRACTORY_S == Declaration(version=1, agent="A@1").wake_refractory_s


def test_a_pace_may_shorten_the_window_to_the_floor_and_never_past_it():
    """Only the declaration sets the floor: a pace may lengthen the window, or shorten it down to
    the floor, and None goes back to the declared window."""
    assert wk.pace_refusal(300, None) is None
    assert wk.pace_refusal(300, 300) is None
    assert wk.pace_refusal(1200, 300) is None
    assert wk.pace_refusal(None, 300) is None
    refused = wk.pace_refusal(299, 300)
    assert refused and "300" in refused and "floor" in refused


def test_no_pace_goes_over_the_ceiling_and_none_is_infinite():
    """#761 review: an unbounded pace muted the wake and was never alerted on."""
    assert wk.pace_refusal(1800, None, 1800) is None
    refused = wk.pace_refusal(1801, None, 1800)
    assert refused and "1800" in refused and "ceiling" in refused
    for bad in (float("inf"), float("nan")):
        assert "finite" in wk.pace_refusal(bad, None, None)


def test_the_default_ceiling_is_the_watchs_allowance_for_a_held_wake():
    """So a pace can never keep an agent unwoken past the point where a stuck wake alerts."""
    from macf.pd.interface import DEFAULT_WAKE_REFRACTORY_CEILING_S
    from macf.pd.watch import WAKE_HELD_ALERT_S
    assert DEFAULT_WAKE_REFRACTORY_CEILING_S == WAKE_HELD_ALERT_S


def test_the_newest_pace_holds_at_boot_and_a_raised_floor_wins_saying_so():
    paced = {"timestamp": 1_800_000_000, "data": {"refractory_s": 120.0, "reason": "a busy hour",
                                                   "asked_by": {"kind": "agent"}}}
    assert wk.window_at_boot(600.0, None, None) == (600.0, "the declaration")
    window, source = wk.window_at_boot(600.0, None, paced)
    assert window == 120.0 and "a busy hour" in source and "by the agent" in source
    window, source = wk.window_at_boot(600.0, 300.0, paced)
    assert window == 300.0 and "floor" in source and "120" in source
    back = {"timestamp": 1_800_000_000, "data": {"refractory_s": None, "reason": "done"}}
    window, source = wk.window_at_boot(900.0, None, back)
    assert window == 900.0 and "declaration" in source


def test_a_saved_pace_over_the_ceiling_or_not_finite_is_held_to_the_ceiling_at_boot():
    for wanted in (7200.0, float("inf"), float("nan")):
        paced = {"timestamp": 1_800_000_000, "data": {"refractory_s": wanted, "reason": "quiet",
                                                       "asked_by": {"kind": "agent"}}}
        window, source = wk.window_at_boot(600.0, None, paced, 1800.0)
        assert window == 1800.0 and "ceiling" in source, (wanted, source)


def test_a_window_paced_shorter_lets_the_next_tick_wake(tmp_path):
    """The window is measured at every tick, so a pace that shortens it holds from the next one."""
    events = []
    h = _sent_then_seen([screen(), RUNNING, screen()], events)
    h.clock[0] += 59.0                                        # t=60, inside the 600 s window
    assert h.waker.tick([ID1, ID2]) is None
    notifier = nt.Notifier(tmp_path, {}, append=lambda e, d: True, events=lambda: [])
    notifier.waker = h.waker
    notifier.pace(30.0)
    assert h.waker.refractory_s == 30.0
    assert h.waker.tick([ID1, ID2]) == "sent"
