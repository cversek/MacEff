"""The statusline's reading of Claude Code's stdin: non-JSON is quiet, a real fault is recorded (#999).

The statusline runs on every refresh and its stderr must stay clean. Non-JSON stdin is normal when it
is run by hand, so that case is a quiet drop. Anything else that goes wrong reading stdin used to be
swallowed with it; it now goes to the event log, where it can be found, and still not to stderr.
"""
import argparse
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from macf import cli


class _Stdin:
    def __init__(self, text=None, error=None):
        self._text, self._error = text, error

    def isatty(self):
        return False

    def read(self):
        if self._error:
            raise self._error
        return self._text


@pytest.fixture
def run(monkeypatch, capsys):
    """Run cmd_statusline against a stdin; returns its rc, stdout, stderr, the cc_json it was given, and the events."""
    def go(stdin):
        seen, events = {}, []
        monkeypatch.setattr(sys, "stdin", stdin)
        monkeypatch.setattr(cli, "append_event", lambda name, data=None, **kw: events.append((name, data)))

        def data(cc_json=None):
            seen["cc_json"] = cc_json
            return {"agent_name": "a", "project": None, "environment": "e", "tokens_used": 1,
                    "tokens_total": 2, "cl": 99, "modes": ""}
        with patch("macf.utils.statusline.get_statusline_data", side_effect=data), \
             patch("macf.utils.statusline.format_statusline", return_value="LINE"):
            rc = cli.cmd_statusline(argparse.Namespace())
        out = capsys.readouterr()
        return SimpleNamespace(rc=rc, out=out.out, err=out.err, cc_json=seen.get("cc_json"), events=events)
    return go


def test_non_json_stdin_is_a_quiet_drop_and_macf_data_is_used(run):
    r = run(_Stdin("not json at all"))
    assert (r.rc, r.out.strip(), r.err, r.cc_json, r.events) == (0, "LINE", "", None, [])


def test_json_stdin_is_passed_through(run):
    r = run(_Stdin(json.dumps({"model": {"id": "x"}})))
    assert (r.rc, r.err, r.cc_json, r.events) == (0, "", {"model": {"id": "x"}}, [])


def test_a_fault_reading_stdin_goes_to_the_event_log_not_to_stderr(run):
    r = run(_Stdin(error=OSError("the pipe broke")))
    assert r.rc == 0 and r.out.strip() == "LINE" and r.err == ""
    assert [e[0] for e in r.events] == ["statusline_stdin_fault"]
    assert "the pipe broke" in r.events[0][1]["error"]
