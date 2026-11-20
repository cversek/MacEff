"""The tray's own LaunchAgent: what keeps the operator's tray running (#747).

The tray is one job for the GUI user, outside every agent's primal daemon, so a daemon in
trouble can't take down the view that shows it.
"""
import argparse
import plistlib
import shutil
import subprocess
from types import SimpleNamespace

from macf.platform.launchd import (TRAY_LABEL, apply_plan, render_tray_launch_agent,
                                   tray_install_plan, tray_uninstall_plan)

ARGV = ["/Users/someone/venv/bin/python", "-m", "macf.tray"]


def test_the_tray_job_relaunches_a_crash_and_respects_a_quit(tmp_path):
    """KeepAlive on an unsuccessful exit only: launchd relaunches a crashed or killed tray and
    leaves it down after Quit, which exits 0. It runs in the GUI session as an interactive app,
    and the tray, which lists agents by their ``maceff_pd.*`` jobs, doesn't count it as one."""
    from macf.tray.controller import installed_homes
    path, data = render_tray_launch_agent(ARGV, "/Users/someone", "/tmp/logs")
    plist = plistlib.loads(data)
    assert path == f"/Users/someone/Library/LaunchAgents/{TRAY_LABEL}.plist"
    assert plist["Label"] == TRAY_LABEL == "maceff_tray"
    assert plist["ProgramArguments"] == ARGV
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["RunAtLoad"] is True
    assert plist["LimitLoadToSessionType"] == "Aqua"
    assert plist["ProcessType"] == "Interactive"
    (tmp_path / f"{TRAY_LABEL}.plist").write_bytes(data)
    assert installed_homes(tmp_path) == []
    if shutil.which("plutil"):
        run = subprocess.run(["plutil", "-lint", str(tmp_path / f"{TRAY_LABEL}.plist")],
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stdout + run.stderr


def test_install_then_uninstall_through_the_plan(tmp_path):
    """Install writes the plist, then bootstraps it into the user's GUI domain. Uninstall boots
    it out, going on when launchd says it isn't loaded, and removes the plist."""
    calls = []

    def run(argv):
        calls.append(argv)
        # a boot-out finds nothing loaded (3), and so does the check that it is gone (113)
        return SimpleNamespace(returncode={"bootout": 3, "print": 113}.get(argv[1], 0), stdout="", stderr="")

    home = str(tmp_path)
    steps = tray_install_plan(ARGV, home, "/tmp/logs", 501)
    assert [s.what for s in steps] == ["launchctl", "unloaded", "write", "launchctl"]
    assert steps[0].argv[1] == "bootout" and steps[0].not_loaded_ok and steps[-1].argv[1] == "bootstrap"
    apply_plan(steps, run=run)
    plist_path = tmp_path / "Library" / "LaunchAgents" / f"{TRAY_LABEL}.plist"
    assert plist_path.exists()
    assert calls[0] == ["launchctl", "bootout", f"gui/501/{TRAY_LABEL}"]
    assert calls[-1] == ["launchctl", "bootstrap", "gui/501", str(plist_path)]
    calls.clear()

    done = apply_plan(tray_uninstall_plan(home, 501), run=run)
    assert calls[-1] == ["launchctl", "bootout", f"gui/501/{TRAY_LABEL}"]
    assert done[0].endswith("(not loaded)")
    assert not plist_path.exists()


def test_install_is_refused_where_the_host_cant_show_the_tray(monkeypatch, tmp_path, capsys):
    """MIS-0002-R73: where the host can't show the tray, install says why and writes nothing."""
    from macf.pd import cli
    from macf.platform import tray_host
    monkeypatch.setattr(tray_host, "tray_host",
                        lambda: tray_host.TrayHost(False, "nobody is logged in to the GUI"))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.cmd_pd_tray_install(argparse.Namespace(plan=False, force=False)) == 1
    assert "nobody is logged in to the GUI" in capsys.readouterr().err
    assert not (tmp_path / "Library").exists()


def test_uninstall_plan_changes_nothing(monkeypatch, tmp_path, capsys):
    """``--plan`` prints the boot-out and the removal, and runs neither."""
    from macf.pd import cli
    monkeypatch.setenv("HOME", str(tmp_path))
    agents = tmp_path / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / f"{TRAY_LABEL}.plist").write_bytes(b"x")
    assert cli.cmd_pd_tray_uninstall(argparse.Namespace(plan=True)) == 0
    out = capsys.readouterr().out
    assert "launchctl bootout gui/" in out and f"remove {agents}/{TRAY_LABEL}.plist" in out
    assert (agents / f"{TRAY_LABEL}.plist").exists()


def test_a_second_tray_install_replaces_the_loaded_job(tmp_path, monkeypatch):
    """launchd refuses to bootstrap a label it has loaded, so installing twice needs the boot-out first
    (#749). The stand-in answers a bootstrap only when the label is not loaded."""
    from macf.platform import launchd
    monkeypatch.setattr(launchd, "_sleep", lambda s: None)
    loaded = {"yes": False}
    calls = []

    def run(argv):
        calls.append(argv[1])
        if argv[1] == "bootstrap":
            if loaded["yes"]:
                return SimpleNamespace(returncode=5, stdout="", stderr="Bootstrap failed: 5: Input/output error")
            loaded["yes"] = True
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[1] == "bootout":
            was = loaded["yes"]
            loaded["yes"] = False
            return SimpleNamespace(returncode=0 if was else 3, stdout="", stderr="")
        return SimpleNamespace(returncode=0 if loaded["yes"] else 113, stdout="", stderr="")   # print

    home = str(tmp_path)
    for _ in range(2):            # a fresh host, then a host that already has the job loaded
        apply_plan(tray_install_plan(ARGV, home, "/tmp/logs", 501), run=run, force=True)
    assert loaded["yes"] is True
    assert calls.count("bootstrap") == 2 and calls.count("bootout") == 2
