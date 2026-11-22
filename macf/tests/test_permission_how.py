"""`permissions how` (#1060): how each tool call was approved, derived from the event log and the
rules in force, with no record of its own. A dialog before the call means the operator answered it;
otherwise an allow rule matched; otherwise the permission mode (or its classifier) let it through."""
from pathlib import Path

from macf import permission_watch as pw

SID = "aaaa1111-0000"
SETTINGS = Path("/w/.claude/settings.json")
RULES = [("allow", "Bash(git status:*)", SETTINGS), ("ask", "Bash(git push:*)", SETTINGS)]


def started(t, command, mode="auto", tool="Bash"):
    return {"event": "tool_call_started", "timestamp": t,
            "data": {"session_id": SID, "tool": tool},
            "hook_input": {"session_id": SID, "tool_name": tool, "tool_input": {"command": command},
                           "permission_mode": mode}}


def request(t, command, tool="Bash"):
    return {"event": "permission_requested", "timestamp": t,
            "data": {"session_id": SID, "tool_name": tool, "timestamp": t},
            "hook_input": {"session_id": SID, "tool_name": tool, "tool_input": {"command": command},
                           "cwd": "/w", "permission_mode": "auto"}}


def completed(t, command, tool="Bash"):
    return {"event": "tool_call_completed", "timestamp": t,
            "data": {"session_id": SID, "success": True, "tool": tool},
            "hook_input": {"session_id": SID, "tool_name": tool, "tool_input": {"command": command}}}


def turn_end(t):
    return {"event": "dev_drv_ended", "timestamp": t, "data": {"session_id": SID}}


def test_a_dialog_the_call_ran_after_was_approved_there():
    events = [started(100, "git push"), request(101, "git push"), completed(130, "git push"), turn_end(140)]
    (a,) = pw.approvals(events, RULES)
    assert a.how == "dialog" and "approved" in a.detail and a.command == "git push"


def test_a_dialog_the_call_never_ran_after_was_denied():
    events = [started(100, "git push"), request(101, "git push"), turn_end(140)]
    (a,) = pw.approvals(events, RULES)
    assert a.how == "dialog" and "denied" in a.detail


def test_no_dialog_and_an_allow_rule_names_the_rule_and_its_file():
    events = [started(100, "git status --short"), completed(101, "git status --short")]
    (a,) = pw.approvals(events, RULES)
    assert a.how == "rule" and "Bash(git status:*)" in a.detail and str(SETTINGS) in a.detail


def test_a_chain_is_the_rules_only_when_every_part_is_allowed():
    rules = RULES + [("allow", "Bash(ls:*)", SETTINGS)]
    events = [started(100, "export X=1; git status"), started(110, "git status && ls -la"),
              completed(101, "export X=1; git status"), completed(111, "git status && ls -la")]
    partly, wholly = pw.approvals(events, rules)
    assert partly.how == "mode"
    assert wholly.how == "rule" and "Bash(git status:*)" in wholly.detail and "Bash(ls:*)" in wholly.detail


def test_no_dialog_and_no_allow_rule_is_the_permission_mode():
    events = [started(100, "ls -la", mode="auto"), completed(101, "ls -la")]
    (a,) = pw.approvals(events, RULES)
    assert a.how == "mode" and "auto" in a.detail and "classifier" in a.detail


def test_one_dialog_answers_one_call_even_when_two_identical_calls_wait_on_it():
    """Parallel calls: two identical pushes start before the one dialog opens."""
    events = [started(100, "git push"), started(100.5, "git push"), request(101, "git push"),
              completed(120, "git push"), completed(121, "git push"), turn_end(125)]
    first, second = pw.approvals(events, RULES)
    assert first.how == "dialog" and second.how != "dialog"


def test_the_text_says_the_rules_are_todays():
    events = [started(100, "git status"), completed(101, "git status")]
    text = pw.approvals_text(pw.approvals(events, RULES))
    assert "today's rules" in text and "Bash(git status:*)" in text
