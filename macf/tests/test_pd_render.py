"""Rendering a primal daemon for the host's own service manager.

This file holds the macOS rendering (MIS-0002 step 4). Linux renderings belong to
step 1 and get their own classes here.
"""
import plistlib
import shutil
import subprocess
import sys
import textwrap

import pytest

from macf.platform.launchd import launchctl_argv, pd_label, render_pd_launch_agent

CARD = "IraMacEff@ee9a78"
ARGV = ["/usr/bin/python3", "-m", "macf.pd", "/Users/someone/agent"]


def _plist(**overrides):
    kwargs = dict(card=CARD, program_argv=ARGV, home="/Users/someone", log_dir="/tmp/maceff-logs")
    kwargs.update(overrides)
    path, data = render_pd_launch_agent(**kwargs)
    return path, plistlib.loads(data)


class TestMacOSLaunchAgent:
    """MIS-0002-R05 (macos_MUST_render_LaunchAgent), with R02, R03 and R06 as they apply on macOS."""

    def test_launchd_is_launchagent(self):
        """A per-user LaunchAgent in the user's GUI session, never a LaunchDaemon."""
        path, plist = _plist()
        assert path == "/Users/someone/Library/LaunchAgents/" + pd_label(CARD) + ".plist"
        assert "UserName" not in plist          # a LaunchDaemon key: root running as someone
        assert plist["LimitLoadToSessionType"] == "Aqua"

    def test_identifier(self):
        """R06's conformance test on macOS: the identifier, made unique per agent from the
        calling card, so two agents on one login never share a label. It is the form
        the primal daemon's interface gives ``launchd_label``."""
        assert pd_label(CARD) == "maceff_pd.IraMacEff_ee9a78"
        assert pd_label("OtherAgent@0a1b2c") != pd_label(CARD)
        with pytest.raises(ValueError):
            pd_label("bad card/with slash")

    def test_outer_tier_restarts_pd(self):
        """R03 on macOS: launchd is the outer tier, so it is KeepAlive plus RunAtLoad. The
        conformance row names this test; the Linux rendering adds its own half."""
        _, plist = _plist()
        assert plist["KeepAlive"] is True and plist["RunAtLoad"] is True
        assert plist["ProgramArguments"] == ARGV

    def test_units_outlive_the_daemons_exit(self):
        """launchd leaves the daemon's process group alone when the daemon dies, so its units,
        the session among them, keep running for the restarted daemon to re-adopt."""
        _, plist = _plist()
        assert plist["AbandonProcessGroup"] is True

    def test_identity_never_travels_in_the_environment(self):
        """R02: the daemon reads its identity from the identity file, so the unit sets none."""
        _, plist = _plist()
        env = plist.get("EnvironmentVariables", {})
        assert not any(name.startswith("MACEFF_AGENT") for name in env)

    def test_launchctl_verbs_target_the_users_gui_domain(self):
        label = pd_label(CARD)
        argv = launchctl_argv("bootstrap", label, uid=501, plist_path="/x.plist")
        assert argv == ["launchctl", "bootstrap", "gui/501", "/x.plist"]
        assert launchctl_argv("kickstart", label, uid=501)[-1] == f"gui/501/{label}"
        with pytest.raises(ValueError):
            launchctl_argv("load", label, uid=501)   # the legacy verb is not offered

    @pytest.mark.live
    @pytest.mark.skipif(shutil.which("plutil") is None, reason="plutil is macOS-only")
    def test_rendered_plist_passes_plutil(self, tmp_path):
        _, data = render_pd_launch_agent(card=CARD, program_argv=ARGV, home=str(tmp_path), log_dir=str(tmp_path))
        target = tmp_path / "agent.plist"
        target.write_bytes(data)
        assert subprocess.run(["plutil", "-lint", str(target)], capture_output=True).returncode == 0


