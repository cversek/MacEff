"""The operator's remotes: declared in his own config, asked over ssh, handed off by card."""
import json
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

from macf.utils.remotes import (Fetcher, Remote, RemotesRefused, RemoteTooOld, fetch_roster,
                                handoff_argv, load_remotes, remotes_path)
from macf.utils.roster import RosterEntry, gather

SEATS = Remote(name="seats", host="box", port=2224, login="seat", list_login="pa_one")


def _entry(**over):
    fields = {"card": "Lumen2MacEff@3f9a1c", "moniker": "Lumen2MacEff", "uuid": "3f9a1c", "account": "pa_two",
              "display_name": "Lumen2", "session_kind": "daemon", "state": "running", "home": "/home/pa_two"}
    fields.update(over)
    return fields


def test_the_declaration_is_the_operators_own_file_and_refused_whole_when_wrong(tmp_path):
    assert remotes_path({"HOME": "/h"}) == Path("/h/.config/maceff/remotes.yaml")
    assert remotes_path({"HOME": "/h", "XDG_CONFIG_HOME": "/x"}) == Path("/x/maceff/remotes.yaml")
    assert load_remotes(tmp_path / "absent.yaml").remotes == []
    bad = tmp_path / "remotes.yaml"
    bad.write_text("remotes:\n  - {name: seats, host: box, login: seat}\n")
    with pytest.raises(RemotesRefused, match="list_login"):
        load_remotes(bad)
    bad.write_text("remotes:\n  - {name: a, host: x, login: me}\n  - {name: a, host: y, login: me}\n")
    with pytest.raises(RemotesRefused, match="unique"):
        load_remotes(bad)


def test_a_roster_is_asked_non_interactively_and_marked_as_the_remotes():
    seen = {}

    def run(argv, **kw):
        seen["argv"] = argv
        return SimpleNamespace(returncode=0, stdout=json.dumps([_entry()]), stderr="")

    entries = fetch_roster(SEATS, 1.0, run=run)
    assert seen["argv"][:3] == ["ssh", "-o", "BatchMode=yes"]
    assert seen["argv"][-7:] == ["-l", "pa_one", "-p", "2224", "--", "box", "macf_tools harness list --json --local"]
    assert [(e.card, e.endpoint) for e in entries] == [("Lumen2MacEff@3f9a1c", "seats")]


def test_a_remote_a_version_ahead_still_lists():
    def run(argv, **kw):
        return SimpleNamespace(returncode=0, stdout=json.dumps([{**_entry(), "new_field": 1}]), stderr="")

    assert [e.card for e in fetch_roster(SEATS, 1.0, run=run)] == ["Lumen2MacEff@3f9a1c"]


def test_an_unreachable_or_too_old_remote_is_said_never_empty():
    def unreachable(argv, **kw):
        return SimpleNamespace(returncode=255, stdout="", stderr="ssh: connect to host box: refused")

    def too_old(argv, **kw):
        return SimpleNamespace(returncode=2, stdout="", stderr="error: argument: invalid choice: 'list'")

    with pytest.raises(RemoteTooOld, match=r"ssh -t -l pa_one -p 2224 -- box macf_tools harness attach"):
        fetch_roster(SEATS, 1.0, run=too_old)
    local = [RosterEntry.model_validate({**_entry(), "card": "Here@aaaaaa", "endpoint": "local"})]
    entries, unanswered = gather(local, [Fetcher(SEATS, run=unreachable)], timeout=2.0)
    assert [e.card for e in entries] == ["Here@aaaaaa"]
    assert len(unanswered) == 1 and "unreachable" in unanswered[0] and "refused" in unanswered[0]


def test_the_handoff_carries_the_card_and_logs_in_as_the_seat():
    entry = RosterEntry.model_validate({**_entry(), "endpoint": "seats"})
    argv = handoff_argv(SEATS, entry, default_control=True)
    assert argv[:8] == ["ssh", "-t", "-l", "pa_two", "-p", "2224", "--", "box"]
    assert shlex.split(argv[8]) == ["macf_tools", "harness", "attach", "--card", "Lumen2MacEff@3f9a1c",
                                    "--control"]
    fixed = Remote(name="host", host="box", login="me", control=False)
    argv = handoff_argv(fixed, entry, default_control=True, read_only=True)
    assert argv[2:6] == ["-l", "me", "--", "box"]
    assert shlex.split(argv[6])[-2:] == ["--no-control", "--read-only"]


@pytest.mark.parametrize("field,value", [("account", "-oProxyCommand=touch /tmp/x"),
                                         ("account", "pa two"), ("card", "-oProxyCommand=x@abcdef")])
def test_a_roster_name_that_could_be_an_ssh_option_is_refused(field, value):
    """A roster is the remote's data; its account becomes the hand-off's login. One that
    begins with ``-o`` would run a command on the operator's machine (CTB on #806)."""
    def run(argv, **kw):
        return SimpleNamespace(returncode=0, stdout=json.dumps([{**_entry(), field: value}]), stderr="")

    with pytest.raises(RuntimeError, match="refused"):
        fetch_roster(SEATS, 1.0, run=run)
    # and should one reach the hand-off anyway, it is refused there, never passed to ssh
    entry = RosterEntry.model_validate({**_entry(), field: value, "endpoint": "seats"})
    with pytest.raises(ValueError):
        handoff_argv(SEATS, entry)


def test_the_operators_own_declaration_is_held_to_the_same_names(tmp_path):
    bad = tmp_path / "remotes.yaml"
    bad.write_text("remotes:\n  - {name: a, host: '-oProxyCommand=x', login: me}\n")
    with pytest.raises(RemotesRefused, match="host"):
        load_remotes(bad)
