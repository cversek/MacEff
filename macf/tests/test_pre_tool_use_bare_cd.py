"""Unit tests for `_is_bare_cd_command` in handle_pre_tool_use.

Regression coverage for the multi-line-bash detection gap (issue #82).
Pre-fix the detector only checked the whole-string-startswith and the first
`&&` fragment, so multi-line scripts with cd on a later line slipped past.
"""

import pytest

from macf.hooks.handle_pre_tool_use import _is_bare_cd_command


# --- Should DETECT (return True) -------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        # Original cases (covered before fix)
        "cd /tmp",
        "cd /tmp && ls",
        "  cd /tmp  ",  # leading/trailing whitespace

        # New cases (post-fix coverage — these slipped past before)
        "mkdir foo\ncd foo",                       # newline-separated, second line
        "echo a\ncd /tmp\necho b",                 # multi-line, cd in middle
        "mkdir foo; cd foo",                       # ;-separated
        "mkdir foo || cd /tmp",                    # ||-separated fallback
        "echo hello\nmkdir foo\ncd foo\nls",       # multi-line script with cd in middle
        "cd /a && cd /b",                          # both fragments are cd
        "ls /tmp; cd /etc",                        # ; then bare cd
    ],
)
def test_detects_bare_cd(command: str):
    assert _is_bare_cd_command(command) is True, \
        f"Expected detection for: {command!r}"


# --- Should NOT detect (return False) --------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        # Subshell — safe (cd is scoped to subshell)
        "(cd /tmp && ls)",
        "(cd /tmp; ls)",

        # Tool flags — not cd
        "git -C /tmp status",
        "pytest /full/path/to/tests",

        # Variable + absolute paths
        'D=/tmp; ls "$D"',
        'export PATH=/foo:$PATH; echo done',

        # Plain commands without cd
        "ls /tmp",
        "mkdir foo\nls foo",
        "echo cd /tmp",                            # cd is an argument to echo, not a command
        "git diff --cached",

        # Empty / whitespace
        "",
        "   ",
    ],
)
def test_does_not_detect_safe_commands(command: str):
    assert _is_bare_cd_command(command) is False, \
        f"Expected no detection for: {command!r}"
