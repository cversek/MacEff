"""Calling-card sign-off and default-branch pushes, enforced where an agent acts.

Unit tests pin the rules; the end-to-end tests run real git through the
installed dispatcher, because the pre-push guard depends on the dispatcher
handing git's stdin to its hooklets -- which it did not do before this change
(a hooklet inherited the dispatcher's own here-document instead).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from macf import attribution as A

CARD = "Tester@abcdef"
GOOD = f"[{CARD}: task#7 s_1/c_2/p_3/t_4]"


@pytest.fixture
def agent(tmp_path, monkeypatch):
    """An agent home that opts into both checks, inside an agent session."""
    home = tmp_path / "agent_home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text("abcdef0123456789\n")
    cfg = {"agent_identity": {"calling_card": "Tester"},
           "opsec": {"public_attribution": True},
           "git": {"forbid_default_branch_push": True}}
    (home / ".maceff" / "config.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(home))
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    return home


def _set(home, **cfg):
    (home / ".maceff" / "config.json").write_text(json.dumps(
        {"agent_identity": {"calling_card": "Tester"}, **cfg}))


# ------------------------------------------------------------- the card line

def test_own_card_plain_or_italic_is_accepted():
    pat = A.card_line_pattern(CARD)
    assert pat.match(GOOD)
    assert pat.match(f"*{GOOD}*")


def test_another_agents_card_is_not_a_sign_off():
    assert not A.card_line_pattern(CARD).match("[Other@123456: task#7 s_1/c_2/p_3/t_4]")


def test_card_must_be_the_last_line(agent, tmp_path):
    msg = tmp_path / "m"
    msg.write_text(f"fix: x\n\n{GOOD}\n\nCo-Authored-By: someone\n")
    assert A.check_commit_message(msg) is not None


# ------------------------------------------------------------- commit-msg

def test_commit_with_card_passes_and_git_comments_are_ignored(agent, tmp_path):
    msg = tmp_path / "m"
    msg.write_text(f"fix: x\n\nbody\n\n{GOOD}\n# Please enter the commit message\n")
    assert A.check_commit_message(msg) is None


def test_commit_without_card_is_refused_and_names_the_card(agent, tmp_path):
    msg = tmp_path / "m"
    msg.write_text("fix: x\n\nbody\n")
    reason = A.check_commit_message(msg)
    assert reason and CARD in reason and "public_voice" in reason


def test_no_check_outside_an_agent_session(agent, tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDECODE")
    msg = tmp_path / "m"
    msg.write_text("fix: a person's own commit\n")
    assert A.check_commit_message(msg) is None


def test_no_check_when_attribution_is_off(agent, tmp_path):
    _set(agent, opsec={"public_attribution": False})
    msg = tmp_path / "m"
    msg.write_text("fix: x\n")
    assert A.check_commit_message(msg) is None


# ------------------------------------------------------------- pre-push

@pytest.mark.parametrize("branch", ["main", "master"])
def test_push_to_default_branch_is_refused(agent, branch):
    reason = A.check_push("origin", [f"refs/heads/x abc refs/heads/{branch} def"])
    assert reason and branch in reason


def test_push_of_a_feature_branch_passes(agent):
    assert A.check_push("origin", ["refs/heads/x abc refs/heads/feature/x def"]) is None


def test_push_guard_off_unless_declared(agent):
    _set(agent, opsec={"public_attribution": True})
    assert A.check_push("origin", ["refs/heads/x abc refs/heads/main def"]) is None


# ------------------------------------------------------------- gh pr

def test_pr_create_with_carded_body_file_passes(agent, tmp_path):
    body = tmp_path / "b.md"
    body.write_text(f"## What\n\nchange\n\n*{GOOD}*\n")
    assert A.check_gh_command(f"gh pr create -R o/r --title t --body-file {body}") is None


def test_pr_create_without_card_is_refused(agent, tmp_path):
    body = tmp_path / "b.md"
    body.write_text("## What\n\nchange\n")
    assert A.check_gh_command(f"gh pr create --title t --body-file {body}")


def test_relative_body_file_resolves_against_the_session_cwd(agent, tmp_path):
    (tmp_path / "b.md").write_text(f"x\n\n{GOOD}\n")
    assert A.check_gh_command("gh pr create --body-file b.md", cwd=str(tmp_path)) is None


def test_unreadable_body_is_refused_with_the_fix(agent):
    reason = A.check_gh_command("gh pr create --fill")
    assert reason and "--body-file" in reason


def test_pr_comment_inline_body(agent):
    assert A.check_gh_command(f"gh pr comment 5 --body 'thanks\n\n{GOOD}'") is None
    assert A.check_gh_command("gh pr comment 5 --body 'thanks'")


def test_title_only_edit_is_not_checked(agent):
    assert A.check_gh_command("gh pr edit 5 --title 'new title'") is None


def test_chained_commands_are_each_checked(agent, tmp_path):
    body = tmp_path / "b.md"
    body.write_text("no card\n")
    assert A.check_gh_command(f"git push -u origin x && gh pr create --body-file {body}")


def test_issues_are_never_checked(agent):
    # public_voice: the card never goes on issues.
    assert A.check_gh_command("gh issue create --title t --body 'no card'") is None


# ------------------------------------------------------------- end to end

def _git(repo, *args, env=None, input=None):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, env=env, input=input)


@pytest.mark.skipif(shutil.which("macf_tools") is None, reason="macf_tools not on PATH")
def test_real_git_through_the_dispatcher(agent, tmp_path):
    from macf.githooks import install_dispatcher
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    repo = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "T")):
        _git(repo, "config", k, v)
    _git(repo, "remote", "add", "origin", str(remote))
    install_dispatcher(repo)
    env = dict(os.environ)
    (repo / "f").write_text("x\n")
    _git(repo, "add", "f")

    refused = _git(repo, "commit", "-q", "-m", "feat: no card", env=env)
    assert refused.returncode != 0 and CARD in refused.stderr

    ok = _git(repo, "commit", "-q", "-m", f"feat: carded\n\n{GOOD}", env=env)
    assert ok.returncode == 0, ok.stderr

    push_main = _git(repo, "push", "-q", "origin", "main", env=env)
    assert push_main.returncode != 0 and "default branch" in push_main.stderr

    push_branch = _git(repo, "push", "-q", "origin", "main:feature/x", env=env)
    assert push_branch.returncode == 0, push_branch.stderr

    person = {k: v for k, v in env.items() if k != "CLAUDECODE"}
    assert _git(repo, "push", "-q", "origin", "main", env=person).returncode == 0


# ------------------------------------------------------------- PreToolUse wiring

def _pretool(command, cwd):
    from macf.hooks.handle_pre_tool_use import run
    return run(json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                           "cwd": cwd, "session_id": "s-attr"}))


def test_pretooluse_denies_an_uncarded_pr_and_passes_a_carded_one(agent, tmp_path):
    (tmp_path / "bad.md").write_text("no card\n")
    (tmp_path / "good.md").write_text(f"body\n\n*{GOOD}*\n")
    denied = _pretool("gh pr create --title t --body-file bad.md", str(tmp_path))
    out = denied.get("hookSpecificOutput", {})
    assert out.get("permissionDecision") == "deny" and CARD in out.get("permissionDecisionReason", "")
    allowed = _pretool("gh pr create --title t --body-file good.md", str(tmp_path))
    assert allowed.get("hookSpecificOutput", {}).get("permissionDecision") != "deny"
