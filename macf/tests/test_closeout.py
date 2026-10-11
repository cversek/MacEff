"""A task's GitHub close-out: posted as the agent, through the publishing checks, when it says something (#582)."""
import json
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from macf import closeout


def _done(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class Recorder:
    """A stand-in for subprocess.run that answers by the command and records every call."""

    def __init__(self, answers=None):
        self.calls, self.answers = [], answers or {}

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        for key, answer in self.answers.items():
            if key in " ".join(argv):
                return answer
        return _done()

    def commented(self):
        return [(a, k) for a, k in self.calls if a[:1] == ["gh"] and "comment" in a]


@pytest.mark.parametrize("choice, is_open, closed_by, me, post", [
    (None, True, None, "maceff-ira[bot]", True),                     # open: say it's done
    (None, False, "maceff-ira[bot]", "maceff-ira[bot]", True),       # this agent merged it
    (None, False, "claude-the-builder", "maceff-ira[bot]", False),   # someone else did
    (None, False, None, "maceff-ira[bot]", False),                   # closed, closer unknown
    (None, None, None, None, True),                                  # state unreadable
    (True, False, "claude-the-builder", "maceff-ira[bot]", True),    # --closeout
    (False, True, None, "maceff-ira[bot]", False),                   # --no-closeout
])
def test_when_a_closeout_is_posted(choice, is_open, closed_by, me, post):
    assert closeout.should_post(choice, is_open, closed_by, me)[0] is post


def test_a_gh_token_in_the_settings_is_the_agents_identity(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "from-settings")
    run = Recorder()
    env, how = closeout.agent_env("o/r", run)
    assert env["GH_TOKEN"] == "from-settings" and "GH_TOKEN" in how and run.calls == []


@pytest.mark.parametrize("rc, out, token, said", [
    (0, "minted\n", "minted", "GitHub App"),
    (3, "", None, "not installed on o/r"),
    (2, "", None, "no GitHub App of the agent's own"),
])
def test_the_agents_app_answers_for_it(monkeypatch, tmp_path, rc, out, token, said):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    tool = tmp_path / "ghapp.py"
    tool.write_text("")
    monkeypatch.setattr(closeout, "_ghapp_tool", lambda: tool)
    run = Recorder({"token --repo o/r": _done(rc, out)})
    env, how = closeout.agent_env("o/r", run)
    assert (env or {}).get("GH_TOKEN") == token and said in how


def test_the_app_login_comes_from_its_facts(monkeypatch, tmp_path):
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    monkeypatch.delenv("GHAPP_NAME", raising=False)
    root = tmp_path / ".maceff" / "ghapp"
    (root / "ira").mkdir(parents=True)
    (root / "ira" / "app.json").write_text(json.dumps({"slug": "maceff-ira"}))
    assert closeout.agent_login() == "maceff-ira[bot]"
    (root / "other").mkdir()
    (root / "other" / "app.json").write_text(json.dumps({"slug": "someone"}))
    assert closeout.agent_login() is None            # two apps and no name: no answer
    monkeypatch.setenv("GHAPP_NAME", "ira")
    assert closeout.agent_login() == "maceff-ira[bot]"


def test_without_an_identity_of_its_own_nothing_is_posted(monkeypatch, capsys):
    """The operator's account is never used in the agent's place: the close-out is printed."""
    monkeypatch.setattr(closeout, "check_body", lambda body, signed, run=None: None)
    monkeypatch.setattr(closeout, "agent_env", lambda repo, run=None: (None, "no GH_TOKEN, and no GitHub App"))
    run = Recorder()
    env = closeout.post("pr", 7, "o/r", "## Review Close-out\n\nDone.", choice=None, is_open=True,
                        closed_by=None, signed=False, run=run)
    out = capsys.readouterr().out
    assert env is None and run.commented() == []
    assert "Close-out not posted" in out and "Done." in out and "gh pr comment 7 --repo o/r --body-file" in out


def test_a_check_finding_stops_the_post(monkeypatch, capsys):
    monkeypatch.setattr(closeout, "check_body", lambda body, signed, run=None: "20-no-private-refs: task #12")
    monkeypatch.setattr(closeout, "agent_env", lambda repo, run=None: ({"GH_TOKEN": "t"}, "the agent's GH_TOKEN"))
    run = Recorder()
    assert closeout.post("issue", 3, "o/r", "body", choice=None, is_open=True, closed_by=None,
                         signed=False, run=run) is None
    assert run.commented() == [] and "task #12" in capsys.readouterr().out


def test_a_post_goes_out_under_the_agents_token(monkeypatch):
    monkeypatch.setattr(closeout, "check_body", lambda body, signed, run=None: None)
    monkeypatch.setattr(closeout, "agent_env", lambda repo, run=None: ({"GH_TOKEN": "app-token"}, "the agent's GitHub App"))
    run = Recorder()
    env = closeout.post("pr", 7, "o/r", "body", choice=None, is_open=True, closed_by=None, signed=False, run=run)
    (argv, kwargs), = run.commented()
    assert argv[:4] == ["gh", "pr", "comment", "7"] and kwargs["env"]["GH_TOKEN"] == "app-token"
    assert env["GH_TOKEN"] == "app-token"


@pytest.mark.skipif(not shutil.which("bash"), reason="the hooklets are bash")
def test_the_real_hooklets_pass_the_cli_footer_and_refuse_a_private_reference():
    """The italic card footer the CLI writes passes the gate; a task number in the report does not."""
    if closeout._maceff_tree() is None:
        pytest.skip("not inside a MacEff source tree")
    card = "*[IraMacEff@ee9a78: task#323 s_89f47c46/c_61/p_d9244919/t_1791685324]*"
    clean = f"## Review Close-out\n\nMerged after both reviews.\n\n**Outcome:** MERGED\n\n---\n{card}\n"
    assert closeout.check_body(clean, signed=False) is None
    leaky = clean.replace("Merged after both reviews.", "Merged; see task #12 for the rest.")
    finding = closeout.check_body(leaky, signed=False)
    assert finding and finding.startswith("20-no-private-refs")


def test_a_pr_someone_else_merged_gets_no_closeout_unless_asked(monkeypatch):
    from macf.cli import _gh_pr_closeout
    from macf.task.models import MacfTaskMetaData
    mtmd = MacfTaskMetaData(task_type='GH_PR', custom={
        'gh_owner': 'o', 'gh_repo': 'r', 'gh_pr_number': 9, 'linked_issues': []})
    view = _done(stdout=json.dumps({"state": "MERGED", "mergeCommit": {"oid": "abc123"},
                                    "mergedBy": {"login": "claude-the-builder"}}))
    monkeypatch.setattr(closeout, "agent_login", lambda: "maceff-ira[bot]")
    monkeypatch.setattr(closeout, "check_body", lambda body, signed, run=None: None)
    monkeypatch.setattr(closeout, "agent_env", lambda repo, run=None: ({"GH_TOKEN": "t"}, "the agent's GitHub App"))
    for choice, posts in ((None, False), (True, True)):
        args = SimpleNamespace(report="Reviewed.", verified=None, cascade=False, closeout=choice)
        with patch('macf.cli._public_attribution_enabled', return_value=False):
            with patch('subprocess.run', side_effect=[view, _done()]) as mock_run:
                assert _gh_pr_closeout(9, mtmd, args, 's/c/g/p/t') == 'MERGED'
        commented = [c for c in mock_run.call_args_list if c[0][0][:3] == ['gh', 'pr', 'comment']]
        assert bool(commented) is posts


def test_the_issue_is_closed_under_the_agents_identity_too(monkeypatch):
    from macf import cli
    from macf.task.models import MacfTaskMetaData
    mtmd = MacfTaskMetaData(task_type='GH_ISSUE', custom={
        'gh_owner': 'o', 'gh_repo': 'r', 'gh_issue_number': 42})
    args = SimpleNamespace(report="Fixed.", commit=["abc1234567890"], verified="tests", closeout=None)
    monkeypatch.setattr(closeout, "item_state", lambda repo, n, run=None: (True, None))
    monkeypatch.setattr(closeout, "check_body", lambda body, signed, run=None: None)
    monkeypatch.setattr(closeout, "agent_env", lambda repo, run=None: ({"GH_TOKEN": "app-token"}, "the agent's GitHub App"))
    monkeypatch.setattr(cli, "_commit_landed_in_merged_pr", lambda repo, commits: True)
    with patch('macf.cli._public_attribution_enabled', return_value=False):
        with patch('subprocess.run', return_value=_done()) as mock_run:
            cli._gh_issue_closeout(42, mtmd, args, 's/c/g/p/t')
    closes = [c for c in mock_run.call_args_list if c[0][0][:3] == ['gh', 'issue', 'close']]
    assert len(closes) == 1 and closes[0][1]["env"]["GH_TOKEN"] == "app-token"
