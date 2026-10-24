"""A primal daemon older than its CLI says so (MacEff #816): the status names each side's build,
and a verb the daemon doesn't know reads as that, not as its parser's message."""
import argparse
import json

import pytest

from macf.pd import build, cli, client
from macf.pd.interface import Response, parse_request
from test_primal_daemon import ask, base, make_home, run_daemon  # noqa: F401 - fixtures


def _parser_refusal(op="entry_list"):
    """The refusal an older daemon really sends: its own parser's message for an unknown op."""
    with pytest.raises(Exception) as e:
        parse_request(json.dumps({"op": op}).replace(op, "no_such_verb_yet"))
    return str(e.value)


def test_a_verb_the_daemon_does_not_know_reads_as_a_daemon_older_than_its_cli(tmp_path, base, run_daemon):
    """Through the real client and a real daemon, whose parser refuses an op it doesn't know with
    the same message an older daemon sends for a newer verb."""
    assert build.unknown_verb(_parser_refusal()) == "no_such_verb_yet"
    assert build.unknown_verb("no entry e-0123456789ab is held") is None
    daemon = run_daemon(make_home(tmp_path, []), base)
    reply = client.ask(daemon.card, {"op": "no_such_verb_yet"}, base=base)
    assert not reply.ok
    assert reply.error.startswith("this daemon is older than this command: it doesn't know the request 'no_such_verb_yet'")
    assert "pd install --force" in reply.error and "Input tag" not in reply.error


def test_a_running_daemon_reports_its_build_in_status(tmp_path, base, run_daemon):
    daemon = run_daemon(make_home(tmp_path, []), base)
    reply = ask(daemon, {"op": "status"})
    assert reply["ok"] and reply["build"].startswith("macf ")
    assert reply["build"] == build.build_id()


@pytest.mark.parametrize("daemon_build, says", [
    ("", "doesn't say which build it runs"),
    ("macf 0.6.0 at 0badc0de", "the daemon runs macf 0.6.0 at 0badc0de, and this command"),
    (None, "the same as this command"),
])
def test_pd_status_says_when_the_daemon_and_the_cli_drift(monkeypatch, capsys, daemon_build, says):
    here = build.build_id()
    report = client.StatusReport(card="Tester@abc123", source="daemon", why="its record and its socket agree",
                                 daemon_build=here if daemon_build is None else daemon_build, cli_build=here)
    monkeypatch.setattr(client, "status", lambda home, card: report)
    monkeypatch.setattr("macf.pd.daemon.card_for_home", lambda home: "Tester@abc123")
    parser = argparse.ArgumentParser()
    cli.add_pd_parser(parser.add_subparsers(dest="cmd"))
    args = parser.parse_args(["pd", "status"])
    assert args.func(args) == 0
    assert says in capsys.readouterr().out
