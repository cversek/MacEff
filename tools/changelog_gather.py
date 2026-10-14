#!/usr/bin/env python3
"""Gather ``changelog.d/`` fragments into CHANGELOG.md (policy ``release_workflow`` §3.5).

Every pull request adds its CHANGELOG entry as a fragment of its own, a new file in
``changelog.d/``, instead of editing CHANGELOG.md. No two pull requests then touch the same
file, so merging one never puts the others into conflict, which per-PR edits at the top of
the same list did. At release, this gathers them:

    python tools/changelog_gather.py            # print what would change, change nothing
    python tools/changelog_gather.py --write    # file the entries, remove the fragments

A fragment is markdown: one or more category headings (``### Added``, ``### Changed``,
``### Deprecated``, ``### Removed``, ``### Fixed``, ``### Security``), each followed by its
bullets. Each bullet is filed under that category of the ``## [Unreleased]`` section,
ahead of the entries already there, newest first as that list reads: the newest is the
fragment whose adding commit is latest, by git, so every checkout gathers the same order. A
fragment that names no known category, holds text outside a category, or a line that is
neither an entry (``- ``) nor an indented continuation is refused by name, as is a file in
``changelog.d/`` that isn't ``.md``, and nothing is written.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

CATEGORIES = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]
ROOT = Path(__file__).resolve().parent.parent
_HEADING = re.compile(r"^###\s+(\w+)\s*$")


class FragmentError(ValueError):
    pass


def read_fragment(path: Path) -> Dict[str, List[str]]:
    """``{category: [bullet text, ...]}`` from one fragment; a bullet keeps its own lines."""
    out: Dict[str, List[str]] = {}
    current = None
    for n, line in enumerate(path.read_text().splitlines(), 1):
        m = _HEADING.match(line)
        if m:
            if m.group(1) not in CATEGORIES:
                raise FragmentError(f"{path.name}:{n}: unknown category {m.group(1)!r}; "
                                    f"known: {', '.join(CATEGORIES)}")
            current = out.setdefault(m.group(1), [])
            continue
        if not line.strip():
            continue
        if current is None:
            raise FragmentError(f"{path.name}:{n}: text before any category heading")
        if line.startswith("- "):
            current.append(line)
        elif current and line[:1] in (" ", "\t"):
            current[-1] += "\n" + line                     # a bullet's indented continuation
        else:
            raise FragmentError(f"{path.name}:{n}: an entry starts with '- ', and its further lines "
                                f"are indented")
    if not any(out.values()):
        raise FragmentError(f"{path.name}: no entries")
    return out


def _added_at(path: Path) -> float:
    """When the commit that added *path* was made, from git; a fragment git doesn't know
    yet counts as the newest. A file's mtime can't serve: git doesn't keep it, so a fresh
    clone or a checkout would decide the order (CTB, on #675)."""
    try:
        out = subprocess.run(["git", "-C", str(path.parent), "log", "--diff-filter=A",
                              "--format=%ct", "-1", "--", path.name],
                             capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else float("inf")
    except (OSError, ValueError, subprocess.SubprocessError):
        return float("inf")


def fragments(directory: Path) -> List[Path]:
    """The fragments, newest first by the commit that added each, as the ``[Unreleased]``
    list reads; the README left out. Any other file in the directory is refused, so a
    fragment saved as ``.txt`` isn't skipped in silence."""
    stray = [p.name for p in directory.iterdir()
             if p.is_file() and p.suffix != ".md" and not p.name.startswith(".")]
    if stray:
        raise FragmentError(f"not a fragment (fragments end in .md): {', '.join(sorted(stray))}")
    files = [p for p in directory.glob("*.md") if p.name.lower() != "readme.md"]
    return sorted(files, key=lambda p: (-_added_at(p), p.name))


def gather(changelog: str, entries: List[Tuple[str, str]]) -> str:
    """*changelog* with each ``(category, bullet)`` filed under ``## [Unreleased]``."""
    lines = changelog.split("\n")
    try:
        top = next(i for i, l in enumerate(lines) if l.strip().lower().startswith("## [unreleased]"))
    except StopIteration:
        raise FragmentError("CHANGELOG.md has no '## [Unreleased]' section") from None
    end = next((i for i in range(top + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    for category in reversed(CATEGORIES):
        bullets = [b for c, b in entries if c == category]
        if not bullets:
            continue
        section = lines[top:end]
        at = next((i for i, l in enumerate(section) if l.strip() == f"### {category}"), None)
        if at is None:
            # A new category heading keeps the standard order: before the first heading of a
            # later category, else at the section's end.
            later = set(CATEGORIES[CATEGORIES.index(category) + 1:])
            first = next((i for i, l in enumerate(section)
                          if l.startswith("### ") and l[4:].strip() in later), len(section))
            insert = [f"### {category}", ""] + bullets + [""]
            pos = top + first
        else:
            pos = top + at + 1
            while pos < end and not lines[pos].strip():
                pos += 1
            insert = bullets
        lines[pos:pos] = "\n".join(insert).split("\n")
        end += sum(b.count("\n") + 1 for b in insert)
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--write", action="store_true", help="file the entries and remove the fragments")
    p.add_argument("--root", type=Path, default=ROOT)
    a = p.parse_args(argv)
    directory, path = a.root / "changelog.d", a.root / "CHANGELOG.md"
    try:
        found = fragments(directory) if directory.is_dir() else []
    except FragmentError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if not found:
        print("no fragments to gather")
        return 0
    entries: List[Tuple[str, str]] = []
    try:
        for f in found:
            for category, bullets in read_fragment(f).items():
                entries += [(category, b) for b in bullets]
        result = gather(path.read_text(), entries)
    except FragmentError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if not a.write:
        print(f"{len(entries)} entries from {len(found)} fragments would be filed:")
        for f in found:
            print(f"  {f.name}")
        return 0
    path.write_text(result)
    for f in found:
        f.unlink()
    print(f"filed {len(entries)} entries from {len(found)} fragments; fragments removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
