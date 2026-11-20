"""MIS-0009 R01-R04: backends are subcommands; the backend attaches only; the launcher refuses the default profile."""
import argparse
from pathlib import Path

import pytest

from macf.browser import cli as bcli, guard


def _parser():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    bcli.add_browser_parser(sub)
    return p


def test_backends_are_subcommands():
    p = _parser()
    args = p.parse_args(["browser", "cdp", "tabs", "--host", "mail.example.com"])
    assert args.browser_backend == "cdp" and args.cdp_cmd == "tabs"
    args = p.parse_args(["browser", "cdp", "outlook", "list", "from:someone"])
    assert args.cdp_cmd == "outlook"


def test_missing_extra_names_install(monkeypatch, capsys):
    from macf.browser import events
    monkeypatch.setattr(events, "_append", lambda name, data: True)
    def no_playwright():
        raise guard.Unavailable("Playwright is not installed: pip install 'macf[browser]'")
    monkeypatch.setattr(bcli, "_backend", lambda args, plugin=None: no_playwright())
    p = _parser()
    args = p.parse_args(["browser", "cdp", "tabs", "--host", "mail.example.com"])
    assert args.func(args) != 0
    assert "pip install 'macf[browser]'" in capsys.readouterr().err
