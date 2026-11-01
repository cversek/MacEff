"""A sprint or play-time close finds its log wherever the CLI runs.

``task create`` stores plan_ca_ref relative to the agent home. The close used to read it against
the working directory, so a CLI run from a project directory skipped the log without a word.
"""
import pytest

from macf import cli
import macf.utils.paths as paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    agent_home = tmp_path / "agent_home"
    for kind, log in (("sprints", "sprint_log.md"), ("play_time", "play_log.md")):
        folder = agent_home / "agent" / "public" / kind / "2026-10-30_run"
        folder.mkdir(parents=True)
        (folder / log).write_text("# log\n")
    elsewhere = tmp_path / "project"
    elsewhere.mkdir()
    monkeypatch.setattr(paths, "find_agent_home", lambda: agent_home)
    monkeypatch.chdir(elsewhere)  # the harness's project dir, with no agent/ folder
    return agent_home


@pytest.mark.parametrize("find,kind,log", [(cli._find_sprint_log, "sprints", "sprint_log.md"),
                                           (cli._find_play_log, "play_time", "play_log.md")])
def test_a_relative_plan_ref_resolves_against_the_agent_home(home, find, kind, log):
    ref = f"agent/public/{kind}/2026-10-30_run/{log}"
    assert find(ref) == home / ref
    assert find(f"agent/public/{kind}/2026-10-30_run") == home / ref  # a folder ref too


def test_an_absolute_plan_ref_still_works_and_a_missing_log_is_none(home):
    ref = home / "agent/public/sprints/2026-10-30_run/sprint_log.md"
    assert cli._find_sprint_log(str(ref)) == ref
    assert cli._find_sprint_log("agent/public/sprints/nowhere/sprint_log.md") is None
