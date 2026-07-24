"""Round-trip tests for the OPSEC pre-commit gate.

Real git repos, real commits: a staged leak must be rejected by the
installed hook; a clean commit must pass; --no-verify must bypass.
"""
import json
import subprocess

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
    assert (repo / ".git" / "hooks" / "pre-commit").exists()
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


def test_foreign_precommit_not_overwritten(repo, profile):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 0\n")
    with pytest.raises(ValueError, match="different pre-commit hook"):
        install_hook(repo, profile)


def test_missing_profile_fails_closed(repo, profile):
    install_hook(repo, profile)
    profile.unlink()
    (repo / "code.py").write_text("clean line\n")
    _git(repo, "add", "code.py")
    r = _git(repo, "commit", "-m", "clean but no profile", check=False)
    assert r.returncode != 0
    assert "failing closed" in r.stdout + r.stderr
