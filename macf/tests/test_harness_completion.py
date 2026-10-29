"""Shell completion: the printed scripts and the hidden candidates command (roadmap Phase 5).

``attach lum<TAB>`` offers every matching card; a remote that doesn't answer adds nothing
and doesn't hold completion past its timeout.
"""
import argparse
import shutil
import subprocess
import time

import pytest

from macf import cli
from macf.utils import roster
from macf.utils.completion import candidate_lines, command_tree, render_bash, render_zsh
from macf.utils.roster import completion_candidates, gather
from roster_seats import seats


@pytest.fixture(autouse=True)
def no_real_remotes(tmp_path, monkeypatch):
    """Candidates read the user's declared remotes; a test must never reach a real one."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no-config"))

CARDS = ["LumenMacEff@a1b2c3", "Lumen2MacEff@d4e5f6", "Lumen3MacEff@0a1b2c", "Lumen4MacEff@3c4d5e"]


def _small_parser():
    p = argparse.ArgumentParser(prog="macf_tools")
    sub = p.add_subparsers(dest="cmd")
    h = sub.add_parser("harness").add_subparsers(dest="harness_cmd")
    a = h.add_parser("attach")
    a.add_argument("--control", action="store_true")
    a.add_argument("--secret", help=argparse.SUPPRESS)
    h.add_parser("list").add_argument("--json", action="store_true")
    sub.add_parser("task")
    return p


def test_the_command_tree_holds_subcommands_and_visible_flags_only():
    tree = command_tree(_small_parser())
    assert {"harness", "task"} <= set(tree[""])
    assert {"attach", "list"} <= set(tree["harness"])
    assert "--control" in tree["harness attach"] and "--secret" not in tree["harness attach"]


def test_the_real_parser_has_harness_list_and_completion_in_its_tree():
    tree = command_tree(cli._build_parser())
    assert "list" in tree["harness"] and "attach" in tree["harness"]
    assert "completion" in tree[""]
    assert "--candidates" not in tree["completion"]         # hidden


def _fake_lister(monkeypatch, entries):
    monkeypatch.setattr(roster, "local_roster", lambda **kw: roster.Roster(entries=list(entries)))


def _candidates(capsys, *argv):
    rc = cli.cmd_completion(cli._build_parser().parse_args(["completion", "--candidates", *argv]))
    assert rc == 0
    return capsys.readouterr().out.splitlines()


def test_candidates_offer_every_matching_card(monkeypatch, capsys):
    """PLANT: the candidates command dropping an entry (completion_candidates skipping the
    last roster entry) loses a card here; this test fails."""
    _fake_lister(monkeypatch, seats())
    out = _candidates(capsys, "--prefix", "lum")
    for card in CARDS:
        assert card in out
    assert all(w.casefold().startswith("lum") for w in out)


def test_candidates_include_monikers_and_uuids(monkeypatch, capsys):
    _fake_lister(monkeypatch, seats())
    assert _candidates(capsys, "--prefix", "d4") == ["d4e5f6"]
    assert _candidates(capsys, "--prefix", "@d4") == ["@d4e5f6"]
    assert "Lumen3MacEff" in _candidates(capsys, "--prefix", "Lumen3")


def test_zsh_candidates_carry_the_endpoint_as_description(monkeypatch, capsys):
    _fake_lister(monkeypatch, seats())
    out = _candidates(capsys, "--describe", "--prefix", "Lumen2MacEff@")
    assert out == ["Lumen2MacEff@d4e5f6:local"]


def test_a_describe_line_escapes_colons_in_the_word():
    assert candidate_lines([("a:b", "local")], describe=True) == ["a\\:b:local"]


def test_an_unreadable_home_offers_no_candidate():
    locked = roster.RosterEntry(account="pa_x", reasons=dict.fromkeys((
        "card", "moniker", "uuid", "display_name", "session_kind", "home", "state"), "unreadable"))
    assert completion_candidates([locked], "") == []


def test_an_unreachable_remote_adds_nothing_and_costs_only_its_timeout():
    def hangs(timeout):
        time.sleep(30)
        return seats("never")

    def fails(timeout):
        raise OSError("ssh: connect to host gone port 22: No route to host")

    def answers(timeout):
        return seats("dolph")

    start = time.monotonic()
    entries, unanswered = gather(seats(), [hangs, fails, answers], timeout=0.3)
    assert time.monotonic() - start < 2.0
    assert {e.endpoint for e in entries} == {"local", "dolph"}
    assert len(entries) == 8 and len(unanswered) == 2
    assert any("No route to host" in u for u in unanswered)


def test_the_candidates_command_passes_its_timeout_to_each_remote(monkeypatch, capsys):
    _fake_lister(monkeypatch, seats())
    seen = []

    def remote(timeout):
        seen.append(timeout)
        return seats("dolph")

    monkeypatch.setattr(roster, "remote_fetchers", lambda: [remote])
    out = _candidates(capsys, "--describe", "--remote-timeout", "0.5", "--prefix", "Lumen2MacEff@")
    assert seen == [0.5]
    assert out == ["Lumen2MacEff@d4e5f6:local"]      # one word, offered once, first endpoint first


def test_completion_prints_a_script_for_each_shell(capsys):
    for shell, marker in (("bash", "complete -F _macf_tools macf_tools"), ("zsh", "#compdef macf_tools")):
        assert cli.cmd_completion(cli._build_parser().parse_args(["completion", shell])) == 0
        assert marker in capsys.readouterr().out


def test_completion_without_a_shell_exits_2(capsys):
    assert cli.cmd_completion(cli._build_parser().parse_args(["completion"])) == 2


def test_the_zsh_script_never_uses_path_as_a_variable():
    """In zsh ``path`` is tied to ``PATH``; a local by that name breaks every command."""
    script = render_zsh(command_tree(_small_parser()))
    assert "local path" not in script and "local mpath" in script


bash = shutil.which("bash")


@pytest.mark.skipif(bash is None, reason="no bash to source the script in")
def test_the_bash_script_parses():
    script = render_bash(command_tree(cli._build_parser()))
    assert subprocess.run([bash, "-n"], input=script, text=True).returncode == 0


def _complete_in_bash(tmp_path, line, candidates_out=""):
    """Source the script in a fresh bash and complete *line*, with ``macf_tools`` a fake
    that prints *candidates_out* for the candidates command."""
    fake = tmp_path / "macf_tools"
    fake.write_text("#!/bin/sh\ncat <<'EOF'\n" + candidates_out + "EOF\n")
    fake.chmod(0o755)
    script = tmp_path / "c.bash"
    script.write_text(render_bash(command_tree(_small_parser())))
    words = line.split(" ")
    driver = (f"source {script}\n"
              f"COMP_WORDS=({' '.join(repr(w) for w in words)})\n"
              f"COMP_WORDS[0]={fake}\n"
              f"COMP_CWORD={len(words) - 1}\n"
              f"COMP_LINE={line!r}\nCOMP_POINT=${{#COMP_LINE}}\n"
              "_macf_tools\nprintf '%s\\n' \"${COMPREPLY[@]}\"\n")
    return subprocess.run([bash, "--norc", "--noprofile"], input=driver, text=True,
                          capture_output=True, timeout=10).stdout.split()


@pytest.mark.skipif(bash is None, reason="no bash to source the script in")
def test_bash_completes_commands_from_the_table(tmp_path):
    assert _complete_in_bash(tmp_path, "macf_tools harness at") == ["attach"]
    assert _complete_in_bash(tmp_path, "macf_tools harness attach --con") == ["--control"]


@pytest.mark.skipif(bash is None, reason="no bash to source the script in")
def test_bash_attach_offers_the_candidates(tmp_path):
    got = _complete_in_bash(tmp_path, "macf_tools harness attach man", "\n".join(CARDS) + "\n")
    assert got == CARDS


@pytest.mark.skipif(bash is None, reason="no bash to source the script in")
def test_bash_trims_a_candidate_to_the_part_after_the_at(tmp_path):
    """bash breaks words at ``@``: after ``Lumen2MacEff@`` the word bash replaces is only
    what follows it, so the candidate must be trimmed or the card would be doubled."""
    line = "macf_tools harness attach Lumen2MacEff@d4"
    driver_words = ["macf_tools", "harness", "attach", "Lumen2MacEff", "@", "d4"]
    fake = tmp_path / "macf_tools"
    fake.write_text("#!/bin/sh\necho Lumen2MacEff@d4e5f6\n")
    fake.chmod(0o755)
    script = tmp_path / "c.bash"
    script.write_text(render_bash(command_tree(_small_parser())))
    driver = (f"source {script}\nCOMP_WORDS=({' '.join(driver_words)})\nCOMP_WORDS[0]={fake}\n"
              f"COMP_CWORD=5\nCOMP_LINE={line!r}\nCOMP_POINT=${{#COMP_LINE}}\n"
              "_macf_tools\nprintf '%s\\n' \"${COMPREPLY[@]}\"\n")
    out = subprocess.run([bash, "--norc", "--noprofile"], input=driver, text=True,
                         capture_output=True, timeout=10).stdout.split()
    assert out == ["d4e5f6"]
