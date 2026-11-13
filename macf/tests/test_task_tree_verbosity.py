"""`task tree` verbosity: notes counted by default, listed at -v, in full at -vv.

The default tree printed a line for every note on every task, so a long-lived
task pushed its siblings off the screen. The levels:

- default: each task's notes are a count on its own line, not separate lines;
- `-v` / `--verbose`: what the default used to show (truncated notes and plans);
- `-vv` / `--verbose 2`: the full text of every note (and plans, breadcrumbs,
  lifecycle updates), wrapped to 80% of the terminal's width.
"""

import os
import re
import subprocess
import sys

import pytest

SRC = os.pathsep.join(p for p in sys.path if p)
LONG = ("The second note is long on purpose: " + " ".join(f"word{i}" for i in range(60))
        + " and it ends here with ENDMARK.")


@pytest.fixture
def env(tmp_path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    e = dict(os.environ)
    e.update({"MACF_TASK_STORE_DIR": str(tasks), "MACF_EVENTS_LOG_PATH": str(tmp_path / "ev.jsonl"),
              "MACEFF_AGENT_HOME_DIR": str(tmp_path), "PYTHONPATH": SRC, "COLUMNS": "100"})
    return e


def run(env, *args):
    r = subprocess.run([sys.executable, "-m", "macf.cli", *args], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    return re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)


@pytest.fixture
def tid(env):
    t = run(env, "task", "create", "task", "--plan", "p", "Noted task").split("Created task #")[1].split()[0]
    run(env, "task", "note", t, "first note SHORTMARK")
    run(env, "task", "note", t, LONG)
    return t


def tree(env, *flags):
    return run(env, "task", "tree", "--roles", "none", *flags)


def test_default_counts_notes_on_the_task_line(env, tid):
    out = tree(env)
    line = next(l for l in out.splitlines() if re.search(rf"#{tid}(?!\d)", l))
    assert "📝 2" in line
    assert "SHORTMARK" not in out and "word1" not in out


@pytest.mark.parametrize("flags", [("-v",), ("--verbose",)])
def test_one_v_is_the_old_default(env, tid, flags):
    out = tree(env, *flags)
    assert "SHORTMARK" in out
    assert "ENDMARK" not in out          # the long note is truncated at this level
    assert "🔖" not in out               # breadcrumbs belong to the next level


@pytest.mark.parametrize("flags", [("-vv",), ("--verbose", "2")])
def test_two_v_shows_every_note_whole_and_wrapped(env, tid, flags):
    out = tree(env, *flags)
    assert "SHORTMARK" in out and "ENDMARK" in out
    assert all(f"word{i}" in out for i in range(60))
    width = int(100 * 0.8)
    note_lines = [l for l in out.splitlines() if "word" in l or "ENDMARK" in l]
    assert len(note_lines) > 1, "a long note must wrap onto several lines"
    assert all(len(l) <= width for l in note_lines), max(note_lines, key=len)


def test_verbose_followed_by_a_task_id_still_reads_it_as_the_root(env, tid):
    """Review of PR 1006 (THM): `task tree --verbose 892` worked on main; keep it working.

    Ids 1 and 2 are also levels, so they read as levels; the root needs an id above 2.
    """
    for title in ("filler a", "filler b"):
        run(env, "task", "create", "task", "--plan", "p", title)
    root = run(env, "task", "create", "task", "--plan", "p", "--parent", tid, "Child root")
    root = root.split("Created task #")[1].split()[0]
    run(env, "task", "note", root, "child note CHILDMARK")
    assert int(root) > 2
    out = tree(env, "--verbose", root)
    assert "Task Tree from #" + root in out
    assert "CHILDMARK" in out and "SHORTMARK" not in out   # level 1, rooted at the child


def test_verbose_level_out_of_range_is_refused(env, tid):
    r = subprocess.run([sys.executable, "-m", "macf.cli", "task", "tree", tid, "--verbose", "3"],
                       capture_output=True, text=True, env=env)
    assert r.returncode != 0 and "1 or 2" in (r.stdout + r.stderr)