class TestMacOSInstall:
    """Install and removal as plans, applied only when asked (MIS-0002-R05, R129)."""

    SOCKETS = ["/tmp/maceff_pd-501/IraMacEff_ee9a78.control.sock"]

    def test_socket_path_length(self):
        """R129: a socket path the kernel would refuse stops the install before anything is written."""
        from macf.amail.broker import SUN_PATH_MAX
        from macf.platform.launchd import install_plan
        too_long = "/tmp/" + "d" * SUN_PATH_MAX + "/x.sock"
        with pytest.raises(OSError, match="longer than"):
            install_plan(CARD, ARGV, "/Users/someone", "/tmp/logs", 501, [too_long])

    def test_install_writes_the_plist_then_bootstraps(self):
        from macf.platform.launchd import install_plan
        steps = install_plan(CARD, ARGV, "/Users/someone", "/tmp/logs", 501, self.SOCKETS)
        assert [s.what for s in steps] == ["write", "launchctl"]
        assert steps[0].path.endswith("/Library/LaunchAgents/maceff_pd.IraMacEff_ee9a78.plist")
        assert steps[1].argv == ["launchctl", "bootstrap", "gui/501", steps[0].path]

    def test_apply_refuses_to_overwrite_a_changed_plist(self, tmp_path):
        from macf.platform.launchd import apply_plan, install_plan
        steps = install_plan(CARD, ARGV, str(tmp_path), str(tmp_path), 501, self.SOCKETS)
        ran = []
        ok = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})
        assert apply_plan(steps, run=lambda argv: ran.append(argv) or ok)[0].startswith("write ")
        assert ran == [steps[1].argv]
        with open(steps[0].path, "ab") as fh:
            fh.write(b"<!-- hand edit -->")
        with pytest.raises(FileExistsError):
            apply_plan(steps, run=lambda argv: ok)
        apply_plan(steps, run=lambda argv: ok, force=True)

    def test_a_failed_launchctl_is_said_not_hidden(self, tmp_path):
        from macf.platform.launchd import apply_plan, uninstall_plan
        bad = type("R", (), {"returncode": 5, "stdout": "", "stderr": "Boot-out failed: 5: Input/output error"})
        with pytest.raises(RuntimeError, match="Input/output error"):
            apply_plan(uninstall_plan(CARD, str(tmp_path), 501), run=lambda argv: bad)

    def test_removing_a_daemon_that_is_not_loaded_still_removes_its_plist(self, tmp_path):
        """launchd answers a boot-out of a service it does not have with exit 3, "No such
        process" (measured on macOS 15). That happens after an install whose bootstrap
        failed, after a reboot outside the GUI session, and on a second removal, and the
        plist must go in each case."""
        from macf.platform.launchd import apply_plan, install_plan, uninstall_plan
        ok = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})
        apply_plan(install_plan(CARD, ARGV, str(tmp_path), str(tmp_path), 501, self.SOCKETS), run=lambda argv: ok)
        plist = tmp_path / "Library" / "LaunchAgents" / (pd_label(CARD) + ".plist")
        assert plist.exists()
        not_loaded = type("R", (), {"returncode": 3, "stdout": "", "stderr": "Boot-out failed: 3: No such process"})
        done = apply_plan(uninstall_plan(CARD, str(tmp_path), 501), run=lambda argv: not_loaded)
        assert not plist.exists() and done[0].endswith("(not loaded)")

    def test_status_reads_launchctl_print(self):
        """Shapes measured on macOS: running with a pid, loaded but stopped, and absent."""
        from macf.platform.launchd import parse_print
        running = parse_print("\tstate = running\n\truns = 1\n\tpid = 8741\n\tlast exit code = (never exited)\n")
        assert running.loaded and running.running and running.pid == 8741
        stopped = parse_print("\tstate = not running\n\truns = 1\n\tlast exit code = 0\n")
        assert stopped.loaded and not stopped.running and stopped.pid is None and stopped.last_exit == "0"
        absent = parse_print('Bad request.\nCould not find service "maceff_pd.X_000000" in domain for user gui: 501\n')
        assert not absent.loaded and not absent.running


class TestMacOSFollowsTheInterface:
    """The label and the socket limit come from the step-1 interface, so one place names them."""

    def test_the_label_is_the_interfaces(self):
        from macf.pd.interface import launchd_label
        from macf.platform.launchd import pd_label
        assert pd_label(CARD) == launchd_label(CARD)


