"""The keystroke fallback's screen reader against real captured screens (MIS-0002-R45).

The four captures, from clients 2.1.281 to 2.1.288, come from the mail clock that typed wakes
before the daemon did, and so do these cases. Conversation text in them was replaced when they
were captured. Each case is a way a typed wake once went wrong, or nearly did.
"""
import re
from pathlib import Path

from macf.pd import wake

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wake_panes"
SUGGESTION = "\x1b[2myes, re-arm the Wednesday reminders\x1b[0m"
RULE = chr(0x2500) * 80
EMPTY_PROMPT = "\x1b[38;5;246m" + chr(0x276F) + "\xa0\x1b[39m"


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")


def test_an_idle_client_with_a_faint_suggestion_is_idle():
    assert wake.classify(fixture("idle_faint_suggestion_2.1.284")) == wake.IDLE_EMPTY


def test_the_echo_of_a_submitted_wake_is_not_a_wake_in_the_box():
    screen = fixture("idle_faint_suggestion_wake_echo_2.1.281")
    plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", screen)
    assert re.search(r"(?m)^\s*[❯>] MAIL CLOCK:", plain)     # what the clock's old check matched
    assert wake.classify(screen) == wake.IDLE_EMPTY


def test_typed_text_in_the_box_is_a_draft():
    screen = fixture("idle_faint_suggestion_wake_echo_2.1.281")
    assert SUGGESTION in screen
    assert wake.classify(screen.replace(SUGGESTION, "yes, re-arm the Wednesday reminders")) == wake.DRAFT


def test_a_wake_left_in_the_box():
    """The daemon's own wake left in the box is a wake in the box, which may be submitted. A
    mail clock's wake left there is the daemon's draft, never submitted by it: both are busy."""
    screen = fixture("idle_faint_suggestion_wake_echo_2.1.281")
    ours = screen.replace(SUGGESTION, wake.wake_text(["msg-1790000001-aaaaaaaaaaaa"]))
    assert wake.classify(ours) == wake.WAKE_IN_BOX
    clocks = screen.replace(SUGGESTION, "MAIL CLOCK: 1 new amail pair(s) in your pickup box")
    assert wake.classify(clocks) == wake.DRAFT


def test_a_permission_dialog_is_never_typed_into():
    assert wake.classify(fixture("permission_dialog_2.1.281")) == wake.DIALOG


def test_a_spinner_without_esc_to_interrupt_is_a_running_turn():
    """2.1.288 prints only the spinner, here seven lines above the box."""
    screen = fixture("turn_running_2.1.288")
    assert "esc to interrupt" not in screen
    assert wake.classify(screen) == wake.RUNNING


def test_a_spinner_naming_a_running_hook_is_a_running_turn():
    """2.1.300, captured during a PreToolUse hook: the spinner names the hook before the
    elapsed time. Every tool call shows it for about a second, and with the box empty below it
    that second read idle, so a wake was typed into a running turn."""
    screen = fixture("hook_running_2.1.300")
    assert "running PreToolUse hook" in screen
    assert wake.classify(screen) == wake.RUNNING


def test_a_spinner_with_or_without_a_phrase_before_the_time():
    for line in ("Accomplishing… (26m 20s · ↓ 72.1k tokens)",
                 "Accomplishing… (running PreToolUse hook · 26m 20s · ↓ 72.1k tokens)",
                 "Pondering… (running Stop hooks · 1h 2m 3s)",
                 "Pondering… (thinking · 45s)"):
        assert wake._SPINNER.search(line), line
    # an ellipsis and a parenthesis with no elapsed time is not a spinner
    for line in ("Waiting… (no output yet)", "see the notes… (part 2)"):
        assert not wake._SPINNER.search(line), line


def test_esc_to_interrupt_in_the_mode_line_is_a_running_turn():
    screen = fixture("idle_faint_suggestion_wake_echo_2.1.281")
    running = screen.replace("for agents", "esc to interrupt · ← for agents", 1)
    assert running != screen
    assert wake.classify(running) == wake.RUNNING


def test_a_dialog_under_an_empty_prompt_frame_is_still_a_dialog():
    """A rule-like line higher up (the client draws a markdown rule as one) and an empty prompt
    line under it pair with the dialog's border; only the dialog's footer tells them apart."""
    screen = RULE + "\n" + EMPTY_PROMPT + "\n" + fixture("permission_dialog_2.1.281")
    assert wake.classify(screen) == wake.DIALOG


def test_a_short_dialog_under_an_empty_prompt_frame_is_still_a_dialog():
    dialog = ["Do you want to proceed?", chr(0x276F) + " 1. Yes", "  2. No", "",
              "\x1b[38;5;246mEsc\x1b[39m \x1b[38;5;246mto\x1b[39m \x1b[38;5;246mcancel\x1b[39m"]
    assert wake.classify("\n".join([RULE, EMPTY_PROMPT, RULE] + dialog)) == wake.DIALOG


def test_a_frame_without_the_prompt_glyph_is_not_an_input_box():
    assert wake.classify("\n".join(["  output", RULE, "", RULE, "  a status line"])) == wake.DIALOG


def test_a_long_screen_under_the_last_rule_is_not_an_input_box():
    overlay = "\n".join(f"  overlay line {i}" for i in range(9))
    assert wake.classify(fixture("idle_faint_suggestion_2.1.284") + "\n" + overlay) == wake.DIALOG


def test_a_screen_with_no_input_box_is_busy():
    assert wake.classify("") == wake.DIALOG
    assert wake.classify("some output\nmore output\n") == wake.DIALOG


LABELED = "labeled_border_draft_2.1.300"
FOLLOWER_TEXT = "The compaction you queued with inject compact has finished."


def _emptied(screen: str) -> str:
    """*screen* with its input box emptied: the prompt line bare, its wrapped lines gone."""
    lines = screen.splitlines()
    plain = [re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line) for line in lines]
    start = next(i for i, line in enumerate(plain) if line.startswith(chr(0x276F)))
    end = next(i for i in range(start + 1, len(plain)) if plain[i].count(chr(0x2500)) >= 20)
    return "\n".join(lines[:start] + [EMPTY_PROMPT] + lines[end:]) + "\n"


def test_a_border_carrying_the_session_name_is_still_the_input_box():
    """2.1.300 prints the session's name in the box's top border. Read as no box at all, every
    screen was a dialog: no wake was typed, and a follower's typed text was never submitted."""
    screen = fixture(LABELED)
    assert "my-session" in screen
    assert wake.classify(screen) == wake.DRAFT
    assert FOLLOWER_TEXT in wake.box_text(screen)
    assert wake.classify(_emptied(screen)) == wake.IDLE_EMPTY


def test_a_draft_is_read_while_a_turn_runs():
    """Text typed during a turn lands after whatever the box already holds."""
    spinner = "✳ Working… (12s · ↓ 1.2k tokens)\n"
    running = spinner + fixture(LABELED)
    assert wake.classify(running) == wake.RUNNING
    assert wake.box_text(running) is None                 # nothing is typed into a running turn
    assert FOLLOWER_TEXT in wake.draft_text(running)
    assert wake.draft_text(spinner + _emptied(fixture(LABELED))) == ""
    assert wake.draft_text(fixture("permission_dialog_2.1.281")) is None


def test_a_short_labeled_rule_in_the_conversation_is_not_a_border():
    short = chr(0x2500) * 8 + " notes " + chr(0x2500) * 4
    assert wake.classify("\n".join([short, EMPTY_PROMPT, RULE, "  a status line"])) == wake.DIALOG
