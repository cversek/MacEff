"""Round-trip tests for the OPSEC pre-commit gate.

Real git repos, real commits: a staged leak must be rejected by the
installed hook; a clean commit must pass; --no-verify must bypass.
"""
import json
import subprocess
from pathlib import Path

import pytest

from macf.opsec import DEFAULT_PROFILE, install_hook


def _git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True, text=True, check=check,
    )


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "scratch_repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "test@example.com")
    _git(r, "config", "user.name", "Test User")
    return r


@pytest.fixture
def profile(tmp_path):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps(DEFAULT_PROFILE))
    return p


def test_install_reports_facts(repo, profile):
    facts = install_hook(repo, profile)
    assert facts["repo"] == str(repo)
    assert Path(facts["hooklet"]).exists()
    assert (repo / ".git" / "hooks" / "check_context_leakage.py").exists()


def test_clean_commit_passes(repo, profile):
    install_hook(repo, profile)
    (repo / "code.py").write_text("def add(a, b):\n    return a + b\n")
    _git(repo, "add", "code.py")
    r = _git(repo, "commit", "-m", "add function", check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_leaky_commit_rejected(repo, profile):
    install_hook(repo, profile)
    (repo / "code.py").write_text("# fixed in c25 after the bench session\n")
    _git(repo, "add", "code.py")
    r = _git(repo, "commit", "-m", "leaky", check=False)
    assert r.returncode != 0
    assert "COMMIT REJECTED" in r.stdout + r.stderr


def test_non_ascii_rejected(repo, profile):
    install_hook(repo, profile)
    (repo / "notes.md").write_text("a thought — with an em-dash\n")
    _git(repo, "add", "notes.md")
    r = _git(repo, "commit", "-m", "unicode", check=False)
    assert r.returncode != 0


def test_no_verify_bypasses(repo, profile):
    install_hook(repo, profile)
    (repo / "code.py").write_text("# fixed in c25 after the bench session\n")
    _git(repo, "add", "code.py")
    r = _git(repo, "commit", "--no-verify", "-m", "reviewed disclosure", check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_profile_inside_repo_refused(repo):
    inside = repo / "profile.json"
    inside.write_text(json.dumps(DEFAULT_PROFILE))
    with pytest.raises(ValueError, match="inside the target repo"):
        install_hook(repo, inside)


def test_foreign_precommit_is_adopted_not_destroyed(repo, profile):
    """This used to RAISE, which was the right posture for a lone installer and
    the wrong shape for a second one: git offers a single pre-commit file, so
    refusing meant one of the two gates the framework wants simply did not
    exist. It now takes a numbered slot and adopts whatever was there."""
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\n# a hook the developer wrote\nexit 0\n")

    facts = install_hook(repo, profile)

    adopted = repo / ".git" / "hooks.local.d" / "pre-commit.d" / "00-local-preexisting"
    assert adopted.is_file(), "the developer's hook was destroyed"
    assert "a hook the developer wrote" in adopted.read_text()
    assert facts["adopted"], "adoption happened but was not reported"


def test_missing_profile_fails_closed(repo, profile):
    install_hook(repo, profile)
    profile.unlink()
    (repo / "code.py").write_text("clean line\n")
    _git(repo, "add", "code.py")
    r = _git(repo, "commit", "-m", "clean but no profile", check=False)
    assert r.returncode != 0
    assert "failing closed" in r.stdout + r.stderr