#: Run in a fresh interpreter, so a tray module another test already imported can't hide
#: an import of it here. The finder records every attempt, so a guarded
#: ``try: import macf.tray`` fails the test too: the layer may not even reach for it.
_WITHOUT_TRAY = textwrap.dedent("""
    import importlib, pkgutil, sys

    attempts = []

    class NoTray:
        def find_spec(self, name, path=None, target=None):
            if name == "macf.tray" or name.startswith("macf.tray."):
                attempts.append(name)
                raise ImportError("no tray on this host")

    sys.meta_path.insert(0, NoTray())
    import macf.observe, macf.pd, macf.platform
    for pkg in (macf.pd, macf.platform, macf.observe):
        for mod in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
            if not mod.name.endswith(".__main__"):    # importing a __main__ would run it
                importlib.import_module(mod.name)
    from macf.platform.launchd import render_pd_launch_agent
    from macf.platform.systemd import render_pd_user_unit
    argv = ["/usr/bin/python3", "-m", "macf.pd", "/home/someone/agent"]
    _, plist = render_pd_launch_agent("IraMacEff@ee9a78", argv, "/Users/someone", "/tmp/logs")
    _, unit = render_pd_user_unit("IraMacEff@ee9a78", argv, "/home/someone")
    assert b"tray" not in plist and "tray" not in unit
    assert attempts == [], attempts
""")


def test_runs_without_tray():
    """MIS-0002-R68 (layer_MUST-NOT_depend_on_tray): where the tray can't be imported, every
    module of the daemon, its platform adapters and observation still imports without reaching
    for it, and both outer-tier units render without naming it."""
    run = subprocess.run([sys.executable, "-c", _WITHOUT_TRAY], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def test_the_grant_probe_runs_as_a_one_shot_launch_agent(tmp_path):
    """The mechanism under MIS-0002-R64 (adapter_MUST_test_grants_at_install): the probe runs as a one-shot
    LaunchAgent with the daemon's own interpreter, so it tests what a launchd job holds, not
    what the terminal holds. It is loaded from the work directory, never ~/Library/LaunchAgents,
    and booted out after, with its files gone, so nothing of it starts at the next login."""
    import json
    from types import SimpleNamespace
    from macf.platform.launchd import grant_probe_label, run_grant_probe

    work, logs, calls = tmp_path / "work", tmp_path / "logs", []
    work.mkdir()
    logs.mkdir()

    def run(argv):
        calls.append(argv)
        if argv[1] == "bootstrap":
            plist = plistlib.loads(open(argv[3], "rb").read())
            calls.append(("plist", plist))
            prog = plist["ProgramArguments"]
            out, grants = prog[3], prog[4:]
            # launchd starts the job: the stand-in writes what the probe would
            with open(out, "w") as f:
                json.dump({g: "denied" if g == "local_network" else "held" for g in grants}, f)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    got = run_grant_probe(CARD, "/opt/venv/bin/python3", ["local_network", "accessibility"],
                          str(work), str(logs), 501, run)
    assert got == {"local_network": "denied", "accessibility": "held"}
    verbs = [c[1] for c in calls if isinstance(c, list)]
    assert verbs == ["bootout", "bootstrap", "bootout"]
    loaded = next(c for c in calls if isinstance(c, list) and c[1] == "bootstrap")
    assert loaded[2] == "gui/501" and loaded[3].startswith(str(work))
    plist = next(c[1] for c in calls if isinstance(c, tuple))
    assert plist["Label"] == grant_probe_label(CARD) == "maceff_pd.IraMacEff_ee9a78.grant_probe"
    assert plist["ProgramArguments"][:3] == ["/opt/venv/bin/python3", "-m", "macf.platform.grants"]
    assert plist["KeepAlive"] is False and plist["LimitLoadToSessionType"] == "Aqua"
    assert list(work.iterdir()) == []


def test_a_probe_that_never_answers_is_still_booted_out(tmp_path):
    from types import SimpleNamespace
    from macf.platform.launchd import run_grant_probe
    calls = []

    def run(argv):
        calls.append(argv[1])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with pytest.raises(RuntimeError, match="didn't answer"):
        run_grant_probe(CARD, "/opt/venv/bin/python3", ["accessibility"], str(tmp_path), str(tmp_path),
                        501, run, timeout=0.05, sleep=lambda s: None)
    assert calls[-1] == "bootout" and not list(tmp_path.glob("*.plist"))


def test_a_denial_is_never_guessed_from_a_failed_probe(monkeypatch):
    """A probe that breaks, and a grant with no dialog-free probe, read as untested, never held."""
    from macf.platform import grants
    monkeypatch.setitem(grants.PROBES, "accessibility", lambda: 1 / 0)
    got = grants.probe(["accessibility", "keychain", "automation:com.apple.Terminal"])
    assert all(v.startswith("untested:") for v in got.values())
