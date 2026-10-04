"""`permissions history`: past permission dialogs, read from the event log alone.

The event shapes below are copied from a real agent log (2026-10-04): a
``permission_requested`` carries the tool and its input in ``hook_input`` but not
the rule that asked; a ``tool_call_completed`` carries the same tool and input
once an approved command has run. Nothing here writes a state file.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from macf import permission_watch as pw

SID_A, SID_B = "aaaa1111-0000", "bbbb2222-0000"


def request(t, sid, tool="Bash", command="git push -u origin b", cwd="/w"):
    tool_input = {"command": command} if tool == "Bash" else {"questions": [{"question": "?"}]}
    return {"event": "permission_requested", "timestamp": t,
            "data": {"session_id": sid, "tool_name": tool, "permission_type": "unknown",
                     "tool_input_preview": str(tool_input)[:200], "timestamp": t},
            "hook_input": {"session_id": sid, "tool_name": tool, "tool_input": tool_input,
                           "cwd": cwd, "permission_mode": "auto"}}


def completed(t, sid, tool="Bash", command="git push -u origin b"):
    return {"event": "tool_call_completed", "timestamp": t,
            "data": {"session_id": sid, "success": True, "tool": tool},
            "hook_input": {"session_id": sid, "tool_name": tool, "tool_use_id": "toolu_x",
                           "tool_input": {"command": command, "description": "added by the client"}}}


def plain(name, t, sid=None):
    data = {"session_id": sid} if sid else {}
    return {"event": name, "timestamp": t, "data": data}


def test_an_approved_command_ran_and_waited_until_it_finished():
    events = [request(100, SID_A), plain("notification_received", 110, SID_A),
              plain("user_activity_detected", 115), completed(160, SID_A), plain("dev_drv_ended", 170, SID_A)]
    (d,) = pw.history(events)
    assert (d.outcome, d.tool, d.command) == ("ran", "Bash", "git push -u origin b")
    assert d.waited_minutes == pytest.approx(1.0)  # notification and typing elsewhere decide nothing


def test_a_command_that_never_ran_is_not_run_when_the_turn_ends():
    events = [request(100, SID_A), completed(130, SID_A, command="ls"), plain("dev_drv_ended", 400, SID_A)]
    (d,) = pw.history(events)
    assert d.outcome == "not run"
    assert d.waited_minutes == pytest.approx(0.5)  # answered at the first progress, the other tool


def test_a_dialog_with_nothing_after_it_is_still_waiting():
    (d,) = pw.history([request(100, SID_A), plain("notification_received", 101, SID_A)])
    assert (d.outcome, d.waited_minutes) == ("waiting", None)


def test_sessions_are_paired_separately():
    events = [request(100, SID_A), request(105, SID_B, command="git reset --hard origin/main"),
              completed(200, SID_B, command="git reset --hard origin/main"), plain("dev_drv_ended", 700, SID_A)]
    a, b = pw.history(events)
    assert (a.session_id, a.outcome) == (SID_A, "not run")
    assert (b.session_id, b.outcome, b.waited_minutes) == (SID_B, "ran", pytest.approx(95 / 60))


def test_a_question_to_the_operator_is_not_a_permission():
    events = [request(100, SID_A, tool="AskUserQuestion"), completed(130, SID_A, tool="AskUserQuestion")]
    assert pw.history(events) == []
    assert [d.tool for d in pw.history(events, include_questions=True)] == ["AskUserQuestion"]


@pytest.mark.parametrize("command, rule", [
    ("git push -u origin b", "Bash(git push:*)"),
    ("cd /w/repo && git push -u origin b 2>&1 | tail -2", "Bash(git push:*)"),  # a segment of a chain
    ("git -C /w/repo push origin b", None),                                      # the prefix is not there
    ("git pushx", None),                                                         # a word, not a prefix of one
    ("D=/w; cd $D && git reset --hard origin/main", "Bash(git reset --hard:*)"),
    ("rm -rf build", "Bash(rm -rf build)"),                                      # an exact rule
])
def test_ask_rules_match_with_the_clients_prefix_meaning(command, rule):
    rules = ["Bash(git push:*)", "Bash(git reset --hard:*)", "Bash(rm -rf build)", "WebFetch"]
    assert pw.matching_rule("Bash", {"command": command}, rules) == rule


def test_a_bare_tool_rule_matches_the_tool():
    assert pw.matching_rule("WebFetch", {"url": "https://x"}, ["Bash(ls:*)", "WebFetch"]) == "WebFetch"


def test_ask_rules_come_from_home_and_the_project_the_dialog_ran_in(tmp_path):
    home = tmp_path / "home"
    project = home / "work" / "repo"
    (home / ".claude").mkdir(parents=True)
    (project / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.local.json").write_text(json.dumps({"permissions": {"ask": ["Bash(git push:*)"]}}))
    (project / ".claude" / "settings.local.json").write_text(json.dumps(
        {"permissions": {"ask": ["Bash(git reset --hard:*)", "Bash(git push:*)"], "deny": ["Bash(git push -f:*)"]}}))
    assert pw.ask_rules(str(project / "sub"), home) == ["Bash(git push:*)", "Bash(git reset --hard:*)"]


def test_the_cli_reads_only_the_log_and_writes_nothing(tmp_path):
    import time
    now = time.time()
    log = tmp_path / "agent_events_log.jsonl"
    old = request(now - 9 * 86400, SID_A, command="git push old")  # outside the default 7 days
    events = [old, completed(now - 9 * 86400 + 30, SID_A, command="git push old"),
              request(now - 600, SID_A), completed(now - 480, SID_A), plain("dev_drv_ended", now - 470, SID_A)]
    log.write_text("".join(json.dumps(e) + "\n" for e in events))
    before = sorted(p.name for p in tmp_path.iterdir())
    env = dict(os.environ, MACF_EVENTS_LOG_PATH=str(log), HOME=str(tmp_path))
    out = subprocess.run([sys.executable, "-m", "macf.cli", "permissions", "history", "--json"],
                         capture_output=True, text=True, env=env, timeout=60)
    assert out.returncode == 0, out.stderr
    rows = json.loads(out.stdout)
    assert [(r["command"], r["outcome"]) for r in rows] == [("git push -u origin b", "ran")]
    assert rows[0]["waited_minutes"] == pytest.approx(2.0, abs=0.01)
    assert sorted(p.name for p in tmp_path.iterdir()) == before  # no state file appeared
