"""The tray's Attach item: a terminal window attached to one agent's session (cversek/MacEff#726).

The window runs ``harness attach --card`` for that agent, which resolves the session from the
agent's own daemon. The tray only opens the window: it never types into a session
(MIS-0002-R71 (tray_MUST-NOT_type_into_session)), and it never asks a daemon to attach.
On macOS the window comes from ``open`` on a ``.command`` file, which needs no Automation
grant. iTerm2 understands tmux control mode, so it gets ``--control``. Terminal does not,
and control mode there would print the raw protocol, so it gets ``--no-control``.
"""
import shlex
import stat
import subprocess
from pathlib import Path

import pytest

from macf.tray.attach import attach_script, open_attach
from macf.tray.controller import Agent, Controller

PY = "/opt/py/bin/python3"


class _Open:
    """A stand-in that answers ``open`` and nothing else, so a new command fails loudly."""

    def __init__(self, returncode=0, stderr=""):
        self.calls = []
        self.returncode, self.stderr = returncode, stderr

    def __call__(self, argv, **kwargs):
        if argv[0] != "open":
            raise AssertionError(f"the tray ran {argv[0]!r}, which this stand-in does not answer")
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, self.returncode, "", self.stderr)


def _exec_argv(script: str):
    """The command the script's exec line runs, as the shell would split it."""
    line = next(l for l in script.splitlines() if l.startswith("exec "))
    return shlex.split(line)[1:]


def test_the_script_attaches_by_card_with_the_trays_own_interpreter():
    assert _exec_argv(attach_script("IraMacEff@ee9a78", PY, control=True)) == [
        PY, "-m", "macf.cli", "harness", "attach", "--card", "IraMacEff@ee9a78", "--control"]
    assert _exec_argv(attach_script("IraMacEff@ee9a78", PY, control=False))[-1] == "--no-control"


def test_a_card_the_shell_would_read_is_passed_as_one_word():
    card = "x'; touch /tmp/owned #@ab12"
    assert _exec_argv(attach_script(card, PY, control=False))[6] == card


def test_iterm_gets_a_control_mode_window(tmp_path):
    iterm = tmp_path / "iTerm.app"
    iterm.mkdir()
    run = _Open()
    done = open_attach("IraMacEff@ee9a78", directory=tmp_path / "rt", python=PY, iterm=iterm, run=run)
    assert done["ok"], done
    script = Path(done["script"])
    assert run.calls == [["open", "-a", str(iterm), str(script)]]
    assert script.suffix == ".command" and script.parent == tmp_path / "rt"
    assert _exec_argv(script.read_text())[-1] == "--control"
    mode = stat.S_IMODE(script.stat().st_mode)
    assert mode & stat.S_IXUSR and not mode & 0o077
    assert stat.S_IMODE(script.parent.stat().st_mode) == 0o700


def test_without_iterm_terminal_gets_a_plain_window(tmp_path):
    run = _Open()
    done = open_attach("IraMacEff@ee9a78", directory=tmp_path / "rt", python=PY,
                       iterm=tmp_path / "absent.app", run=run)
    assert done["ok"], done
    assert run.calls == [["open", "-a", "Terminal", done["script"]]]
    assert _exec_argv(Path(done["script"]).read_text())[-1] == "--no-control"


def test_the_script_never_types_into_a_session(tmp_path):
    """MIS-0002-R71: the window is the operator's; the tray sends no keys anywhere."""
    run = _Open()
    done = open_attach("IraMacEff@ee9a78", directory=tmp_path, python=PY, iterm=tmp_path / "no", run=run)
    assert "send-keys" not in Path(done["script"]).read_text()


def test_a_refused_open_is_said(tmp_path):
    run = _Open(returncode=1, stderr="LSOpenURLsWithRole() failed")
    done = open_attach("IraMacEff@ee9a78", directory=tmp_path, python=PY, iterm=tmp_path / "no", run=run)
    assert not done["ok"] and "LSOpenURLsWithRole" in done["error"]


def _controller(found):
    c = Controller(homes=list, paths=lambda: None)
    c.found = found
    cards = [a.card for a in found]
    c.agents = {a.card: a for a in found if cards.count(a.card) == 1}
    return c


def test_attach_opens_a_window_only_for_an_installed_card_and_asks_no_daemon():
    agent = Agent("IraMacEff@ee9a78", Path("/run/c.sock"), Path("/run/c.json"))
    c = _controller([agent])
    c._ask = lambda *a: pytest.fail("attach must not ask the daemon anything")
    opened = []
    assert c.attach("IraMacEff@ee9a78", opener=lambda card: opened.append(card) or {"ok": True})["ok"]
    assert opened == ["IraMacEff@ee9a78"]
    assert not c.attach("Nobody@000000", opener=lambda card: pytest.fail("opened"))["ok"]


def test_attach_refuses_a_card_two_homes_claim():
    twins = [Agent("Twin@aaaaaa", Path("/run/a"), Path("/run/a.json")),
             Agent("Twin@aaaaaa", Path("/run/b"), Path("/run/b.json"))]
    done = _controller(twins).attach("Twin@aaaaaa", opener=lambda card: pytest.fail("opened"))
    assert not done["ok"] and "two installed agents" in done["error"]


def test_a_link_planted_at_the_scripts_temporary_path_is_refused_and_said(tmp_path):
    """Nothing is written through the link, and the refusal comes back for the alert, not as
    an exception the menu callback would swallow."""
    victim = tmp_path / "victim"
    victim.write_text("untouched")
    (tmp_path / "rt").mkdir(mode=0o700)
    (tmp_path / "rt" / "attach-IraMacEff-ee9a78.tmp").symlink_to(victim)
    done = open_attach("IraMacEff@ee9a78", directory=tmp_path / "rt", python=PY,
                       iterm=tmp_path / "no", run=_Open())
    assert not done["ok"] and "could not be written" in done["error"]
    assert victim.read_text() == "untouched"


def test_a_runtime_directory_the_tray_cannot_use_is_said(tmp_path, monkeypatch):
    import macf.utils.paths as paths

    def refuse():
        raise PermissionError("the runtime directory is writable by others")
    monkeypatch.setattr(paths, "user_runtime_dir", refuse)
    run = _Open()
    done = open_attach("IraMacEff@ee9a78", python=PY, iterm=tmp_path / "no", run=run)
    assert not done["ok"] and "writable by others" in done["error"]
    assert run.calls == []
