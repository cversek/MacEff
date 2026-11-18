"""Knowing what would stop at a dialog before running it, and refusing it when nobody can answer.

On 2026-10-24 a container seat in AUTO_MODE waited seven hours on one permission dialog, with the
operator away. Its command ended in a cleanup, ``; rm -r <scratch>``, and the Ask rule
``Bash(rm -r:*)`` matched that part. The operator asked for prevention: a way to list the rules,
a way to check a command, and a refusal instead of a hang while nobody is at the keyboard
(autonomous_operation 5.5).
"""
import argparse
import json

import pytest

from macf import permission_watch as pw

HANG = 'E=$(ls -d x); (cd $E && CUDA_VISIBLE_DEVICES="" timeout 300 python3 -B - ); rm -r /tmp/s/redproof'


@pytest.fixture
def settings(tmp_path):
    """A home whose user file allows git push and denies sudo, and a project whose local file
    asks for rm -r, as the seat's did."""
    home, project = tmp_path / "home", tmp_path / "proj"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(json.dumps(
        {"permissions": {"allow": ["Bash(git push:*)", "Bash(rm -r:*)"], "deny": ["Bash(sudo:*)"]}}))
    (project / ".claude").mkdir(parents=True)
    (project / ".git").mkdir()
    (project / ".claude" / "settings.local.json").write_text(json.dumps(
        {"permissions": {"ask": ["Bash(rm -r:*)", "Bash(git reset --hard:*)"]}}))
    return home, project


def test_the_rules_in_force_come_with_their_files(settings):
    home, project = settings
    rules = pw.rules_in_force(str(project), home, environ={})
    assert ("ask", "Bash(rm -r:*)", project / ".claude" / "settings.local.json") in rules
    assert ("deny", "Bash(sudo:*)", home / ".claude" / "settings.json") in rules
    assert ("allow", "Bash(git push:*)", home / ".claude" / "settings.json") in rules


@pytest.mark.parametrize("command, kind", [
    (HANG, "ask"),                                  # the seven-hour command: its chained cleanup asks
    ("git push -u origin x", "allow"),
    ("sudo rm -r /x", "deny"),                      # deny wins over the ask the rm -r part meets
    ("rm -r /tmp/x", "ask"),                        # an ask wins over an allow of the same command
    ("python3 -B script.py", "unlisted"),
])
def test_a_call_is_judged_deny_then_ask_then_allow(settings, command, kind):
    home, project = settings
    assert pw.decide("Bash", {"command": command}, pw.rules_in_force(str(project), home, environ={})).kind == kind


def test_check_names_the_part_of_a_chain_that_asks_and_exits_by_verdict(monkeypatch, settings, capsys):
    from macf import cli
    home, project = settings
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    ns = argparse.Namespace
    assert cli.cmd_permissions_check(ns(command=HANG, tool="Bash")) == 1
    out = capsys.readouterr().out
    assert out.startswith("PROMPTS: Bash(rm -r:*)") and "this part: rm -r /tmp/s/redproof" in out
    assert cli.cmd_permissions_check(ns(command="git push", tool="Bash")) == 0
    assert cli.cmd_permissions_check(ns(command="sudo ls", tool="Bash")) == 2


def test_list_shows_each_kind_with_its_file(monkeypatch, settings, capsys):
    from macf import cli
    home, project = settings
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    assert cli.cmd_permissions_list(argparse.Namespace(kind=None, json=False)) == 0
    out = capsys.readouterr().out
    assert out.index("DENY") < out.index("ASK") < out.index("ALLOW")
    assert "Bash(rm -r:*)" in out and "settings.local.json" in out
    assert cli.cmd_permissions_list(argparse.Namespace(kind="ask", json=True)) == 0
    assert {r["rule"] for r in json.loads(capsys.readouterr().out)} == {"Bash(rm -r:*)", "Bash(git reset --hard:*)"}


@pytest.mark.parametrize("modes, command, refused", [
    ({"AUTO_MODE", "USER_IDLE"}, HANG, True),
    ({"AUTO_MODE", "USER_REMOTE"}, "rm -r /tmp/x", True),
    ({"AUTO_MODE"}, HANG, False),                       # the operator is at the keyboard
    ({"USER_IDLE"}, HANG, False),                       # MANUAL_MODE: the operator drives
    ({"AUTO_MODE", "USER_IDLE"}, "git push", False),    # runs without a dialog
    ({"AUTO_MODE", "USER_IDLE"}, "python3 x.py", False),  # no rule: the permission mode's call
])
def test_an_asking_call_is_refused_only_while_nobody_can_answer(settings, modes, command, refused):
    home, project = settings
    why = pw.unattended_refusal("Bash", {"command": command}, modes, str(project), home, environ={})
    assert bool(why) is refused
    if refused:
        assert "Bash(rm -r:*)" in why and "permissions check" in why


def test_the_hook_refuses_the_seven_hour_command_while_the_operator_is_idle(monkeypatch, settings):
    from macf.hooks import handle_pre_tool_use as hook
    home, project = settings
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setattr(hook, "detect_active_modes", lambda sid, ti: {"AUTO_MODE", "USER_IDLE"})
    out = hook.run(json.dumps({"tool_name": "Bash", "tool_input": {"command": HANG}, "session_id": "s-g"}))
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny" and "rm -r /tmp/s/redproof" in decision["permissionDecisionReason"]
    assert out.get("continue") is not False                 # the agent reads the reason and goes on
    monkeypatch.setattr(hook, "detect_active_modes", lambda sid, ti: {"AUTO_MODE"})
    out = hook.run(json.dumps({"tool_name": "Bash", "tool_input": {"command": HANG}, "session_id": "s-g"}))
    assert out.get("hookSpecificOutput", {}).get("permissionDecision") != "deny"


def test_session_start_names_the_ask_rules_in_force(settings):
    from macf.hooks.handle_session_start import _ask_rules_block
    home, project = settings
    block = _ask_rules_block(str(project), home, environ={})
    assert "2 Ask rule(s)" in block and "Bash(rm -r:*)" in block and "permissions check" in block
    assert _ask_rules_block(str(home), home / "nowhere", environ={}) == ""      # none in force: silent
