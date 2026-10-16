"""CHANGELOG fragments are gathered at release (``tools/changelog_gather.py``, release_workflow §3.5)."""
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "changelog_gather", Path(__file__).resolve().parents[2] / "tools" / "changelog_gather.py")
cg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cg)

CHANGELOG = """# Changelog

## [Unreleased]

Since 0.6.0: things.

### Added

- **An older feature**: kept.

### Fixed

- **An older fix**: kept.

## [0.6.0] - 2026-09-01

### Fixed

- **Released**: untouched.
"""

T0 = 1_790_000_000


def _git(root, *args, when=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test"}
    if when is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"@{when} +0000"
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
                   check=True, capture_output=True, env=env)


def _repo(tmp_path, fragments, commit=True):
    """A repository whose fragments merged in the order given, one commit apart."""
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG)
    d = tmp_path / "changelog.d"
    d.mkdir()
    (d / "README.md").write_text("# not a fragment\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "--no-verify", "-m", "base", when=T0)
    for n, (name, text) in enumerate(fragments, 1):
        (d / name).write_text(text)
        if commit:
            _git(tmp_path, "add", ".")
            _git(tmp_path, "commit", "-q", "--no-verify", "-m", name, when=T0 + 100 * n)
    return tmp_path


def _unreleased(root):
    return (root / "CHANGELOG.md").read_text().split("## [0.6.0]")[0]


def test_fragments_are_filed_newest_first_under_their_categories_and_removed(tmp_path):
    root = _repo(tmp_path, [
        ("a.md", "### Fixed\n\n- **Merged first**: from a.\n"),
        ("b.md", "### Added\n\n- **New thing**: from b,\n  over two lines.\n\n### Fixed\n\n- **Merged second**: from b.\n"),
    ])
    assert cg.main(["--root", str(root), "--write"]) == 0
    text = (root / "CHANGELOG.md").read_text()
    unreleased, released = text.split("## [0.6.0]")
    assert unreleased.index("**New thing**") < unreleased.index("**An older feature**")
    assert "from b,\n  over two lines." in unreleased
    # newest first, as the [Unreleased] list on main reads (CTB, on #675)
    assert unreleased.index("**Merged second**") < unreleased.index("**Merged first**") < unreleased.index("**An older fix**")
    assert "**Released**: untouched." in released and "Merged first" not in released
    assert sorted(p.name for p in (root / "changelog.d").iterdir()) == ["README.md"]


def test_the_order_comes_from_git_not_from_the_checkout(tmp_path):
    """CTB's probe on #675: git keeps no mtimes, so a fresh clone or a touch reordered the
    gather. The commit that added each fragment decides, so every checkout agrees."""
    root = _repo(tmp_path, [("zeta.md", "### Fixed\n\n- **Zeta merged first**.\n"),
                            ("alpha.md", "### Fixed\n\n- **Alpha merged second**.\n")])
    order = [p.name for p in cg.fragments(root / "changelog.d")]
    future = T0 + 10_000
    os.utime(root / "changelog.d" / "zeta.md", (future, future))   # a checkout's new mtimes
    assert [p.name for p in cg.fragments(root / "changelog.d")] == order == ["alpha.md", "zeta.md"]


def test_a_fragment_not_yet_committed_counts_as_the_newest(tmp_path):
    root = _repo(tmp_path, [("old.md", "### Fixed\n\n- **Committed**.\n")])
    (root / "changelog.d" / "new.md").write_text("### Fixed\n\n- **Not committed yet**.\n")
    assert [p.name for p in cg.fragments(root / "changelog.d")] == ["new.md", "old.md"]


def test_a_category_new_to_the_section_keeps_the_standard_order(tmp_path):
    root = _repo(tmp_path, [("c.md", "### Changed\n\n- **A change**: from c.\n")])
    cg.main(["--root", str(root), "--write"])
    unreleased = _unreleased(root)
    assert unreleased.index("### Added") < unreleased.index("### Changed") < unreleased.index("### Fixed")


def test_without_write_nothing_changes(tmp_path):
    root = _repo(tmp_path, [("a.md", "### Fixed\n\n- **A fix**.\n")])
    assert cg.main(["--root", str(root)]) == 0
    assert (root / "CHANGELOG.md").read_text() == CHANGELOG
    assert (root / "changelog.d" / "a.md").exists()


@pytest.mark.parametrize("text, said", [
    ("### Fixd\n\n- **Typo**.\n", "unknown category"),
    ("- **No heading**.\n", "before any category"),
    ("### Fixed\n\n", "no entries"),
    ("### Fixed\n\n- **One**.\n* **Two, starred**.\n", "starts with '- '"),   # CTB, on #675
])
def test_a_malformed_fragment_is_refused_and_nothing_is_written(tmp_path, capsys, text, said):
    root = _repo(tmp_path, [("good.md", "### Fixed\n\n- **Fine**.\n"), ("bad.md", text)])
    assert cg.main(["--root", str(root), "--write"]) == 1
    assert said in capsys.readouterr().err
    assert (root / "CHANGELOG.md").read_text() == CHANGELOG
    assert (root / "changelog.d" / "good.md").exists()


def test_a_fragment_saved_with_another_extension_is_refused(tmp_path, capsys):
    """CTB, on #675: a .txt fragment was skipped in silence, by the gather and the test."""
    root = _repo(tmp_path, [("good.md", "### Fixed\n\n- **Fine**.\n"), ("fix.txt", "### Fixed\n\n- **Lost**.\n")])
    assert cg.main(["--root", str(root), "--write"]) == 1
    assert "fix.txt" in capsys.readouterr().err
    assert (root / "CHANGELOG.md").read_text() == CHANGELOG


def test_the_repository_fragments_are_well_formed():
    """Every fragment checked in gathers cleanly, so a malformed one, or a stray file,
    fails here, in its own pull request, not at release."""
    root = Path(__file__).resolve().parents[2]
    for f in cg.fragments(root / "changelog.d"):
        cg.read_fragment(f)
