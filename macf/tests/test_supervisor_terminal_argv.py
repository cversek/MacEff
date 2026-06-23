"""Tests for terminal launch-argv construction in macf.supervisor.

Regression coverage for the auto-restart launch bug where the supervisor
command was passed to argv-respecting terminals (ptyxis, gnome-terminal) as a
single ``" ".join(...)`` token, making them try to exec the whole command line
as one filename:

    Failed to find executable 'python3 -m macf.supervisor ... -- foo.sh':
    No such file or directory

The fix passes the command as SEPARATE argv elements for terminals that exec
their command argument directly, and resolves ``x-terminal-emulator`` (the
Debian alternatives symlink) to its concrete terminal.
"""

import pytest

from macf.supervisor import (
    _applescript_quote,
    _shell_command_string,
    _terminal_argv,
    _terminal_command_form,
)

CMD = ["/usr/bin/python3", "-m", "macf.supervisor", "_run_loop",
       "--name", "demo", "--delay", "5", "--", "/path/launch.sh"]


# --- pure dispatch (_terminal_command_form) -------------------------------

@pytest.mark.parametrize("base", ["gnome-terminal", "ptyxis", "kgx", "tilix"])
def test_double_dash_terminals_keep_argv_separate(base):
    argv = _terminal_command_form(base, "/usr/bin/" + base, CMD)
    assert argv[:2] == ["/usr/bin/" + base, "--"]
    assert argv[2:] == CMD  # command preserved as separate tokens


@pytest.mark.parametrize("base", ["konsole", "xterm"])
def test_dash_e_terminals_keep_argv_separate(base):
    argv = _terminal_command_form(base, "/usr/bin/" + base, CMD)
    assert argv[:2] == ["/usr/bin/" + base, "-e"]
    assert argv[2:] == CMD


def test_foot_takes_command_directly():
    argv = _terminal_command_form("foot", "/usr/bin/foot", CMD)
    assert argv == ["/usr/bin/foot", *CMD]


def test_lxterminal_uses_single_shell_string():
    argv = _terminal_command_form("lxterminal", "/usr/bin/lxterminal", CMD)
    assert argv[:2] == ["/usr/bin/lxterminal", "-e"]
    assert len(argv) == 3  # the command collapses to ONE shell-quoted string
    assert argv[2] == _shell_command_string(CMD)


def test_unknown_terminal_defaults_to_double_dash():
    argv = _terminal_command_form("some-future-term", "/usr/bin/some-future-term", CMD)
    assert argv[:2] == ["/usr/bin/some-future-term", "--"]
    assert argv[2:] == CMD


def test_wrapper_suffix_is_stripped_for_dispatch():
    argv = _terminal_command_form(
        "gnome-terminal.wrapper", "/usr/bin/gnome-terminal.wrapper", CMD)
    assert argv[:2] == ["/usr/bin/gnome-terminal.wrapper", "--"]


def test_the_original_bug_is_gone():
    # No argv-respecting form may contain the whole command as one token.
    joined = " ".join(CMD)
    for base in ["gnome-terminal", "ptyxis", "konsole", "xterm", "foot"]:
        argv = _terminal_command_form(base, "/usr/bin/" + base, CMD)
        assert joined not in argv


# --- resolution (_terminal_argv) ------------------------------------------

def test_bare_name_resolved_via_path(monkeypatch):
    # A bare name must resolve through PATH, not become a bogus cwd path.
    monkeypatch.setattr("shutil.which", lambda t: "/usr/bin/ptyxis")
    monkeypatch.setattr("os.path.realpath", lambda p: p)
    argv = _terminal_argv("ptyxis", CMD)
    assert argv[0] == "/usr/bin/ptyxis"
    assert argv[1] == "--"
    assert argv[2:] == CMD


def test_x_terminal_emulator_resolves_to_concrete_terminal(monkeypatch):
    # Debian alternatives symlink -> ptyxis: use ptyxis's native -- form,
    # not the lossy x-terminal-emulator "-e <string>" compat interface.
    monkeypatch.setattr("shutil.which", lambda t: "/usr/bin/x-terminal-emulator")
    monkeypatch.setattr("os.path.realpath", lambda p: "/usr/bin/ptyxis")
    argv = _terminal_argv("x-terminal-emulator", CMD)
    assert argv[0] == "/usr/bin/ptyxis"
    assert argv[1] == "--"
    assert argv[2:] == CMD


def test_which_miss_falls_back_to_name(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda t: None)
    monkeypatch.setattr("os.path.realpath", lambda p: p)
    argv = _terminal_argv("xterm", CMD)
    assert argv[0] == "xterm"
    assert argv[1] == "-e"


# --- shell / applescript quoting helpers ----------------------------------

def test_shell_command_string_preserves_spaces():
    s = _shell_command_string(["/p ath/x", "-m", "a b"])
    assert s == "'/p ath/x' -m 'a b'"


def test_applescript_quote_escapes_backslash_and_quote():
    assert _applescript_quote('a "b" \\ c') == 'a \\"b\\" \\\\ c'
