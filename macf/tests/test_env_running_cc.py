"""#866: `macf_tools env` names the binary the session runs, not only the one installed.

The installed binary is found through the `claude` launcher, which an auto-update moves under a
session that keeps running the older one. One host's line said 2.1.310 while the session's process
and transcript said 2.1.308.
"""
from macf.utils import paths


def test_the_running_binary_is_named_plainly_when_it_is_the_installed_one():
    installed = "/h/.local/share/claude/versions/2.1.326 (via /h/.local/bin/claude)"
    assert paths.describe_cc_running(installed, "/h/.local/share/claude/versions/2.1.326") == \
        "/h/.local/share/claude/versions/2.1.326"


def test_a_session_that_predates_an_update_is_marked():
    installed = "/h/.local/share/claude/versions/2.1.326 (via /h/.local/bin/claude)"
    line = paths.describe_cc_running(installed, "/h/.local/share/claude/versions/2.1.325")
    assert line.startswith("/h/.local/share/claude/versions/2.1.325")
    assert "not the installed binary" in line


def test_an_unknown_running_binary_says_so_and_is_not_guessed():
    assert "unknown" in paths.describe_cc_running("/h/claude", "")


def test_no_installed_binary_to_compare_with_leaves_the_running_one_unmarked():
    assert paths.describe_cc_running("(not found on PATH)", "/h/versions/2.1.325") == "/h/versions/2.1.325"


def test_the_running_binary_comes_from_claude_pid(monkeypatch):
    import macf.utils.formatting as f
    monkeypatch.setenv("CLAUDE_PID", "4242")
    monkeypatch.setattr(f, "_running_executable", lambda pid: f"/versions/for-{pid}")
    assert paths.detect_cc_running() == "/versions/for-4242"
    monkeypatch.delenv("CLAUDE_PID")
    assert paths.detect_cc_running() == ""


def test_env_prints_both_lines(capsys, monkeypatch):
    from macf import cli
    monkeypatch.setattr(paths, "detect_cc_binary", lambda: "/v/2.1.326 (via /bin/claude)")
    monkeypatch.setattr(paths, "detect_cc_running", lambda: "/v/2.1.325")
    monkeypatch.setattr(cli.sys, "argv", ["macf_tools", "env"])
    try:
        cli.main()
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "CC Installed:   /v/2.1.326 (via /bin/claude)" in out
    assert "CC Running:     /v/2.1.325 (not the installed binary" in out
