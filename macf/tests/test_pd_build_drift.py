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
    import pytest as _pt
    with _pt.MonkeyPatch.context() as mp:                # an op this command knows, the daemon not
        mp.setattr(build, "known_ops", lambda: frozenset({"no_such_verb_yet"}))
        reply = client.ask(daemon.card, {"op": "no_such_verb_yet"}, base=base)
    assert not reply.ok
    assert reply.error.startswith("this daemon is older than this command: it doesn't know the request 'no_such_verb_yet'")
    assert "pd install --force" in reply.error and "Input tag" not in reply.error
    # An op neither side knows is this command's defect, and no update of the daemon is advised.
    bad = client.ask(daemon.card, {"op": "no_such_verb_yet"}, base=base)
    assert "a defect in this command" in bad.error and "pd install" not in bad.error


def test_a_running_daemon_reports_its_build_on_its_own_request(tmp_path, base, run_daemon):
    daemon = run_daemon(make_home(tmp_path, []), base)
    reply = ask(daemon, {"op": "build"})
    assert reply["ok"] and reply["build"] == build.build_id()


def test_an_older_cli_still_reads_this_daemons_status(tmp_path, base, run_daemon):
    """Ira's review on #820: a CLI from before this change reads replies strictly, so a status
    carrying a field it doesn't know would stop pd status, the command meant to explain the
    drift. The status reply carries nothing new, and from here on a reply ignores what it
    doesn't know."""
    from pydantic import ConfigDict, ValidationError
    daemon = run_daemon(make_home(tmp_path, []), base)
    line = json.dumps(ask(daemon, {"op": "status"}))
    fields = {k: (v.annotation, v.default) for k, v in Response.model_fields.items() if k != "build"}
    from pydantic import create_model
    OlderResponse = create_model("OlderResponse", __config__=ConfigDict(extra="forbid"), **fields)
    assert OlderResponse.model_validate_json(line).ok             # what a CLI out there does
    with pytest.raises(ValidationError):
        OlderResponse.model_validate_json('{"ok": true, "build": "macf 9"}')
    assert Response.model_validate_json('{"ok": true, "some_later_field": 1}').ok


@pytest.mark.parametrize("daemon_build, says", [
    ("", "doesn't say which build it runs"),
    ("macf 0.6.0 at 0badc0de", "run different builds: the daemon macf 0.6.0 at 0badc0de, this command"),
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


def test_status_asks_the_daemon_for_its_build_separately(tmp_path, base, run_daemon):
    home = make_home(tmp_path, [])
    daemon = run_daemon(home, base)
    report = client.status(home, daemon.card, base=base)
    assert report.source == "daemon" and report.daemon_build == build.build_id() == report.cli_build


def test_two_commits_of_one_version_are_two_builds_and_edits_say_dirty(tmp_path):
    """The head maintainer's review on #820: the version is the same on every commit since a
    bump, so only the commit tells a pinned daemon from today's CLI, the case that prompted
    #816. Uncommitted edits make another build again."""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "one")
    (repo / "f.py").write_text("x = 1\n")
    git("add", "f.py")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "two")
    second = build.build_id(repo)
    git("checkout", "-q", "HEAD~1")
    first = build.build_id(repo)
    assert first != second and first.split(" at ")[0] == second.split(" at ")[0]
    git("checkout", "-q", "-")
    (repo / "f.py").write_text("x = 2\n")
    assert build.build_id(repo) == second + "-dirty"
