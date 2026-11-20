"""The legacy pre-commit hook's silent-exception check stands aside while a merge is concluded (#1023).

A commit that concludes a merge stages every file the other side changed, and the whole-file check
reads each one, so it refused a merge of main over handlers that were already on main. The merge's own
changes are judged by the versioned style gate, so the legacy check skips while MERGE_HEAD exists and
still judges every ordinary commit.

The sample handler is a list of quoted lines, because the check reads files line by line and would
otherwise find its own sample in this file.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HANDLER = ["def f():", "    try:", "        return 1", "    except Exception:", "        return 2"]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True)


def hook(repo):
    return subprocess.run(["bash", str(repo / "macf" / "scripts" / "pre-commit-hook.sh")],
                          cwd=repo, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    scripts = tmp_path / "macf" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("pre-commit-hook.sh", "check_silent_exceptions.py"):
        shutil.copy(SCRIPTS / name, scripts / name)
    (tmp_path / "base.txt").write_text("base\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_a_merge_of_main_over_a_handler_already_on_main_is_not_refused(repo):
    git(repo, "checkout", "-q", "-b", "side")
    (repo / "side.txt").write_text("side\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "side")
    git(repo, "checkout", "-q", "main")
    (repo / "handler.py").write_text("\n".join(HANDLER) + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "a handler on main")
    git(repo, "checkout", "-q", "side")
    git(repo, "merge", "-q", "--no-commit", "--no-ff", "main")
    done = hook(repo)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "concluding a merge" in done.stderr


def test_an_ordinary_commit_of_the_same_handler_is_still_refused(repo):
    (repo / "handler.py").write_text("\n".join(HANDLER) + "\n")
    git(repo, "add", "-A")
    done = hook(repo)
    assert done.returncode == 1
    assert "silent exception" in done.stdout
