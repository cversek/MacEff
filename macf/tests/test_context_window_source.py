"""The context window says where it came from, so a fallback never reads as a measurement (#1050)."""
import argparse
import json

import pytest

from macf.utils import tokens


def _resolved(monkeypatch, value, source):
    monkeypatch.setattr("macf.config.resolve_setting", lambda *a, **k: (value, source))


def test_a_set_window_reports_its_source_and_an_unset_one_says_default(monkeypatch):
    _resolved(monkeypatch, 1_000_000, "env")
    assert tokens.get_total_context_and_source() == (1_000_000, "env")
    _resolved(monkeypatch, 500_000, "config")
    assert tokens.get_total_context_and_source() == (500_000, "config")
    _resolved(monkeypatch, 200_000, "default")
    assert tokens.get_total_context_and_source() == (200_000, "default")
    assert tokens.get_total_context() == 200_000       # the plain reader still answers with the number


INFO = {"cl_level": 80, "percentage_used": 20.0, "tokens_used": 40_000, "tokens_remaining": 160_000}


def test_the_hook_readout_labels_an_assumed_window_and_leaves_a_set_one_alone(monkeypatch):
    _resolved(monkeypatch, 200_000, "default")
    assumed = tokens.format_token_context_full(INFO)
    assert "Tokens Used: 40,000 / 200,000 (assumed default: not read from your account)" in assumed
    _resolved(monkeypatch, 1_000_000, "config")
    assert "assumed default" not in tokens.format_token_context_full(INFO)


@pytest.mark.parametrize("source,labelled", [("default", True), ("env", False), ("config", False)])
def test_macf_tools_env_labels_a_default_window_in_text_and_json(monkeypatch, capsys, source, labelled):
    from macf import cli
    _resolved(monkeypatch, 200_000, source)
    for as_json in (False, True):
        args = argparse.Namespace(json=as_json, set_term_title=None, command="env")
        try:
            cli.cmd_env(args)
        except SystemExit:
            pass
        out = capsys.readouterr().out
        if as_json:
            assert json.loads(out)["versions"]["context_window_source"] == source
        else:
            assert ("assumed default, not read from your account" in out) is labelled
