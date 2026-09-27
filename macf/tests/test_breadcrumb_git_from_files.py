"""The breadcrumb's git hash and the project root, found without running git.

Every breadcrumb ran `git rev-parse` for HEAD, and outside Claude Code a second
one for the project root: two processes per command line, about 16 ms. Both
answers are now read from the repository's files, the way git finds them, and
git is asked whenever the files do not say it plainly or the environment
redirects git. Each test holds the file read to git's own answer on a real
repository of one shape.
"""
import subprocess
from pathlib import Path

import pytest

from macf.utils import paths
from macf.utils.breadcrumbs import _head_from_files, extract_current_git_hash
from macf.utils.paths import find_git_worktree, find_project_root


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture(autouse=True)
def plain_git_env(monkeypatch):
    for var in paths._GIT_LOCATION_ENV + ("CLAUDE_PROJECT_DIR",):
        monkeypatch.delenv(var, raising=False)
    find_project_root.cache_clear()
    yield
    find_project_root.cache_clear()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "CLAUDE.md").write_text("marker\n")
    git(root, "add", "CLAUDE.md")
    git(root, "commit", "-q", "-m", "one")
    (root / "src" / "deep").mkdir(parents=True)
    return root


@pytest.mark.parametrize("shape", ["loose", "packed", "detached", "worktree"])
def test_the_file_read_agrees_with_git(repo, tmp_path, shape):
    where = repo
    if shape == "packed":
        git(repo, "pack-refs", "--all")
        assert not (repo / ".git" / "refs" / "heads" / "main").exists(), "the ref must be packed"
    elif shape == "detached":
        git(repo, "checkout", "-q", "--detach")
    elif shape == "worktree":
        where = tmp_path / "linked"
        git(repo, "worktree", "add", "-q", "-b", "side", str(where))
        (where / "x").write_text("x\n")
        git(where, "add", "x")
        git(where, "commit", "-q", "-m", "on side")
        assert (where / ".git").is_file(), "a linked worktree has a .git file"
    top = find_git_worktree(where / "src" / "deep" if shape != "worktree" else where)
    assert top == where.resolve()
    assert _head_from_files(top)[:7] == git(where, "rev-parse", "--short=7", "HEAD")


def test_an_unborn_branch_has_no_hash_by_either_path(tmp_path):
    git(tmp_path, "init", "-q")
    assert _head_from_files(tmp_path) is None
    assert subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=tmp_path,
                          capture_output=True).returncode != 0


def test_a_redirected_git_is_asked_rather_than_read(repo, tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q")
    (other / "f").write_text("f\n")
    git(other, "add", "f")
    git(other, "commit", "-q", "-m", "other")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    assert extract_current_git_hash() == git(other, "rev-parse", "--short=7", "HEAD")
    assert extract_current_git_hash() != _head_from_files(repo)[:7]


def test_the_project_root_is_the_marked_repository_above_the_working_directory(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(paths.subprocess, "run", None)  # no git process may run
    monkeypatch.chdir(repo / "src" / "deep")
    assert find_project_root() == repo.resolve()
    find_project_root.cache_clear()
    (repo / "CLAUDE.md").unlink()
    assert find_project_root() == (repo / "src" / "deep").resolve()


def test_a_failed_file_read_says_so_and_asks_git(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)

    def unreadable(start):
        raise PermissionError(13, "Permission denied", str(start))

    monkeypatch.setattr("macf.utils.breadcrumbs.find_git_worktree", unreadable)
    assert extract_current_git_hash() == git(repo, "rev-parse", "--short=7", "HEAD")
    assert "asking git" in capsys.readouterr().err
