"""A command group run without a subcommand shows its help.

Running a group bare is how someone finds out what it offers, and the
framework tells agents to discover commands from the CLI. Only leaf commands
set a function, so a bare group used to reach main() with nothing to call and
raise AttributeError.
"""
import argparse

import pytest

from macf.cli import _build_parser, main


def _groups(parser, path=()):
    """Every command group in the tree, as the argv that names it."""
    sub = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
    if sub is None:
        return
    for name, child in sub.choices.items():
        child_sub = next((a for a in child._actions if isinstance(a, argparse._SubParsersAction)), None)
        if child_sub is not None and child.get_default("func") is None:
            yield path + (name,)
            yield from _groups(child, path + (name,))


GROUPS = list(_groups(_build_parser()))


def test_the_walk_finds_the_groups():
    """A walk that found nothing would make the test below vacuous."""
    assert ("knowledge",) in GROUPS and ("task", "scope") in GROUPS and len(GROUPS) > 10


@pytest.mark.parametrize("argv", GROUPS, ids=" ".join)
def test_every_bare_group_prints_its_own_help(argv, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(list(argv))
    assert exit_info.value.code == 2
    out = capsys.readouterr().out
    assert out.startswith(f"usage: macf_tools {' '.join(argv)}")
