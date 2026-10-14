"""CHANGELOG fragments are gathered at release (``tools/changelog_gather.py``, release_workflow §3.5)."""
import importlib.util
import os
import time
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


def _repo(tmp_path, fragments):
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG)
    d = tmp_path / "changelog.d"
    d.mkdir()
    (d / "README.md").write_text("# not a fragment\n")
    for n, (name, text) in enumerate(fragments):
        f = d / name
        f.write_text(text)
        os.utime(f, (time.time() + n, time.time() + n))    # oldest first, in the order given
    return tmp_path


def test_fragments_are_filed_under_their_categories_and_removed(tmp_path):
    root = _repo(tmp_path, [
        ("a.md", "### Fixed\n\n- **First fix**: from a.\n"),
        ("b.md", "### Added\n\n- **New thing**: from b,\n  over two lines.\n\n### Fixed\n\n- **Second fix**: from b.\n"),
    ])
    assert cg.main(["--root", str(root), "--write"]) == 0
    text = (root / "CHANGELOG.md").read_text()
    unreleased, released = text.split("## [0.6.0]")
    assert unreleased.index("**New thing**") < unreleased.index("**An older feature**")
    assert "from b,\n  over two lines." in unreleased
    assert unreleased.index("**First fix**") < unreleased.index("**Second fix**") < unreleased.index("**An older fix**")
    assert "**Released**: untouched." in released and "First fix" not in released
    assert sorted(p.name for p in (root / "changelog.d").iterdir()) == ["README.md"]


def test_a_category_new_to_the_section_keeps_the_standard_order(tmp_path):
    root = _repo(tmp_path, [("c.md", "### Changed\n\n- **A change**: from c.\n")])
    cg.main(["--root", str(root), "--write"])
    unreleased = (root / "CHANGELOG.md").read_text().split("## [0.6.0]")[0]
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
])
def test_a_malformed_fragment_is_refused_and_nothing_is_written(tmp_path, capsys, text, said):
    root = _repo(tmp_path, [("good.md", "### Fixed\n\n- **Fine**.\n"), ("bad.md", text)])
    assert cg.main(["--root", str(root), "--write"]) == 1
    assert said in capsys.readouterr().err
    assert (root / "CHANGELOG.md").read_text() == CHANGELOG
    assert (root / "changelog.d" / "good.md").exists()


def test_the_repository_fragments_are_well_formed():
    """Every fragment checked in now gathers cleanly, so a malformed one fails here, in its
    own pull request, not at release."""
    root = Path(__file__).resolve().parents[2]
    for f in cg.fragments(root / "changelog.d"):
        cg.read_fragment(f)
