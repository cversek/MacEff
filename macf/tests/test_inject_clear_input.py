"""inject clear-input: an agent empties its own input box of framework text it recognizes.

A seat's box held a stale mail clock line for half a day (Oct 24 to 25). Every
``inject compact`` refused, rightly, and told the seat to clear the box, but nothing the
seat could run would clear it, and a fixed ``C-u C-u`` typed from outside left it half
full: each Ctrl-U erases one screen row, or the line break before the cursor when the
row is empty. So the clearing re-reads the box after every press, and stops at the
first thing that is not the expected text shrinking.
"""

from types import SimpleNamespace
from unittest.mock import patch

from macf import supervisor

MAIL = "MAIL CLOCK: 1 new amail pair(s) in your pickup box (1 waiting)."


def _clear(boxes, expect="MAIL CLOCK:", typed_by="wake", **kw):
    """Run clear_own_input against a pane whose box reads *boxes* in turn, the first before
    any press and one after each; returns the exit status, the keys pressed and what was
    recorded as cleared."""
    presses, cleared = [], []

    def run(argv, *a, **k):
        presses.append(argv[-1])
        return SimpleNamespace(returncode=0)

    with patch.object(supervisor, "own_pane_target", return_value="seat"), \
         patch.object(supervisor, "_resolve_pane_target", return_value={"tmux_session": "s"}), \
         patch.object(supervisor, "_tmux_available", return_value=True), \
         patch.object(supervisor, "_draft_in_box", side_effect=list(boxes)), \
         patch.object(supervisor, "_framework_typed", return_value=typed_by), \
         patch.object(supervisor, "_record_keys_sent"), \
         patch.object(supervisor, "_record_box_cleared",
                      side_effect=lambda text, n, s: cleared.append((text, n))), \
         patch.object(supervisor.subprocess, "run", side_effect=run):
        rc = supervisor.clear_own_input(expect, sleep=lambda s: None, **kw)
    return SimpleNamespace(rc=rc, presses=presses, cleared=cleared)


def test_a_framework_line_over_several_rows_is_cleared_and_recorded():
    # Rows go one press at a time; the press at an empty row only removes its line break,
    # which reads the same once the rows are joined.
    boxes = [MAIL + " second line", MAIL + " second line", MAIL, MAIL[:20], ""]
    r = _clear(boxes)
    assert r.rc == 0
    assert r.presses == ["C-u"] * 4
    assert r.cleared == [(MAIL + " second line", 4)]


def test_a_box_that_does_not_start_with_the_expected_text_is_left_alone(capsys):
    r = _clear(["dear operator, about the budget"])
    assert r.rc == 1 and r.presses == [] and r.cleared == []
    assert "dear operator" in capsys.readouterr().err


def test_an_empty_box_needs_nothing():
    r = _clear([""])
    assert r.rc == 0 and r.presses == []


def test_a_box_that_stops_shrinking_is_reported_not_pressed_forever(capsys):
    r = _clear([MAIL] * 10)
    assert r.rc == 1 and len(r.presses) == supervisor.CLEAR_STALL and r.cleared == []
    assert "stopped shrinking" in capsys.readouterr().err


def test_text_that_grows_while_clearing_stops_it(capsys):
    """Someone typing: the box gains what was not there, so the clearing stops."""
    r = _clear([MAIL, MAIL[:30], MAIL[:30] + " hello"])
    assert r.rc == 1 and len(r.presses) == 2 and r.cleared == []
    assert "someone" in capsys.readouterr().err


def test_no_expected_text_presses_nothing(capsys):
    r = _clear([MAIL], expect="  ")
    assert r.rc == 1 and r.presses == []
    assert "--expect" in capsys.readouterr().err


def test_a_draft_no_framework_keystroke_typed_is_refused_even_with_the_right_words(capsys):
    """Whose text it is comes from the framework's record, never from the agent asking."""
    r = _clear([MAIL, ""], typed_by=None)
    assert r.rc == 1 and r.presses == [] and r.cleared == []
    assert "person's draft" in capsys.readouterr().err


def _compact_refusal(typed_by):
    with patch.object(supervisor, "own_pane_target", return_value="seat"), \
         patch.object(supervisor, "_draft_in_box", return_value=MAIL), \
         patch.object(supervisor, "_framework_typed", return_value=typed_by), \
         patch.object(supervisor, "send_keys", return_value=0) as send:
        assert supervisor.send_slash_to_self("compact", then=None) == 1
    send.assert_not_called()


def test_inject_compact_refusal_names_the_clearing_command_for_framework_text(capsys):
    _compact_refusal("wake")
    assert "macf_tools inject clear-input --expect 'MAIL CLOCK: 1'" in capsys.readouterr().err


def test_inject_compact_refusal_says_ask_them_for_a_persons_draft(capsys):
    _compact_refusal(None)
    err = capsys.readouterr().err
    assert "clear-input" not in err and "ask them" in err


def _keys_sent(*records):
    """Events as read_events yields them, newest first, from (age_s, text, kind) tuples."""
    now = 1_000_000.0
    return now, [{"timestamp": now - age, "event": "keys_sent", "data": {"text": text, "kind": kind}}
                 for age, text, kind in records]


def test_box_text_the_framework_typed_is_found_across_wraps_and_partial_clears():
    from macf.utils import input_origin
    now, events = _keys_sent((3600, "MAIL CLOCK: 1 new amail pair(s)\nRead EACH", "send-keys"))
    with patch("macf.agent_events_log.read_events", return_value=iter(events)):
        assert input_origin.framework_typed_box_text("MAIL CLOCK: 1  new amail", now=now) == "send-keys"


def test_text_a_person_added_or_typed_is_not_the_frameworks():
    from macf.utils import input_origin
    now, events = _keys_sent((60, "[maceff:wake] mail waiting", "wake"), (30, "C-u", "clear_input"))
    for box in ("hi [maceff:wake] mail waiting", "dear operator", "C-u"):
        with patch("macf.agent_events_log.read_events", return_value=iter(events)):
            assert input_origin.framework_typed_box_text(box, now=now) is None


def test_a_keystroke_older_than_the_window_does_not_count():
    from macf.utils import input_origin
    now, events = _keys_sent((input_origin.BOX_TEXT_WINDOW_SECONDS + 60, MAIL, "send-keys"))
    with patch("macf.agent_events_log.read_events", return_value=iter(events)):
        assert input_origin.framework_typed_box_text(MAIL, now=now) is None


def test_clear_input_refuses_another_pane(capsys):
    from macf.cli import _cmd_inject
    args = SimpleNamespace(command="clear-input", target="other-seat", expect="MAIL")
    with patch.object(supervisor, "clear_own_input") as clear:
        assert _cmd_inject(args) == 1
    clear.assert_not_called()
    assert "own pane" in capsys.readouterr().err
