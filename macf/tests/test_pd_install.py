"""``macf_tools pd install`` and ``uninstall``, and the installer checks each adapter makes:
nothing installed from a declaration that fails, the daemon's exact command line, a socket
path that cannot work, a unit that differs, and a removal that tolerates only "not loaded"."""
import json
import os
import plistlib
import pwd
import subprocess
import sys
from pathlib import Path

import pytest

from macf.cli import main
from macf.pd import adapter as adapters
from macf.pd.interface import Declaration, Unit, declaration_path

CARD = "Tester@abc123"
ME = pwd.getpwuid(os.getuid()).pw_name


def make_home(tmp_path, declared=True):
    home = tmp_path / "home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text("abc123def4567890\n")
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"moniker": "Tester"}}))
    if declared:
        unit = Unit(name="worker", command=["/bin/sleep", "60"], account=ME, restart="always",
                    liveness_interval_s=60, memory_limit_mb=64)
        path = declaration_path(home)
        path.parent.mkdir(parents=True)
        path.write_text(Declaration(version=1, agent=CARD, units=[unit]).model_dump_json())
    return home


class _Recorder:
    """This platform's adapter, recording what the command asked of it."""

    def __init__(self):
        self.platform = sys.platform
        self.installed, self.removed = [], []

    def render(self, card, agent_home):
        return f"run python -m macf.pd {agent_home}"

    def install(self, card, agent_home, force=False):
        self.installed.append((card, agent_home, force))
        return Path("/unit")

    def uninstall(self, card):
        self.removed.append(card)

    def status(self, card):
        return "running" if self.installed and not self.removed else "not loaded"


@pytest.fixture
def tier(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(adapters, "_ADAPTERS", {sys.platform: recorder})
    return recorder


def run(*argv):
    with pytest.raises(SystemExit) as exited:
        main(["pd", *argv])
    return exited.value.code


def test_a_declaration_that_fails_installs_nothing(tmp_path, monkeypatch, tier, capsys):
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(make_home(tmp_path, declared=False)))
    assert run("install") == 1
    assert tier.installed == [] and "nothing installed" in capsys.readouterr().err


def test_the_plan_prints_the_unit_and_changes_nothing(tmp_path, monkeypatch, tier, capsys):
    home = make_home(tmp_path)
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(home))
    assert run("install", "--plan") == 0
    assert tier.installed == [] and f"python -m macf.pd {home.resolve()}" in capsys.readouterr().out


def test_install_and_uninstall_name_the_resolved_home_and_its_own_card(tmp_path, monkeypatch, tier):
    """The card comes from the home's own files and the home is resolved, so a unit
    installed through a symlink still names the real home."""
    home = make_home(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(home)
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(link))
    assert run("install", "--force") == 0
    assert tier.installed == [(CARD, home.resolve(), True)]
    assert run("uninstall") == 0
    assert tier.removed == [CARD]


def test_the_launch_agent_runs_exactly_the_daemon_on_the_home(tmp_path):
    """MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config): the agent home is the daemon's
    only argument."""
    home = tmp_path / "home"
    plist = plistlib.loads(adapters.LaunchdAdapter(user_home=tmp_path).render(CARD, home).encode())
    assert plist["ProgramArguments"] == [sys.executable, "-m", "macf.pd", str(home)]


def test_a_socket_path_too_long_stops_the_launchd_install_before_anything_is_written(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / ("x" * 120)))
    calls = []
    tier = adapters.LaunchdAdapter(user_home=tmp_path, uid=os.getuid(), run=lambda argv: calls.append(argv))
    with pytest.raises(OSError):
        tier.install(CARD, tmp_path / "home")
    assert calls == [] and not (tmp_path / "Library").exists()


def test_a_socket_path_too_long_stops_the_systemd_install_before_anything_is_written(tmp_path, monkeypatch):
    """MIS-0002-R129 (adapter_MUST_check_socket_path_length) on Linux too."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / ("x" * 120)))
    calls = []
    tier = adapters.SystemdAdapter(user_home=tmp_path, run=lambda argv: calls.append(argv))
    with pytest.raises(OSError):
        tier.install(CARD, tmp_path / "home")
    assert calls == [] and not (tmp_path / ".config").exists()


def test_the_plan_names_the_interpreter_and_the_macf_it_runs(tmp_path, monkeypatch, tier, capsys):
    import macf
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(make_home(tmp_path)))
    assert run("install", "--plan") == 0
    out = capsys.readouterr().out
    assert sys.executable in out and str(Path(macf.__file__).resolve().parent) in out


def _ok(argv):
    return subprocess.CompletedProcess(argv, 0, "", "")


def test_a_systemd_unit_that_differs_is_replaced_only_with_force(tmp_path):
    tier = adapters.SystemdAdapter(user_home=tmp_path, run=_ok)
    path = tier.install(CARD, tmp_path / "home")
    path.write_text(path.read_text() + "# edited by hand\n")
    with pytest.raises(FileExistsError):
        tier.install(CARD, tmp_path / "home")
    assert "edited by hand" in path.read_text()
    tier.install(CARD, tmp_path / "home", force=True)
    assert "edited by hand" not in path.read_text()


def test_systemd_removal_tolerates_only_not_loaded(tmp_path):
    def not_loaded(argv):
        if argv[2] in ("stop", "disable"):
            return subprocess.CompletedProcess(argv, 5, "", f"Unit {argv[-1]} not loaded.")
        return _ok(argv)

    def refused(argv):
        if argv[2] == "stop":
            return subprocess.CompletedProcess(argv, 1, "", "Access denied")
        return _ok(argv)

    adapters.SystemdAdapter(user_home=tmp_path, run=not_loaded).uninstall(CARD)
    tier = adapters.SystemdAdapter(user_home=tmp_path, run=_ok)
    path = tier.install(CARD, tmp_path / "home")
    with pytest.raises(RuntimeError, match="Access denied"):
        adapters.SystemdAdapter(user_home=tmp_path, run=refused).uninstall(CARD)
    assert path.exists()


def test_uninstall_waits_for_the_service_to_go_before_it_reports(tmp_path, monkeypatch, tier, capsys):
    """launchctl bootout returns before the service is gone, so the line waits for "not
    loaded" rather than reporting a state that's already ending."""
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(make_home(tmp_path)))
    answers = iter(["loaded, pid 23510", "loaded, pid 23510", "not loaded"])
    tier.status = lambda card: next(answers, "not loaded")
    assert run("uninstall") == 0
    out = capsys.readouterr().out
    assert "no longer has it" in out and "pid 23510" not in out


def test_uninstall_says_so_when_the_service_stays(tmp_path, monkeypatch, tier, capsys):
    from macf.pd import cli as pd_cli
    monkeypatch.setattr(pd_cli, "UNINSTALL_WAIT_S", 0.3)
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(make_home(tmp_path)))
    tier.status = lambda card: "loaded, pid 23510"
    assert run("uninstall") == 0
    assert "still says: loaded, pid 23510" in capsys.readouterr().out
